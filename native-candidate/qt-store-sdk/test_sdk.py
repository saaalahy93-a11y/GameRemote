"""Vulkan SDK input and command contracts; no native build or GPU execution."""

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_sdk as build_macos
import sdk_common as common


class VulkanSdkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.evidence = self.work / 'evidence'
        self.evidence.mkdir()

    def archive(self, names=None):
        archive = self.work / 'downloads/headers.tar.gz'
        archive.parent.mkdir(exist_ok=True)
        with tarfile.open(archive, 'w:gz') as output:
            for name in names or ['vulkan.h', 'vulkan_core.h', 'vk_platform.h']:
                path = tarfile.TarInfo('Vulkan-Headers-fixture/include/vulkan/' + name)
                data = b'explicitly synthetic header fixture'
                path.size = len(data)
                output.addfile(path, io.BytesIO(data))
        return {'version': 'fixture', 'url': 'https://example.invalid/headers.tar.gz',
                'filename': archive.name, 'sha256': common.digest(archive)}

    def moltenvk_archive(self, kind='file'):
        archive = self.work / 'downloads/MoltenVK-fixture.tar.gz'
        archive.parent.mkdir(exist_ok=True)
        with tarfile.open(archive, 'w:gz') as output:
            name = 'mvk_vulkan.h' if kind != 'missing' else 'another.h'
            member = tarfile.TarInfo('MoltenVK-fixture/MoltenVK/MoltenVK/API/' + name)
            if kind == 'symlink':
                member.type = tarfile.SYMTYPE
                member.linkname = '/unrelated/header'
                output.addfile(member)
            else:
                data = b'/* explicitly synthetic MoltenVK header fixture */'
                member.size = len(data)
                output.addfile(member, io.BytesIO(data))
        return {'version': 'fixture', 'url': 'https://example.invalid/MoltenVK-fixture.tar.gz',
                'filename': archive.name, 'sha256': common.digest(archive)}

    def test_macos_headers_bind_moltenvk_source_without_modifying_khronos_tree(self):
        vulkan = build_macos.prepare_vulkan_headers(self.archive(), self.work, self.evidence)
        spec = self.moltenvk_archive()
        with patch.object(common.urllib.request, 'urlopen', side_effect=AssertionError('network forbidden')):
            include = build_macos.prepare_macos_vulkan_headers(vulkan, spec, self.work, self.evidence)
        self.assertFalse((vulkan / 'MoltenVK').exists())
        self.assertEqual((include / 'vulkan/vulkan.h').read_bytes(), (vulkan / 'vulkan/vulkan.h').read_bytes())
        record = json.loads((self.evidence / 'moltenvk-headers.json').read_text())
        self.assertEqual(record['archive_sha256'], spec['sha256'])
        self.assertEqual(record['source_member'], 'MoltenVK-fixture/MoltenVK/MoltenVK/API/mvk_vulkan.h')
        self.assertEqual(record['header_sha256'], common.digest(include / record['header']))
        with self.assertRaisesRegex(ValueError, 'cached'):
            build_macos.prepare_macos_vulkan_headers(vulkan, {**spec, 'sha256': '0' * 64}, self.work, self.evidence)

    def test_macos_headers_reject_missing_and_non_regular_wrapper(self):
        vulkan = build_macos.prepare_vulkan_headers(self.archive(), self.work, self.evidence)
        for kind, message in (('missing', 'missing mvk_vulkan.h'), ('symlink', 'bounded regular file')):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, message):
                build_macos.prepare_macos_vulkan_headers(vulkan, self.moltenvk_archive(kind), self.work, self.evidence)
            self.assertFalse((self.work / 'macos-vulkan-include').exists())

    def test_recipe_rejects_khronos_only_headers_before_xcode_or_compilation(self):
        vulkan = build_macos.prepare_vulkan_headers(self.archive(), self.work, self.evidence)
        environment = dict(os.environ, QT_CMAKE_TOOL_BIN=str(self.work / 'unused-tools'),
                           QT_VULKAN_INCLUDE_DIR=str(vulkan))
        result = subprocess.run(['bash', str(ROOT / 'build-qt693.sh'), 'configure'],
                                env=environment, capture_output=True, text=True, timeout=10, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Qt Cocoa requires verified MoltenVK/mvk_vulkan.h', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_header_compile_failure_stops_before_any_qt_build_phase(self):
        lock = {'macos': {'developer_dir': '/fixture/Xcode', 'xcode': '16.4', 'sdk': '15.5',
                          'vulkan_headers': {}, 'moltenvk_headers': {}}}
        with (patch.dict(os.environ, {}, clear=False),
              patch.object(build_macos, 'read_lock', return_value=lock),
              patch.object(build_macos, 'tools_for', return_value={}),
              patch.object(build_macos, 'prepare_vulkan_headers', return_value=self.work / 'khronos'),
              patch.object(build_macos, 'prepare_macos_vulkan_headers', return_value=self.work / 'combined'),
              patch.object(build_macos.subprocess, 'check_output', side_effect=['Xcode 16.4\nBuild fixture', '15.5']),
              patch.object(build_macos, 'run', side_effect=RuntimeError('header compile fixture failure')) as run,
              self.assertRaisesRegex(RuntimeError, 'header compile fixture failure')):
            build_macos.build(self.work, self.evidence)
        run.assert_called_once()
        self.assertIn('-fsyntax-only', run.call_args.args[0])
        self.assertFalse((self.work / 'qt-store-sdk').exists())

    def test_exact_cached_archive_is_verified_and_its_headers_are_recorded(self):
        spec = self.archive()
        with patch.object(common.urllib.request, 'urlopen', side_effect=AssertionError('network forbidden')):
            include = build_macos.prepare_vulkan_headers(spec, self.work, self.evidence)
        record = json.loads((self.evidence / 'vulkan-headers.json').read_text())
        self.assertEqual(record['archive_sha256'], spec['sha256'])
        self.assertEqual(record['include'], str(include))
        self.assertEqual(len(record['headers']), 3)
        for row in record['headers']:
            self.assertEqual(row['sha256'], common.digest(include / row['path']))

    def test_bad_pin_and_incomplete_headers_fail_before_recipe_use(self):
        spec = self.archive(['vulkan.h'])
        with self.assertRaisesRegex(ValueError, 'cached'):
            build_macos.prepare_vulkan_headers({**spec, 'sha256': '0' * 64}, self.work, self.evidence)
        with self.assertRaises(FileNotFoundError):
            build_macos.prepare_vulkan_headers(spec, self.work, self.evidence)
        self.assertFalse((self.evidence / 'vulkan-headers.json').exists())

    def test_public_download_cap_removes_partial_and_never_installs_oversized_bytes(self):
        data = b'fixture' * 32
        spec = {'filename': 'oversized.tar.gz', 'url': 'https://example.invalid/oversized.tar.gz',
                'sha256': hashlib.sha256(data).hexdigest()}
        downloads = self.work / 'downloads'
        with (patch.object(common, 'MAX_DOWNLOAD_BYTES', 64),
              patch.object(common.urllib.request, 'urlopen', return_value=io.BytesIO(data)),
              self.assertRaisesRegex(ValueError, 'download exceeds')):
            common.fetch(spec, downloads)
        self.assertEqual(list(downloads.iterdir()), [])

    def test_recipe_rejects_missing_header_input_before_xcode_or_compilation(self):
        environment = dict(os.environ)
        environment['QT_CMAKE_TOOL_BIN'] = str(self.work / 'unused-tools')
        environment.pop('QT_VULKAN_INCLUDE_DIR', None)
        result = subprocess.run(['bash', str(ROOT / 'build-qt693.sh'), 'configure'],
                                env=environment, capture_output=True, text=True, timeout=10, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('QT_VULKAN_INCLUDE_DIR must select checksum-verified', result.stderr)
        self.assertNotIn('xcode-select', result.stderr)

    def test_native_driver_passes_verified_headers_to_build_and_relocation_probe(self):
        spec = self.archive()
        lock = {'macos': {'developer_dir': '/fixture/Xcode', 'xcode': '16.4',
                          'sdk': '15.5', 'vulkan_headers': spec, 'moltenvk_headers': self.moltenvk_archive()}}
        tools = {'cmake': self.work / 'tools/cmake', 'ninja': self.work / 'tools/ninja'}
        recipe = self.work / 'qt-store-sdk'
        calls = []

        def run(command, **kwargs):
            calls.append(list(map(str, command)))
            if '-fsyntax-only' in command:
                include = Path(command[command.index('-I') + 1])
                self.assertTrue((include / 'MoltenVK/mvk_vulkan.h').is_file())
                self.assertEqual(kwargs['timeout'], 60)
                return
            include = Path(os.environ['QT_VULKAN_INCLUDE_DIR'])
            self.assertTrue((include / 'vulkan/vulkan.h').is_file())
            self.assertTrue((include / 'MoltenVK/mvk_vulkan.h').is_file())
            if command[-1] == 'build':
                (recipe / 'prefix/bin').mkdir(parents=True)
                (recipe / 'prefix/bin/qt-cmake').write_text('synthetic tool fixture')
                (recipe / 'build/probe').mkdir(parents=True)
                (recipe / 'build/qtbase').mkdir()
                (recipe / 'build/probe/gameremote-mac-app-store-qt.json').write_text('{}')
                (recipe / 'build/qtbase/CMakeCache.txt').write_text('synthetic cache')
            if str(command[0]).endswith('/qt-cmake'):
                self.assertIn('-DVulkan_INCLUDE_DIR=' + str(include), command)
                (self.work / 'relocation-probe').mkdir()
                (self.work / 'relocation-probe/gameremote-mac-app-store-qt.json').write_text('{}')

        with (patch.dict(os.environ, {}, clear=False),
              patch.object(build_macos, 'read_lock', return_value=lock),
              patch.object(build_macos, 'tools_for', return_value=tools),
              patch.object(build_macos.subprocess, 'check_output', side_effect=['Xcode 16.4\nBuild fixture', '15.5']),
              patch.object(build_macos, 'run', side_effect=run)):
            package = build_macos.build(self.work, self.evidence)
        self.assertTrue(package.is_file())
        self.assertTrue((self.evidence / 'vulkan-headers.json').is_file())
        self.assertIn('-fsyntax-only', calls[0])
        self.assertEqual([call[-1] for call in calls if call[0] == 'bash'],
                         ['preflight', 'download', 'sources', 'build'])
        self.assertTrue((self.evidence / 'macos-vulkan-header-check.json').is_file())
        self.assertTrue((self.evidence / 'relocated-qt-guard.json').is_file())

    def test_public_entry_point_records_reference_without_reading_app_source(self):
        work, output = self.work / 'sdk-work', self.work / 'sdk-output'
        reference = 'a' * 64

        def build(work, evidence):
            self.assertFalse((ROOT / 'source.tar.gz').exists())
            package = work / 'synthetic-sdk.tar.gz'
            package.write_bytes(b'SYNTHETIC SDK packaging fixture; no native proof')
            return package

        def package_kit(package, sdk_work, sdk_output):
            self.assertEqual(package, work / 'synthetic-sdk.tar.gz')
            self.assertEqual((sdk_work, sdk_output), (work, output))
            self.assertFalse((output / 'packages').exists())
            manifest = output / 'distribution.json'
            common.write_json(manifest, {'sdk': {'file': 'packages/' + package.name,
                                                 'sha256': common.digest(package)}})
            return {'file': manifest.name, 'sha256': common.digest(manifest)}

        with (patch.object(build_macos.platform, 'system', return_value='Darwin'),
              patch.object(build_macos.platform, 'machine', return_value='arm64'),
              patch.object(build_macos, 'build', side_effect=build),
              patch.object(build_macos, 'assemble_distribution', side_effect=package_kit) as assemble):
            self.assertEqual(build_macos.main(['--work', str(work), '--output', str(output),
                                              '--app-source-reference-sha256', reference]), 0)
        record = json.loads((output / 'evidence/candidate.json').read_text())
        self.assertNotIn('source', record)
        self.assertEqual(record['scope'], 'qt-sdk-only')
        self.assertEqual(record['app_source_reference'],
                         {'sha256': reference, 'archive_read': False, 'application_built': False})
        self.assertEqual(record['sha256'], common.digest(output / 'packages/synthetic-sdk.tar.gz'))
        assemble.assert_called_once_with(work / 'synthetic-sdk.tar.gz', work, output)
        manifest = output / record['distribution']['file']
        self.assertEqual(record['distribution']['sha256'], common.digest(manifest))
        sdk = json.loads(manifest.read_text())['sdk']
        self.assertEqual(sdk['sha256'], common.digest(output / sdk['file']))
        self.assertFalse((work / 'synthetic-sdk.tar.gz').exists())

    def test_public_entry_point_retains_failed_sdk_evidence(self):
        output = self.work / 'failed-output'
        with (patch.object(build_macos.platform, 'system', return_value='Darwin'),
              patch.object(build_macos.platform, 'machine', return_value='arm64'),
              patch.object(build_macos, 'build', side_effect=RuntimeError('synthetic SDK failure')),
              self.assertRaisesRegex(RuntimeError, 'synthetic SDK failure')):
            build_macos.main(['--work', str(self.work / 'failed-work'), '--output', str(output),
                              '--app-source-reference-sha256', 'a' * 64])
        record = json.loads((output / 'evidence/candidate.json').read_text())
        self.assertEqual(record['status'], 'FAILED')
        self.assertFalse(record['app_source_reference']['archive_read'])

    def test_public_entry_point_rejects_bad_reference_and_existing_output_before_build(self):
        output = self.work / 'existing-output'
        output.mkdir()
        sentinel = output / 'preserved.txt'
        sentinel.write_text('existing evidence')
        arguments = ['--work', str(self.work / 'new-work'), '--output', str(output),
                     '--app-source-reference-sha256']
        with (patch.object(build_macos.platform, 'system', return_value='Darwin'),
              patch.object(build_macos.platform, 'machine', return_value='arm64'),
              patch.object(build_macos, 'build') as native):
            with self.assertRaisesRegex(ValueError, 'lowercase SHA-256'):
                build_macos.main(arguments + ['not-a-reference'])
            with self.assertRaisesRegex(ValueError, 'fresh, separate directories'):
                build_macos.main(arguments + ['a' * 64])
            native.assert_not_called()
        self.assertEqual(sentinel.read_text(), 'existing evidence')


if __name__ == '__main__':
    unittest.main()
