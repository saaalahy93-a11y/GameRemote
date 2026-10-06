"""Small synthetic distribution fixtures; no native build, network or GPU work."""

import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_sdk
import sdk_distribution as distribution
from sdk_common import digest


def archive(path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 'w:xz' if path.name.endswith('.xz') else 'w:gz'
    with tarfile.open(path, mode) as output:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.work, self.output, self.recipe = [self.root / name for name in ('work', 'output', 'recipe')]
        self.output.mkdir()
        for name in distribution.RECIPE_FILES:
            file = self.recipe / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('synthetic recipe fixture\n')
        self.workflow = self.root / 'workflow.yml'
        self.workflow.write_text('synthetic workflow fixture\n')
        self.sources = []
        pins = []
        for module in distribution.QT_MODULES:
            path = self.work / 'qt-store-sdk/downloads' / (module + '-everywhere-src-6.9.3.tar.xz')
            archive(path, {module + '/LICENSES/LGPL-3.0-only.txt': b'synthetic licence bytes',
                           module + '/vendor/qt_attributions.json':
                           b'{"Description":"literal\nnewline", "LicenseFile":"terms.txt"}',
                           module + '/vendor/terms.txt': b'exact referenced terms'})
            pins.append(digest(path) + '  ' + path.name)
            self.sources.append(path)
        (self.recipe / 'SHA256SUMS').write_text('\n'.join(pins) + '\n')
        vulkan = self.work / 'downloads/Vulkan-Headers-fixture.tar.gz'
        archive(vulkan, {'headers/LICENSE.md': b'synthetic Vulkan notice'})
        self.sources.append(vulkan)
        self.lock = {'macos': {'vulkan_headers': {
            'version': 'fixture', 'url': 'https://example.invalid/headers.tar.gz',
            'filename': vulkan.name, 'sha256': digest(vulkan)}}}
        (self.recipe / 'dependencies.lock.json').write_text(json.dumps(self.lock))
        self.prefix = self.work / 'relocated/Qt-6.9.3-appstore-arm64'
        binary = self.prefix / 'lib/fixture.dylib'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(bytes.fromhex('cffaedfe') + b'explicitly synthetic Mach-O fixture')
        self.package = self.output / 'packages/sdk.tar.gz'
        archive(self.package, {self.prefix.name + '/lib/fixture.dylib': binary.read_bytes()})

    def test_complete_kit_binds_sources_notices_recipe_and_actual_archive_inventory(self):
        metadata = {'architectures': ['arm64'], 'imports': ['/usr/lib/libSystem.B.dylib'],
                    'non_system_absolute_imports': []}
        with patch.object(distribution, 'inspect_macho', return_value=metadata) as inspect:
            summary = distribution.assemble_distribution(self.package, self.work, self.output,
                                                        self.recipe, self.workflow)
        inspect.assert_called_once_with(self.prefix / 'lib/fixture.dylib')
        result = json.loads((self.output / summary['file']).read_text())
        self.assertEqual(summary['sha256'], digest(self.output / summary['file']))
        self.assertEqual(summary['source_archives'], 5)
        self.assertEqual(summary['notice_records'], 13)
        self.assertFalse(result['private_app_source_included'])
        for section in ('sdk', 'sdk_inventory', 'readme', 'recipe'):
            self.assertEqual(result[section]['sha256'], digest(self.output / result[section]['file']))
        for row in result['sources']:
            self.assertEqual(row['sha256'], digest(self.output / row['file']))
            for notice in row['texts']:
                self.assertEqual(notice['sha256'], digest(self.output / notice['file']))
        self.assertEqual(len(list((self.output / 'notices').iterdir())), 4)
        inventory = json.loads((self.output / 'sdk-inventory.json').read_text())
        self.assertEqual(inventory['mach_o'][0]['sha256'], digest(self.prefix / 'lib/fixture.dylib'))
        with tarfile.open(self.output / 'recipe.tar.gz') as recipe_archive:
            self.assertIn('SDK-Recipe/.github/workflows/build-macos-store-sdk.yml', recipe_archive.getnames())
            for row in result['recipe']['files']:
                data = recipe_archive.extractfile(row['member']).read()
                self.assertEqual(distribution.hashlib.sha256(data).hexdigest(), row['sha256'])

    def test_changed_source_archive_is_rejected_before_copy(self):
        self.sources[0].write_bytes(b'changed upstream bytes')
        with self.assertRaisesRegex(ValueError, 'checksum changed: qtbase'):
            distribution.assemble_distribution(self.package, self.work, self.output,
                                               self.recipe, self.workflow)
        self.assertFalse((self.output / 'sources').exists())

    def test_absent_referenced_licence_fails_with_archive_evidence(self):
        broken = self.root / 'absent.tar.gz'
        archive(broken, {'module/qt_attributions.json': b'{"LicenseFile":"missing.txt"}'})
        with self.assertRaisesRegex(ValueError, 'module/qt_attributions.json: missing.txt'):
            distribution.collect_notices(broken, self.output / 'notices')
        self.assertFalse((self.output / 'notices').exists())

    def test_inventory_rejects_relocated_binary_that_differs_from_archive(self):
        (self.prefix / 'lib/fixture.dylib').write_bytes(b'changed relocated binary')
        with (patch.object(distribution, 'inspect_macho') as inspect,
              self.assertRaisesRegex(ValueError, 'differs from the packaged SDK')):
            distribution.sdk_inventory(self.package, self.prefix)
        inspect.assert_not_called()

    def test_entry_point_keeps_sdk_and_failed_receipt_if_source_kit_cannot_complete(self):
        work, output = self.root / 'driver-work', self.root / 'driver-output'

        def build(work, _evidence):
            result = work / 'sdk.tar.gz'
            result.write_bytes(b'explicitly synthetic completed SDK')
            return result

        with (patch.object(build_sdk.platform, 'system', return_value='Darwin'),
              patch.object(build_sdk.platform, 'machine', return_value='arm64'),
              patch.object(build_sdk, 'build', side_effect=build),
              patch.object(build_sdk, 'assemble_distribution', side_effect=ValueError('source kit fixture failure')),
              self.assertRaisesRegex(ValueError, 'source kit fixture failure')):
            build_sdk.main(['--work', str(work), '--output', str(output),
                            '--app-source-reference-sha256', 'a' * 64])
        record = json.loads((output / 'evidence/candidate.json').read_text())
        self.assertEqual(record['status'], 'FAILED')
        self.assertTrue(record['retained_incomplete_output'])
        self.assertTrue((work / 'sdk.tar.gz').is_file())
        self.assertFalse((output / 'packages').exists())
        self.assertEqual(list(output.rglob('sdk.tar.gz')), [])


if __name__ == '__main__':
    unittest.main()
