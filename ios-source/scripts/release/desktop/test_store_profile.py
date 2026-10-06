"""Synthetic Store input safeguards; no app build, signing, launch or Store claim."""
import contextlib
import io
import json
import plistlib
import tempfile
import unittest
from pathlib import Path

import macos_store_profile as store


class StoreProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.profile = self.root / 'profile'
        store.prepare(self.profile)

    def fixture(self):
        app = self.root / 'Fixture.app'
        (app / 'Contents/MacOS').mkdir(parents=True)
        (app / 'Contents/MacOS/client').write_bytes(bytes.fromhex('cffaedfe'))
        info = {'CFBundleExecutable': 'client', 'CFBundleIdentifier': 'com.acme.GameRemote',
                **store.INFO_ADDITIONS}
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        header = self.root / 'qconfig.h'
        header.write_text('#define QT_FEATURE_appstore_compliant 1\n#define QT_VERSION_STR "6.9.3"\n')
        return app, header

    def replace_entitlements(self, data):
        path = self.profile / store.ENTITLEMENTS_NAME
        path.write_bytes(plistlib.dumps(data))
        self.rehash()

    def rehash(self):
        path = self.profile / 'profile.json'
        data = json.loads(path.read_text())
        data['files'] = {name: store.digest(self.profile / name)
                         for name in (store.ENTITLEMENTS_NAME, store.INFO_NAME)}
        path.write_text(json.dumps(data))

    def run_cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return store.main(list(args))

    def test_prepare_produces_valid_unsigned_inputs(self):
        files = store.validate_profile(self.profile)
        self.assertEqual(set(files), {store.ENTITLEMENTS_NAME, store.INFO_NAME})
        manifest = json.loads((self.profile / 'profile.json').read_text())
        self.assertEqual(manifest['status'], 'PREPARED_NOT_SIGNED')
        self.assertTrue(manifest['remaining_gates'])
        self.assertEqual(store.read_plist(self.profile / store.ENTITLEMENTS_NAME),
                         {key: True for key in store.REQUIRED_ENTITLEMENTS})

    def test_existing_direct_download_entitlement_has_exact_key(self):
        entitlements = store.read_plist(store.TEMPLATE.with_name('entitlements.xml'))
        self.assertEqual(entitlements, {'com.apple.security.device.audio-input': True})

    def test_production_bundle_template_includes_privacy_descriptions(self):
        info = store.read_plist(store.TEMPLATE.with_name('MacOSXBundleInfo.plist.in'))
        for key in store.INFO_ADDITIONS:
            with self.subTest(key=key):
                self.assertIsInstance(info.get(key), str)
                self.assertTrue(info[key].strip())

    def test_prepare_refuses_overwrite(self):
        before = {path.name: path.read_bytes() for path in self.profile.iterdir()}
        with self.assertRaisesRegex(ValueError, 'already exists'):
            store.prepare(self.profile)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.profile.iterdir()})

    def test_prepare_refuses_output_inside_app_or_alias(self):
        app, _ = self.fixture()
        alias = self.root / 'alias'
        alias.symlink_to(app, target_is_directory=True)
        for destination in (app / 'profile', alias / 'profile'):
            with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, 'outside every .app'):
                store.prepare(destination)
        self.assertFalse((app / 'profile').exists())

    def test_tampering_is_rejected_before_entitlement_validation(self):
        (self.profile / store.ENTITLEMENTS_NAME).write_bytes(b'invalid plist')
        with self.assertRaisesRegex(ValueError, 'hashes'):
            store.validate_profile(self.profile)

    def test_unknown_or_whitespace_entitlements_fail_even_with_updated_hash(self):
        for key in ('com.apple.security.get-task-allow', 'com.apple.security.cs.disable-library-validation',
                    'com.apple.security.temporary-exception.files.home-relative-path.read-write',
                    'com.apple.security.device.audio-input\n  '):
            with self.subTest(key=key):
                data = {name: True for name in store.REQUIRED_ENTITLEMENTS}
                data[key] = True
                self.replace_entitlements(data)
                with self.assertRaisesRegex(ValueError, 'unknown='):
                    store.validate_profile(self.profile)

    def test_missing_sandbox_fails_with_updated_hash(self):
        data = {name: True for name in store.REQUIRED_ENTITLEMENTS if name != 'com.apple.security.app-sandbox'}
        self.replace_entitlements(data)
        with self.assertRaisesRegex(ValueError, 'missing=.*app-sandbox'):
            store.validate_profile(self.profile)

    def test_non_boolean_or_disabled_entitlements_fail(self):
        for value in ('true', 1, False, ['true']):
            with self.subTest(value=value):
                data = {name: True for name in store.REQUIRED_ENTITLEMENTS}
                data['com.apple.security.app-sandbox'] = value
                self.replace_entitlements(data)
                with self.assertRaisesRegex(ValueError, 'boolean true'):
                    store.validate_profile(self.profile)

    def test_duplicate_plist_keys_fail(self):
        plist = self.root / 'duplicate.plist'
        plist.write_text('<plist version="1.0"><dict><key>key</key><true/><key>key</key><false/></dict></plist>')
        with self.assertRaisesRegex(ValueError, 'duplicate plist key'):
            store.read_plist(plist)

    def test_malformed_plist_and_non_dictionary_fail_cleanly(self):
        plist = self.root / 'bad.plist'
        for content in (b'<plist><dict>', plistlib.dumps(['unexpected']), b'not a plist'):
            with self.subTest(content=content):
                plist.write_bytes(content)
                with self.assertRaises(ValueError):
                    store.read_plist(plist)

    def test_profile_extra_file_and_symlink_fail(self):
        extra = self.profile / 'Other.entitlements'
        extra.write_text('ambiguous input')
        with self.assertRaisesRegex(ValueError, 'exactly'):
            store.validate_profile(self.profile)
        extra.unlink()
        info = self.profile / store.INFO_NAME
        external = self.root / 'external.plist'
        info.rename(external)
        info.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            store.validate_profile(self.profile)

    def test_profile_rejects_missing_privacy_description(self):
        info = dict(store.INFO_ADDITIONS)
        info['NSBluetoothAlwaysUsageDescription'] = ''
        (self.profile / store.INFO_NAME).write_bytes(plistlib.dumps(info))
        self.rehash()
        with self.assertRaisesRegex(ValueError, 'privacy description'):
            store.validate_profile(self.profile)

    def test_preflight_positive_is_inputs_only_and_read_only(self):
        app, header = self.fixture()
        before = {path: path.read_bytes() for tree in (app, self.profile)
                  for path in tree.rglob('*') if path.is_file()}
        before[header] = header.read_bytes()
        result = store.preflight(app, self.profile, header, 'com.acme.GameRemote')
        self.assertEqual(result['status'], 'PREFLIGHT_INPUTS_PASS')
        self.assertEqual(result['mach_o_images_inventoried'], 1)
        self.assertEqual(result['failures'], [])
        self.assertIn('No signature', result['scope'])
        self.assertTrue(result['remaining_gates'])
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_candidate_missing_privacy_descriptions_is_blocked(self):
        app, header = self.fixture()
        info_path = app / 'Contents/Info.plist'
        info = store.read_plist(info_path)
        del info['NSLocalNetworkUsageDescription']
        info['NSBluetoothAlwaysUsageDescription'] = ' '
        info_path.write_bytes(plistlib.dumps(info))
        result = store.preflight(app, self.profile, header, 'com.acme.GameRemote')
        self.assertEqual(result['status'], 'PREFLIGHT_BLOCKED')
        self.assertEqual(len(result['failures']), 2)

    def test_webengine_is_blocked(self):
        app, header = self.fixture()
        (app / 'Contents/MacOS/QtWebEngineProcess').write_bytes(bytes.fromhex('cffaedfe'))
        result = store.preflight(app, self.profile, header, 'com.acme.GameRemote')
        self.assertEqual(result['status'], 'PREFLIGHT_BLOCKED')
        self.assertIn('WebEngine', result['failures'][0])

    def test_candidate_escaping_link_is_blocked(self):
        app, header = self.fixture()
        (app / 'Contents/outside').symlink_to(self.root, target_is_directory=True)
        result = store.preflight(app, self.profile, header, 'com.acme.GameRemote')
        self.assertEqual(result['status'], 'PREFLIGHT_BLOCKED')
        self.assertIn('escaping or broken symlink', result['failures'][0])

    def test_bundle_id_must_match_explicit_selection(self):
        app, header = self.fixture()
        result = store.preflight(app, self.profile, header, 'com.acme.Other')
        self.assertEqual(result['status'], 'PREFLIGHT_BLOCKED')
        self.assertIn('bundle ID differs', result['failures'][0])

    def test_disabled_missing_commented_or_ambiguous_qt_flag_fails(self):
        header = self.root / 'qconfig.h'
        for flag in ('#define QT_FEATURE_appstore_compliant -1', '',
                     '// #define QT_FEATURE_appstore_compliant 1',
                     '/* #define QT_FEATURE_appstore_compliant 1 */',
                     '#define QT_FEATURE_appstore_compliant 1\n#define QT_FEATURE_appstore_compliant -1'):
            with self.subTest(flag=flag):
                header.write_text(flag + '\n#define QT_VERSION_STR "6.9.3"\n')
                with self.assertRaisesRegex(ValueError, 'exactly once as 1'):
                    store.qt_configuration(header)

    def test_other_qt_version_requires_explicit_future_profile_review(self):
        header = self.root / 'qconfig.h'
        header.write_text('#define QT_FEATURE_appstore_compliant 1\n#define QT_VERSION_STR "6.11.2"\n')
        with self.assertRaisesRegex(ValueError, 'Qt 6.9.x'):
            store.qt_configuration(header)

    def test_cli_records_blocker_and_returns_failure(self):
        app, header = self.fixture()
        header.write_text('#define QT_FEATURE_appstore_compliant -1\n#define QT_VERSION_STR "6.9.3"\n')
        report = self.root / 'blocked.json'
        status = self.run_cli('preflight', '--app', str(app), '--profile', str(self.profile),
                              '--qt-config-header', str(header), '--expected-bundle-id',
                              'com.acme.GameRemote', '--report', str(report))
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(report.read_text())['status'], 'PREFLIGHT_BLOCKED')

    def test_cli_refuses_report_overwrite_or_profile_mutation(self):
        app, header = self.fixture()
        report = self.root / 'existing.json'
        report.write_bytes(b'preserve me')
        for target in (report, self.profile / 'report.json'):
            with self.subTest(target=target):
                status = self.run_cli('preflight', '--app', str(app), '--profile', str(self.profile),
                                      '--qt-config-header', str(header), '--expected-bundle-id',
                                      'com.acme.GameRemote', '--report', str(target))
                self.assertEqual(status, 1)
        self.assertEqual(report.read_bytes(), b'preserve me')
        self.assertFalse((self.profile / 'report.json').exists())


if __name__ == '__main__':
    unittest.main()
