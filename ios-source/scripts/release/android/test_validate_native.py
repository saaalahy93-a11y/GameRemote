#!/usr/bin/env python3
"""Behavioral fixtures for native page-size rejection checks."""
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from validate_native import validate_bundle_config, validate_elf


def elf(alignment=16384, offset=0, address=0, relro_end=16384, file_size=176, memory_size=16384):
    data = bytearray(64 + 2 * 56)
    data[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<I', data, 20, 1)
    struct.pack_into('<H', data, 52, 64)
    struct.pack_into('<Q', data, 32, 64)
    struct.pack_into('<HH', data, 54, 56, 2)
    struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, offset, address, 0, file_size, memory_size, alignment)
    struct.pack_into('<IIQQQQQQ', data, 120, 0x6474E552, 4, 0, 0, 0, 0, relro_end, 1)
    return data


class AlignmentTests(unittest.TestCase):
    def test_bundle_config_accepts_actual_native_alignment(self):
        validate_bundle_config(json.dumps({'optimizations': {'uncompressNativeLibraries': {
            'enabled': True, 'alignment': 'PAGE_ALIGNMENT_16K'}}}))

    def test_bundle_config_rejects_disabled_native_alignment(self):
        with self.assertRaisesRegex(ValueError, 'does not enable'):
            validate_bundle_config(json.dumps({'optimizations': {'uncompressNativeLibraries': {
                'enabled': False, 'alignment': 'PAGE_ALIGNMENT_16K'}}}))

    def test_bundle_config_rejects_unrelated_alignment_string(self):
        with self.assertRaisesRegex(ValueError, 'missing'):
            validate_bundle_config(json.dumps({'unrelated': 'PAGE_ALIGNMENT_16K'}))

    def run_aab(self, *options):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / 'fixture.aab'
            with zipfile.ZipFile(artifact, 'w') as archive:
                archive.writestr('base/lib/arm64-v8a/libfixture.so', elf())
            environment = os.environ.copy()
            environment.pop('BUNDLETOOL_JAR', None)
            return subprocess.run(
                [sys.executable, str(Path(__file__).with_name('validate_native.py')), str(artifact), *options],
                capture_output=True, text=True, env=environment,
            )

    def test_aab_requires_bundletool_by_default(self):
        result = self.run_aab()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('BUNDLETOOL_JAR is required', result.stderr)

    def test_aab_elf_only_is_explicitly_partial(self):
        result = self.run_aab('--elf-only')
        self.assertEqual(result.returncode, 0)
        self.assertIn('PARTIAL AAB validation', result.stdout)

    def test_accepts_aligned_load_and_relro(self):
        validate_elf(elf())

    def test_rejects_out_of_bounds_segment(self):
        with self.assertRaisesRegex(ValueError, 'file range'):
            validate_elf(elf(offset=16384, address=16384, file_size=4096))

    def test_rejects_file_size_larger_than_memory(self):
        with self.assertRaisesRegex(ValueError, 'memory size'):
            validate_elf(elf(memory_size=100))

    def test_rejects_truncated_64bit_header(self):
        with self.assertRaisesRegex(ValueError, 'truncated ELF header'):
            validate_elf(elf()[:52])

    def test_rejects_4k_load(self):
        with self.assertRaisesRegex(ValueError, 'alignment'):
            validate_elf(elf(alignment=4096))

    def test_rejects_incongruent_load(self):
        with self.assertRaisesRegex(ValueError, 'congruent'):
            validate_elf(elf(address=4096))

    def test_rejects_4k_relro_end(self):
        with self.assertRaisesRegex(ValueError, 'GNU_RELRO'):
            validate_elf(elf(relro_end=4096))

    def test_rejects_malformed_headers(self):
        with self.assertRaisesRegex(ValueError, 'header'):
            validate_elf(elf()[:64])


if __name__ == '__main__':
    unittest.main()
