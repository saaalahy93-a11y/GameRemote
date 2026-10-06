"""Rejection tests for candidate-only dependency relocation and runtime gates."""
import json
import plistlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import macos_relocate as relocation
import macos_validate as validator


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.app = self.root / 'Client.app'
        self.main = self.app / 'Contents/MacOS/client'
        self.main.parent.mkdir(parents=True)
        self.main.write_bytes(bytes.fromhex('cffaedfe') + b'fixture')
        self.plist = self.app / 'Contents/Info.plist'
        self.plist.write_bytes(plistlib.dumps({'CFBundleExecutable': 'client', 'LSMinimumSystemVersion': '14.0'}))
        self.deps = self.root / 'approved'
        self.deps.mkdir()

    def test_copies_without_mutating_or_linking_source(self):
        library = self.deps / 'libfixture.dylib'
        library.write_bytes(b'original source bytes')
        mover = relocation.Relocator(self.app, [self.deps])
        target = mover.include(library)
        self.assertEqual(target.read_bytes(), library.read_bytes())
        self.assertNotEqual(target.stat().st_ino, library.stat().st_ino)
        target.write_bytes(b'candidate-only change')
        self.assertEqual(library.read_bytes(), b'original source bytes')

    def test_rejects_dependency_outside_approved_roots(self):
        library = self.root / 'unapproved.dylib'
        library.write_bytes(b'fixture')
        with self.assertRaisesRegex(ValueError, 'outside approved roots'):
            relocation.Relocator(self.app, [self.deps]).include(library)

    def predeployed_library_fixture(self):
        source = self.deps / 'lib/libbrotlidec.1.dylib'
        child = source.parent / 'libbrotlicommon.1.dylib'
        source.parent.mkdir()
        for image in (source, child):
            image.write_bytes(bytes.fromhex('cffaedfe') + b'approved source fixture')
        staged = self.app / 'Contents/Frameworks/libbrotlidec.1.dylib'
        staged.parent.mkdir()
        staged.write_bytes(bytes.fromhex('cffaedfe') + b'macdeployqt edited fixture')
        commands = ('cmd LC_UUID\n uuid 43EB690D-1071-35E5-A6B2-9A5005643EA0\n'
                    'cmd LC_LOAD_DYLIB\n name @rpath/libbrotlicommon.1.dylib (offset 24)\n'
                    'cmd LC_RPATH\n path @loader_path/../lib (offset 12)\n')
        return source, child, staged, commands

    def test_predeployed_library_recovers_uuid_matched_source_for_transitive_rpath(self):
        source, child, staged, commands = self.predeployed_library_fixture()
        original_source = source.read_bytes()
        mover = relocation.Relocator(self.app, [self.deps])
        self.assertNotIn(staged, mover.origins)
        with patch('macos_relocate.inspect', return_value=commands):
            target = mover.dependency('@rpath/libbrotlicommon.1.dylib', staged, ['@loader_path/../lib'])
        self.assertEqual(target, staged.parent / child.name)
        self.assertEqual(target.read_bytes(), child.read_bytes())
        self.assertEqual(source.read_bytes(), original_source)
        self.assertEqual(mover.origins[staged], source)

    def test_predeployed_library_rejects_different_source_uuid(self):
        source, child, staged, commands = self.predeployed_library_fixture()
        different = commands.replace('43EB690D-1071-35E5-A6B2-9A5005643EA0', '11111111-1111-1111-1111-111111111111')
        with patch('macos_relocate.inspect', side_effect=lambda path: commands if path == staged else different):
            with self.assertRaisesRegex(ValueError, 'unresolved relocation input'):
                relocation.Relocator(self.app, [self.deps]).dependency('@rpath/' + child.name, staged, [])
        self.assertFalse((staged.parent / child.name).exists())

    def test_predeployed_library_rejects_ambiguous_uuid_matched_sources(self):
        source, child, staged, commands = self.predeployed_library_fixture()
        alternate = self.root / 'second-approved'
        (alternate / 'lib').mkdir(parents=True)
        shutil.copy2(source, alternate / 'lib' / source.name)
        with patch('macos_relocate.inspect', return_value=commands):
            with self.assertRaisesRegex(ValueError, 'ambiguous approved source'):
                relocation.Relocator(self.app, [self.deps, alternate]).dependency('@rpath/' + child.name, staged, [])
        self.assertFalse((staged.parent / child.name).exists())

    def test_predeployed_library_still_rejects_transitive_source_outside_approved_roots(self):
        source, child, staged, commands = self.predeployed_library_fixture()
        outside = self.root / child.name
        child.rename(outside)
        child.symlink_to(outside)
        with patch('macos_relocate.inspect', return_value=commands):
            with self.assertRaisesRegex(ValueError, 'outside approved roots'):
                relocation.Relocator(self.app, [self.deps]).dependency('@rpath/' + child.name, staged, [])
        self.assertFalse((staged.parent / child.name).exists())

    def test_rejects_distinct_libraries_with_same_target_name(self):
        first = self.deps / 'a/libfoo.dylib'
        second = self.deps / 'b/libfoo.dylib'
        for path in (first, second):
            path.parent.mkdir()
            path.write_bytes(path.parent.name.encode())
        mover = relocation.Relocator(self.app, [self.deps])
        mover.include(first)
        with patch('macos_relocate.identity', side_effect=[{'uuid-b'}, {'uuid-a'}]):
            with self.assertRaisesRegex(ValueError, 'conflicting dependency target'):
                mover.include(second)

    def test_rejects_framework_symlink_escape_before_copy(self):
        framework = self.deps / 'QtFixture.framework'
        framework.mkdir()
        image = framework / 'QtFixture'
        image.write_bytes(b'fixture')
        (framework / 'outside').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'source symlink'):
            relocation.Relocator(self.app, [self.deps]).include(image)
        self.assertFalse((self.app / 'Contents/Frameworks/QtFixture.framework').exists())

    def framework_fixture(self):
        framework = self.deps / 'QtFixture.framework'
        version = framework / 'Versions/A'
        resources = version / 'Resources'
        resources.mkdir(parents=True)
        (version / 'QtFixture').write_bytes(bytes.fromhex('cffaedfe') + b'fixture')
        (resources / 'required.dat').write_bytes(b'required runtime data')
        (resources / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleName': 'QtFixture'}))
        (resources / 'QtFixture.prl').write_text('development linkage metadata')
        (version / 'QtFixture_debug').write_bytes(b'development debug binary')
        (framework / 'Versions/Resources').mkdir()
        for name in ('Headers', 'Modules', '_CodeSignature'):
            (version / name).mkdir()
            (version / name / 'fixture').write_bytes(b'development or signing data')
        (framework / 'Versions/Current').symlink_to('A', target_is_directory=True)
        (framework / 'QtFixture').symlink_to('Versions/Current/QtFixture')
        (framework / 'Resources').symlink_to('Versions/Current/Resources', target_is_directory=True)
        destination = self.app / 'Contents/Frameworks/QtFixture.framework'
        destination.parent.mkdir()
        shutil.copytree(framework, destination, symlinks=True)
        return framework, destination

    def test_framework_reuse_rejects_missing_runtime_resources(self):
        source, destination = self.framework_fixture()
        (destination / 'Versions/A/Resources/required.dat').unlink()
        with patch('macos_relocate.identity', return_value={'same-uuid'}):
            with self.assertRaisesRegex(ValueError, 'incomplete framework runtime resource'):
                relocation.Relocator(self.app, [self.deps]).include(source / 'QtFixture')
        self.assertTrue((source / 'Versions/A/Resources/required.dat').is_file())
        self.assertFalse((destination / 'Versions/A/Resources/required.dat').exists())

    def test_framework_reuse_accepts_deployment_stripped_sdk_content(self):
        source, destination = self.framework_fixture()
        for name in ('Headers', 'Modules', '_CodeSignature'):
            shutil.rmtree(destination / 'Versions/A' / name)
        (destination / 'Versions/A/Resources/QtFixture.prl').unlink()
        (destination / 'Versions/A/QtFixture_debug').unlink()
        (destination / 'Versions/Resources').rmdir()
        with patch('macos_relocate.identity', return_value={'same-uuid'}):
            target = relocation.Relocator(self.app, [self.deps]).include(source / 'QtFixture')
        self.assertEqual(target, (destination / 'Versions/A/QtFixture').resolve())
        self.assertTrue((destination / 'Resources/required.dat').is_file())
        self.assertFalse((destination / 'Versions/A/Headers').exists())

    def vulkan_fixture(self):
        frameworks = self.app / 'Contents/Frameworks'
        frameworks.mkdir()
        loader = frameworks / 'libvulkan.1.dylib'
        driver = frameworks / 'libMoltenVK.dylib'
        directory = self.app / 'Contents/Resources/vulkan/icd.d'
        directory.mkdir(parents=True)
        (directory / 'MoltenVK_icd.json').write_text(json.dumps({
            'ICD': {'library_path': '../../../Frameworks/libMoltenVK.dylib'}}))
        metadata = {}
        for image in (self.main, loader, driver):
            image.write_bytes(bytes.fromhex('cffaedfe') + b'fixture')
            metadata[image] = {arch: {'dependencies': ['/usr/lib/libSystem.B.dylib'], 'rpaths': []}
                               for arch in ('arm64', 'x86_64')}
        return loader, driver, metadata

    def test_vulkan_rejects_non_macho_loader_and_driver(self):
        loader, driver, metadata = self.vulkan_fixture()
        for image in (loader, driver):
            with self.subTest(image=image.name):
                original = image.read_bytes()
                image.write_text('malicious non-Mach-O payload')
                with self.assertRaisesRegex(ValueError, 'Vulkan runtime is not an inventoried Mach-O'):
                    validator.validate(self.app, metadata.__getitem__)
                image.write_bytes(original)

    def test_vulkan_requires_every_main_executable_slice(self):
        loader, driver, metadata = self.vulkan_fixture()
        for image in (loader, driver):
            with self.subTest(image=image.name):
                original = metadata[image].pop('x86_64')
                with self.assertRaisesRegex(ValueError, 'missing Mach-O architecture x86_64'):
                    validator.validate(self.app, metadata.__getitem__)
                metadata[image]['x86_64'] = original

    def test_vulkan_validates_dependencies_for_each_runtime_slice(self):
        loader, driver, metadata = self.vulkan_fixture()
        for image in (loader, driver):
            with self.subTest(image=image.name):
                dependencies = metadata[image]['x86_64']['dependencies']
                metadata[image]['x86_64']['dependencies'] = ['/private/malicious.dylib']
                with self.assertRaisesRegex(ValueError, 'absolute non-system dependency'):
                    validator.validate(self.app, metadata.__getitem__)
                metadata[image]['x86_64']['dependencies'] = dependencies

    def test_vulkan_accepts_complete_universal_runtime(self):
        loader, driver, metadata = self.vulkan_fixture()
        report = validator.validate(self.app, metadata.__getitem__)
        self.assertEqual(report['mach_o_images'], 3)
        runtime_loads = {(row['image'], row['architecture']) for row in report['loads']
                         if row['image'].startswith('Contents/Frameworks/')}
        self.assertEqual(runtime_loads, {(str(image.relative_to(self.app)), arch)
                                        for image in (loader, driver) for arch in ('arm64', 'x86_64')})

    def test_rejects_private_runtime_environment(self):
        self.plist.write_bytes(plistlib.dumps({'CFBundleExecutable': 'client',
                                             'LSEnvironment': {'QT_VULKAN_LIB': '/opt/homebrew/lib/libvulkan.dylib'}}))
        with self.assertRaisesRegex(ValueError, 'runtime environment'):
            validator.validate_runtime_config(self.app)

    def test_rejects_absolute_or_escaping_vulkan_driver(self):
        directory = self.app / 'Contents/Resources/vulkan/icd.d'
        directory.mkdir(parents=True)
        icd = directory / 'MoltenVK_icd.json'
        for path in ('/private/libMoltenVK.dylib', '../../../../../../libMoltenVK.dylib'):
            icd.write_text(json.dumps({'ICD': {'library_path': path}}))
            with self.assertRaisesRegex(ValueError, 'Vulkan ICD'):
                validator.validate_runtime_config(self.app)

    def test_minimum_os_rejects_dependency_above_declaration(self):
        info = {'arm64': {'dependencies': [], 'rpaths': [], 'minimum_os': '26.0'}}
        with self.assertRaisesRegex(ValueError, 'minimum OS exceeds'):
            validator.validate(self.app, lambda _: info, require_release_metadata=True)

    def test_minimum_os_accepts_equal_and_rejects_unknown(self):
        info = {'arm64': {'dependencies': [], 'rpaths': [], 'minimum_os': '14.0'}}
        self.assertEqual(validator.validate(self.app, lambda _: info, True)['minimum_system_version'], '14.0')
        del info['arm64']['minimum_os']
        with self.assertRaisesRegex(ValueError, 'invalid minimum'):
            validator.validate(self.app, lambda _: info, True)

    def test_reads_modern_and_legacy_minimum_os(self):
        for command, key in (('LC_BUILD_VERSION', 'minos'), ('LC_VERSION_MIN_MACOSX', 'version')):
            result = validator.parse_load_commands(f'cmd {command}\n {key} 26.0\n')
            self.assertEqual(result['native']['minimum_os'], '26.0')


if __name__ == '__main__':
    unittest.main()
