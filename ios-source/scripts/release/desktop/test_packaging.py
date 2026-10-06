"""Synthetic safeguard fixtures, not store/runtime acceptance tests."""
import hashlib
import io
import json
import plistlib
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import flatpak_prepare
import macos_stage
import macos_validate as mac
import windows_msix as win


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def app(self):
        app = self.root / 'Candidate.app'
        (app / 'Contents/MacOS').mkdir(parents=True)
        (app / 'Contents/Frameworks').mkdir()
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'client'}))
        main = app / 'Contents/MacOS/client'
        lib = app / 'Contents/Frameworks/libfoo.dylib'
        for image in (main, lib):
            image.write_bytes(bytes.fromhex('cffaedfe'))
        metadata = {main: {'native': {'dependencies': ['@rpath/libfoo.dylib'], 'rpaths': ['@executable_path/../Frameworks']}},
                    lib: {'native': {'dependencies': ['/usr/lib/libSystem.B.dylib'], 'rpaths': []}}}
        return app, main, lib, metadata

    def test_macos_resolves_rpath_and_cache_system_library(self):
        app, _, _, metadata = self.app()
        report = mac.validate(app, metadata.__getitem__)
        self.assertEqual(report['mach_o_images'], 2)
        self.assertEqual(report['loads'][0]['resolved'], 'Contents/Frameworks/libfoo.dylib')

    def test_macos_rejects_private_dependency(self):
        app, _, lib, metadata = self.app()
        metadata[lib]['native']['dependencies'] = ['/opt/homebrew/lib/libfoo.dylib']
        with self.assertRaisesRegex(ValueError, 'absolute non-system'):
            mac.validate(app, metadata.__getitem__)

    def test_macos_validates_unreached_architecture_of_reached_image(self):
        app, main, lib, _ = self.app()
        metadata = {
            main: {
                'arm64': {'dependencies': ['@rpath/libfoo.dylib'], 'rpaths': ['@executable_path/../Frameworks']},
                'x86_64': {'dependencies': [], 'rpaths': ['@executable_path/../Frameworks']},
            },
            lib: {
                'arm64': {'dependencies': ['/usr/lib/libSystem.B.dylib'], 'rpaths': []},
                'x86_64': {'dependencies': ['/private/not-shipped/libbad.dylib'], 'rpaths': []},
            },
        }
        with self.assertRaisesRegex(ValueError, 'absolute non-system'):
            mac.validate(app, metadata.__getitem__)

    def test_macos_checks_symlinked_qt_conf(self):
        app, _, _, metadata = self.app()
        resources = app / 'Contents/Resources'
        resources.mkdir()
        (resources / 'private-settings.ini').write_text('[Paths]\nPrefix=/private/not-shipped/qt\n')
        (resources / 'qt.conf').symlink_to('private-settings.ini')
        with self.assertRaisesRegex(ValueError, 'absolute qt.conf'):
            mac.validate(app, metadata.__getitem__)

    def test_macos_stage_rejects_copied_links_before_mutation(self):
        app, main, _, _ = self.app()
        original_bytes = main.read_bytes()
        original_directory = main.parent
        relocated = app / 'Contents/RealMacOS'
        original_directory.rename(relocated)
        original_directory.symlink_to(relocated, target_is_directory=True)
        notices = self.root / 'notices'
        notices.mkdir()
        for name in ('COPYING', 'THIRD_PARTY_NOTICES.txt', 'SOURCE_OFFER.txt'):
            (notices / name).write_text('synthetic test fixture')
        deploy = self.root / 'macdeployqt'
        deploy.write_text('synthetic tool path')
        qml = self.root / 'qml'
        qml.mkdir()
        report = self.root / 'report.json'
        with patch('macos_stage.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'escaping or broken symlink'):
                macos_stage.stage(app, self.root / 'Staged.app', deploy, qml, notices, report)
            run.assert_not_called()
        self.assertEqual((relocated / 'client').read_bytes(), original_bytes)
        self.assertEqual(json.loads(report.read_text())['status'], 'FAILED')

    def test_macos_rejects_escaping_symlink_and_private_qt_conf(self):
        app, _, _, _ = self.app()
        link = app / 'Contents/Frameworks/external'
        link.symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'escaping'):
            mac.inventory(app)
        link.unlink()
        (app / 'Contents/MacOS/qt.conf').write_text('[Paths]\nPrefix=/private/qt\n')
        with self.assertRaisesRegex(ValueError, 'qt.conf'):
            mac.inventory(app)

    def test_macos_system_path_cannot_escape_via_parent_segments(self):
        app, _, lib, metadata = self.app()
        metadata[lib]['native']['dependencies'] = ['/usr/lib/../../private/libfoo.dylib']
        with self.assertRaisesRegex(ValueError, 'absolute non-system'):
            mac.validate(app, metadata.__getitem__)

    def test_macos_rejects_orphan_plugin_load(self):
        app, _, _, metadata = self.app()
        plugin = app / 'Contents/Frameworks/plugin.dylib'
        plugin.write_bytes(bytes.fromhex('cffaedfe'))
        metadata[plugin] = {'native': {'dependencies': ['@rpath/missing.dylib'], 'rpaths': []}}
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            mac.validate(app, metadata.__getitem__)

    def test_loader_prefers_image_rpath_over_inherited(self):
        app, _, lib, metadata = self.app()
        nested = app / 'Contents/Frameworks/Nested'
        nested.mkdir()
        second = nested / 'libfoo.dylib'
        second.write_bytes(bytes.fromhex('cffaedfe'))
        metadata[lib]['native'] = {'dependencies': ['@rpath/libfoo.dylib'], 'rpaths': ['@loader_path/Nested']}
        metadata[second] = {'native': {'dependencies': [], 'rpaths': []}}
        report = mac.validate(app, metadata.__getitem__)
        load = next(x for x in report['loads'] if x['image'] == 'Contents/Frameworks/libfoo.dylib')
        self.assertEqual(load['resolved'], 'Contents/Frameworks/Nested/libfoo.dylib')

    def test_load_command_parser_ignores_install_id_and_preserves_spaces(self):
        output = 'file (architecture arm64):\n cmd LC_ID_DYLIB\n name /private/own.dylib (offset 24)\n cmd LC_LOAD_DYLIB\n name @rpath/lib Foo.dylib (offset 24)\n cmd LC_RPATH\n path @loader_path/../Frameworks (offset 12)\n'
        data = mac.parse_load_commands(output)
        self.assertEqual(data['arm64']['dependencies'], ['@rpath/lib Foo.dylib'])

    def test_macos_stage_preserves_source_and_reports_failure(self):
        app, _, _, _ = self.app()
        resources = app / 'Contents/Resources'
        resources.mkdir()
        original = '[Paths]\nPrefix=/private/qt\n'
        (resources / 'qt.conf').write_text(original)
        notices = self.root / 'notices'
        notices.mkdir()
        for name in ('COPYING', 'THIRD_PARTY_NOTICES.txt', 'SOURCE_OFFER.txt'):
            (notices / name).write_text('synthetic test fixture')
        deploy = self.root / 'macdeployqt'
        deploy.write_text('synthetic tool path; process is mocked')
        qml = self.root / 'qml'
        qml.mkdir()
        candidate = self.root / 'Staged.app'
        report = self.root / 'report.json'
        with (
            patch('macos_stage.subprocess.run'),
            patch('macos_stage.validate', side_effect=ValueError('private dependency')),
            self.assertRaisesRegex(ValueError, 'private dependency'),
        ):
            macos_stage.stage(app, candidate, deploy, qml, notices, report)
        self.assertEqual((resources / 'qt.conf').read_text(), original)
        self.assertNotIn('/private/qt', (candidate / 'Contents/Resources/qt.conf').read_text())
        self.assertEqual(json.loads(report.read_text())['status'], 'FAILED')
        mac.inventory(candidate)  # Containment and generated Qt path layout pass.

    def test_macos_qt_prefix_is_relative_to_contents(self):
        app, _, _, _ = self.app()
        resources = app / 'Contents/Resources'
        resources.mkdir()
        conf = resources / 'qt.conf'
        conf.write_text('[Paths]\nPrefix=..\nPlugins=../escaping\n')
        with self.assertRaisesRegex(ValueError, 'escaping qt.conf'):
            mac.inventory(app)

    def deployment(self):
        source = self.root / 'deployment'
        source.mkdir()
        paths = ('client.exe', 'logo.png', 'COPYING', 'THIRD_PARTY_NOTICES.txt', 'SOURCE_OFFER.txt',
                 'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Qml.dll', 'Qt6Quick.dll', 'Qt6WebEngineCore.dll',
                 'QtWebEngineProcess.exe', 'platforms/qwindows.dll')
        for name in paths:
            path = source / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'fixture')
        identity = {
            'name': 'Example.Product', 'publisher': 'CN=Example Publisher', 'display_name': 'Remote Play Prototype',
            'publisher_display_name': 'Example Publisher', 'version': '1.2.3.0', 'arch': 'x64',
            'executable': 'client.exe', 'logo': 'logo.png', 'logo_44': 'logo44.png', 'logo_150': 'logo150.png',
        }
        for name, size in (('logo.png', 50), ('logo44.png', 44), ('logo150.png', 150)):
            (source / name).write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' + struct.pack('>II', size, size))
        return source, identity

    def test_windows_stages_explicit_identity_and_preserves_notices(self):
        source, identity = self.deployment()
        stage = self.root / 'stage'
        win.prepare(source, stage, identity)
        tree = ET.parse(stage / 'AppxManifest.xml')
        entry = tree.find('{' + win.FOUNDATION + '}Identity')
        self.assertEqual(entry.attrib['Name'], identity['name'])
        self.assertEqual(entry.attrib['Publisher'], identity['publisher'])
        self.assertTrue((stage / 'SOURCE_OFFER.txt').exists())
        self.assertFalse((source / 'AppxManifest.xml').exists())

    def test_windows_rejects_missing_runtime_and_traversal(self):
        source, identity = self.deployment()
        identity['logo'] = '../outside.png'
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            win.prepare(source, self.root / 'stage', identity)
        identity['logo'] = 'logo.png'
        (source / 'platforms/qwindows.dll').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            win.prepare(source, self.root / 'stage', identity)

    def test_windows_cli_stages_without_webengine_when_explicitly_disabled(self):
        source, identity = self.deployment()
        for name in ('Qt6WebEngineCore.dll', 'QtWebEngineProcess.exe'):
            (source / name).unlink()
        stage = self.root / 'stage'
        command = [sys.executable, str(Path(win.__file__).resolve()),
                   '--deployment', str(source), '--stage', str(stage),
                   '--prepare-only', '--webengine', 'disabled']
        for key, value in identity.items():
            command.extend(['--' + key.replace('_', '-'), value])
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((stage / 'AppxManifest.xml').is_file())
        self.assertTrue((stage / 'platforms/qwindows.dll').is_file())
        self.assertFalse((stage / 'QtWebEngineProcess.exe').exists())
        self.assertFalse((source / 'AppxManifest.xml').exists())

    def test_windows_enabled_webengine_requires_browser_files(self):
        source, identity = self.deployment()
        identity['webengine'] = 'enabled'
        for name in ('Qt6WebEngineCore.dll', 'QtWebEngineProcess.exe'):
            with self.subTest(missing=name):
                image = source / name
                original = image.read_bytes()
                image.unlink()
                with self.assertRaisesRegex(ValueError, name):
                    win.prepare(source, self.root / 'stage', identity)
                self.assertFalse((self.root / 'stage').exists())
                image.write_bytes(original)

    def test_windows_disabled_webengine_still_requires_qt_platform(self):
        source, identity = self.deployment()
        identity['webengine'] = 'disabled'
        for name in ('Qt6WebEngineCore.dll', 'QtWebEngineProcess.exe', 'platforms/qwindows.dll'):
            (source / name).unlink()
        with self.assertRaisesRegex(ValueError, 'qwindows.dll'):
            win.prepare(source, self.root / 'stage', identity)
        self.assertFalse((self.root / 'stage').exists())

    def test_windows_rejects_invalid_webengine_selection(self):
        source, identity = self.deployment()
        identity['webengine'] = 'disable'
        with self.assertRaisesRegex(ValueError, 'WebEngine selection'):
            win.prepare(source, self.root / 'stage', identity)
        self.assertFalse((self.root / 'stage').exists())

    def test_windows_dependency_inventory_rejects_absent_dll(self):
        source, _ = self.deployment()
        with (
            patch('subprocess.check_output', return_value='Image has the following dependencies:\n    VCRUNTIME140.dll\n'),
            self.assertRaisesRegex(ValueError, 'missing runtime DLL'),
        ):
            win.validate_dlls(source, ['kernel32.dll'])
        with patch('subprocess.check_output', return_value='Image has the following dependencies:\n    KERNEL32.dll\n'):
            win.validate_dlls(source, ['kernel32.dll'])

    def archive(self, revision):
        archive = self.root / 'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            for name, value in {'RELEASE_SOURCE_REVISION': revision, 'COPYING': 'license fixture', 'CMakeLists.txt': 'source fixture'}.items():
                data = value.encode()
                entry = tarfile.TarInfo('source/' + name)
                entry.size = len(data)
                output.addfile(entry, io.BytesIO(data))
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_flatpak_preserves_manifest_and_pins_local_source(self):
        revision = 'a' * 40
        archive, digest = self.archive(revision)
        manifest = self.root / 'manifest.yaml'
        manifest.write_text('app-id: org.example.Client\nruntime: org.kde.Platform\nruntime-version: "6.9"\nmodules:\n  - name: GameRemote\n    sources:\n      - type: git\n        url: https://upstream.invalid/source\n        branch: main\n')
        result = flatpak_prepare.prepare(manifest, archive, digest, revision, 'org.example.Client')
        self.assertEqual(result['modules'][0]['sources'], [{'type': 'archive', 'path': str(archive), 'sha256': digest}])
        self.assertIn('upstream.invalid', manifest.read_text())
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            flatpak_prepare.prepare(manifest, archive, '0' * 64, revision, 'org.example.Client')
        with self.assertRaisesRegex(ValueError, 'revision metadata mismatch'):
            flatpak_prepare.prepare(manifest, archive, digest, 'b' * 40, 'org.example.Client')

    def test_flatpak_real_manifest_is_rebound_without_policy_changes(self):
        revision = 'c' * 40
        archive, digest = self.archive(revision)
        manifest = Path(__file__).resolve().parents[3] / 'scripts/flatpak/org.example.GameRemote.yaml'
        import yaml
        original = yaml.safe_load(manifest.read_text())
        result = flatpak_prepare.prepare(manifest, archive, digest, revision, original['app-id'])
        self.assertEqual(result['finish-args'], original['finish-args'])
        self.assertEqual(result['runtime-version'], original['runtime-version'])
        app = next(x for x in result['modules'] if x['name'] == 'GameRemote')
        self.assertEqual(app['sources'][0]['sha256'], digest)
        self.assertEqual(app['sources'][0]['path'], str(archive))
        self.assertNotIn('url', app['sources'][0])


if __name__ == '__main__':
    unittest.main()
