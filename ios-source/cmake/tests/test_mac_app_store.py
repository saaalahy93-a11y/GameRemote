"""Configure-only safeguards using synthetic Qt targets; no SDK/build/signing claim."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'MacAppStore.cmake'
RECEIPT = 'gameremote-mac-app-store-qt.json'


class MacAppStoreGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gameremote-store-guard-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source'
        self.build = self.root / 'build'
        self.source.mkdir()
        self.build.mkdir()
        self.include = self.root / 'selected-sdk/include/QtCore'
        self.include.mkdir(parents=True)
        self.header = self.include / 'qconfig.h'
        self.header.write_text('#define QT_FEATURE_appstore_compliant 1\n')
        self.cmake = os.environ.get('CMAKE_COMMAND') or shutil.which('cmake')
        self.assertIsNotNone(self.cmake, 'cmake is required; this safeguard must not be silently skipped')

    def configure(self, *, store=True, apple=True, system='Darwin', gui=True,
                  webengine=False, steam=False, include_dirs=None, target=True):
        def cmake_bool(value):
            return 'ON' if value else 'OFF'

        include_dirs = [self.include] if include_dirs is None else include_dirs
        lines = [
            'cmake_minimum_required(VERSION 3.10)',
            'project(StoreGuardFixture NONE)',
            f'include("{MODULE.as_posix()}")',
            f'set(GAMEREMOTE_MAC_APP_STORE {cmake_bool(store)})',
            f'set(APPLE {cmake_bool(apple)})',
            f'set(CMAKE_SYSTEM_NAME "{system}")',
            f'set(CHIAKI_ENABLE_GUI {cmake_bool(gui)})',
            f'set(CHIAKI_ENABLE_WEBENGINE {cmake_bool(webengine)})',
            f'set(CHIAKI_ENABLE_STEAM_SHORTCUT {cmake_bool(steam)})',
            'gameremote_validate_mac_app_store_options()',
        ]
        if target:
            lines += [
                'add_library(Qt6::Core INTERFACE IMPORTED)',
                'set_property(TARGET Qt6::Core PROPERTY INTERFACE_INCLUDE_DIRECTORIES "'
                + ';'.join(str(directory) for directory in include_dirs) + '")',
                'set(Qt6Core_VERSION "fixture-only")',
                f'set(Qt6Core_DIR "{self.root.as_posix()}/selected-sdk/lib/cmake/Qt6Core")',
            ]
        lines.append('gameremote_validate_mac_app_store_qt(Qt6::Core)')
        (self.source / 'CMakeLists.txt').write_text('\n'.join(lines) + '\n')
        return subprocess.run([self.cmake, '-S', str(self.source), '-B', str(self.build)],
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)

    def assert_rejected(self, message, **options):
        # A failed reconfigure must not leave an earlier successful receipt.
        (self.build / RECEIPT).write_text('{"stale": true}\n')
        result = self.configure(**options)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, ' '.join(result.stdout.split()), result.stdout)
        self.assertFalse((self.build / RECEIPT).exists(), 'stale successful receipt survived')

    def test_normal_build_does_not_require_store_sdk_or_features(self):
        (self.build / RECEIPT).write_text('{"stale": true}\n')
        result = self.configure(store=False, apple=False, system='Linux', gui=False,
                                webengine=True, steam=True, target=False)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.build / RECEIPT).exists())

    def test_non_apple_and_ios_targets_are_rejected(self):
        for apple, system in [(False, 'Linux'), (True, 'iOS')]:
            with self.subTest(system=system):
                self.assert_rejected('requires a macOS (APPLE/Darwin) target', apple=apple, system=system)

    def test_gui_cannot_be_disabled_to_bypass_qt_validation(self):
        self.assert_rejected('requires CHIAKI_ENABLE_GUI=ON', gui=False)

    def test_embedded_browser_is_rejected(self):
        self.assert_rejected('requires CHIAKI_ENABLE_WEBENGINE=OFF', webengine=True)

    def test_steam_external_writes_are_rejected(self):
        self.assert_rejected('requires CHIAKI_ENABLE_STEAM_SHORTCUT=OFF', steam=True)

    def test_missing_target_is_rejected(self):
        self.assert_rejected('target Qt6::Core is missing', target=False)

    def test_missing_header_is_rejected(self):
        self.header.unlink()
        self.assert_rejected('found 0:')

    def test_empty_include_paths_are_rejected(self):
        self.assert_rejected('found 0:', include_dirs=[])

    def test_disabled_and_unresolved_features_are_rejected(self):
        for value in ['-1', '0', 'APPSTORE_FLAG', '(1)']:
            with self.subTest(value=value):
                self.header.write_text(f'#define QT_FEATURE_appstore_compliant {value}\n')
                self.assert_rejected('requires QT_FEATURE_appstore_compliant=1')

    def test_missing_or_duplicate_flag_is_rejected(self):
        for content in ['', '// #define QT_FEATURE_appstore_compliant 1\n',
                        '#define QT_FEATURE_appstore_compliant 1\n#define QT_FEATURE_appstore_compliant -1\n',
                        '#define QT_FEATURE_appstore_compliant 1\n#undef QT_FEATURE_appstore_compliant\n']:
            with self.subTest(content=content):
                self.header.write_text(content)
                self.assert_rejected('missing or ambiguous QT_FEATURE_appstore_compliant flag')

    def test_undef_is_rejected(self):
        self.header.write_text('#undef QT_FEATURE_appstore_compliant\n')
        self.assert_rejected('requires QT_FEATURE_appstore_compliant=1')

    def test_multiple_sdk_headers_are_rejected_even_if_both_enabled(self):
        other = self.root / 'other-sdk/QtCore'
        other.mkdir(parents=True)
        (other / 'qconfig.h').write_text(self.header.read_text())
        self.assert_rejected('found 2:', include_dirs=[self.include, other])

    def test_unselected_enabled_sdk_does_not_rescue_selected_disabled_sdk(self):
        other = self.root / 'unselected-sdk/QtCore'
        other.mkdir(parents=True)
        (other / 'qconfig.h').write_text('#define QT_FEATURE_appstore_compliant 1\n')
        self.header.write_text('#define QT_FEATURE_appstore_compliant -1\n')
        self.assert_rejected('requires QT_FEATURE_appstore_compliant=1')

    def test_unresolved_generator_expression_is_rejected(self):
        self.assert_rejected('cannot resolve the selected QtCore include directory',
                             include_dirs=[f'$<BUILD_INTERFACE:{self.include}>'])

    def test_enabled_selected_sdk_creates_exact_header_receipt(self):
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stdout)
        receipt = json.loads((self.build / RECEIPT).read_text())
        self.assertEqual(receipt['qconfig_header'], str(self.header.resolve()))
        self.assertEqual(receipt['qconfig_sha256'], hashlib.sha256(self.header.read_bytes()).hexdigest())
        self.assertEqual(receipt['appstore_compliant'], 1)
        self.assertFalse(receipt['embedded_webengine'])
        self.assertFalse(receipt['steam_shortcut'])
        self.assertEqual(receipt['scope'], 'configure-time Qt feature check only')

    def test_framework_symlinks_to_one_header_are_not_ambiguous(self):
        framework = self.root / 'QtCore.framework'
        framework.mkdir()
        (framework / 'Headers').symlink_to(self.include, target_is_directory=True)
        result = self.configure(include_dirs=[framework, framework / 'Headers', self.include])
        self.assertEqual(result.returncode, 0, result.stdout)
        receipt = json.loads((self.build / RECEIPT).read_text())
        self.assertEqual(receipt['qconfig_header'], str(self.header.resolve()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
