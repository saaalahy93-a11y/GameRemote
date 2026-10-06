#!/usr/bin/env python3
"""Check every packaged ELF library; APK ZIP alignment is checked by zipalign."""
import argparse
import json
import os
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

PAGE_SIZE = 16384


def validate_elf(data):
    if data[:4] != b'\x7fELF' or len(data) < 52:
        raise ValueError('not an ELF library')
    elf_class, byte_order = data[4:6]
    if byte_order not in (1, 2) or elf_class not in (1, 2):
        raise ValueError('unsupported ELF format')
    header_size = 64 if elf_class == 2 else 52
    if len(data) < header_size:
        raise ValueError('truncated ELF header')
    endian = '<' if byte_order == 1 else '>'
    actual_header_size = struct.unpack_from(endian + 'H', data, 52 if elf_class == 2 else 40)[0]
    if actual_header_size != header_size or data[6] != 1 or struct.unpack_from(endian + 'I', data, 20)[0] != 1:
        raise ValueError('invalid ELF header size or version')
    if elf_class == 2:
        phoff = struct.unpack_from(endian + 'Q', data, 32)[0]
        entry_size, count = struct.unpack_from(endian + 'HH', data, 54)
        fmt = endian + 'IIQQQQQQ'
    else:
        phoff = struct.unpack_from(endian + 'I', data, 28)[0]
        entry_size, count = struct.unpack_from(endian + 'HH', data, 42)
        fmt = endian + 'IIIIIIII'
    if count == 0 or phoff < header_size or entry_size < struct.calcsize(fmt) or phoff + entry_size * count > len(data):
        raise ValueError('invalid program header table')
    loads = 0
    for index in range(count):
        header = struct.unpack_from(fmt, data, phoff + index * entry_size)
        if elf_class == 2:
            kind, _, offset, address, _, file_size, memory_size, alignment = header
        else:
            kind, offset, address, _, file_size, memory_size, _, alignment = header
        if kind == 1:  # PT_LOAD
            loads += 1
            if offset + file_size > len(data):
                raise ValueError(f'LOAD segment {index} file range exceeds ELF size')
            if file_size > memory_size:
                raise ValueError(f'LOAD segment {index} file size exceeds memory size')
            if alignment < PAGE_SIZE or alignment & (alignment - 1):
                raise ValueError(f'LOAD segment {index} alignment {alignment} is below 16 KB or invalid')
            if (address - offset) % PAGE_SIZE:
                raise ValueError(f'LOAD segment {index} offset/address are not congruent at 16 KB')
        if kind == 0x6474E552 and (address + memory_size) % PAGE_SIZE:  # PT_GNU_RELRO
            raise ValueError(f'GNU_RELRO segment {index} end is not 16 KB aligned')
    if not loads:
        raise ValueError('no LOAD segments')


def validate_bundle_config(config):
    try:
        native = json.loads(config)['optimizations']['uncompressNativeLibraries']
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError('invalid or missing bundletool native packaging configuration') from error
    if not isinstance(native, dict):
        raise ValueError('invalid bundletool native packaging configuration')
    if native.get('enabled') is not True or native.get('alignment') != 'PAGE_ALIGNMENT_16K':
        raise ValueError('bundletool config does not enable uncompressed PAGE_ALIGNMENT_16K libraries')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--elf-only', action='store_true', help='Explicit partial AAB validation without packaging checks')
    parser.add_argument('--bundletool', type=Path, default=os.environ.get('BUNDLETOOL_JAR'))
    parser.add_argument('--sdk', type=Path, default=os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT'))
    args = parser.parse_args()
    failures = []
    with zipfile.ZipFile(args.artifact) as archive:
        libraries = [entry for entry in archive.infolist() if entry.filename.endswith('.so')]
        if not libraries:
            raise ValueError('artifact contains no native libraries')
        for entry in libraries:
            try:
                validate_elf(archive.read(entry))
                print(f'PASS ELF 16 KB: {entry.filename}')
            except (ValueError, struct.error) as error:
                failures.append(f'{entry.filename}: {error}')
    if failures:
        raise ValueError('\n'.join(failures))
    if args.artifact.suffix == '.apk':
        if args.sdk is None:
            raise ValueError('ANDROID_HOME or --sdk is required for APK ZIP alignment')
        zipalign = args.sdk / 'build-tools' / '36.0.0' / 'zipalign'
        if not zipalign.is_file():
            raise ValueError('SDK build-tools 36.0.0 zipalign is missing')
        subprocess.run([str(zipalign), '-c', '-P', '16', '4', str(args.artifact)], check=True)
        print('PASS APK ZIP 16 KB alignment')
    elif args.artifact.suffix == '.aab':
        if args.elf_only:
            print('PARTIAL AAB validation: ELF only; packaging checks deliberately skipped')
        elif args.bundletool is not None:
            config = subprocess.run(
                [str(Path(os.environ['JAVA_HOME']) / 'bin' / 'java') if os.environ.get('JAVA_HOME') else 'java', '-jar', str(args.bundletool), 'dump', 'config', '--bundle=' + str(args.artifact)],
                check=True, capture_output=True, text=True,
            ).stdout
            validate_bundle_config(config)
            print('PASS AAB bundletool PAGE_ALIGNMENT_16K configuration')
        else:
            raise ValueError('BUNDLETOOL_JAR is required for AAB packaging validation (or explicitly use --elf-only)')
        print('Generated APKs and 16 KB runtime remain required before distribution')
    else:
        raise ValueError('expected .apk or .aab')
    print(f'Checked all {len(libraries)} packaged native libraries')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(1)
