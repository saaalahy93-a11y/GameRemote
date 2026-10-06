#!/usr/bin/env python3
"""Small real Mach-O fixtures for the validator; never launches an executable."""
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

from macos_validate import validate


def main():
    if sys.platform != 'darwin':
        raise RuntimeError('native Mach-O fixture check requires macOS and Xcode command-line tools')
    with tempfile.TemporaryDirectory(prefix='desktop-native-packaging-') as directory:
        root = Path(directory).resolve()
        app = root / 'Fixture.app'
        (app / 'Contents/MacOS').mkdir(parents=True)
        (app / 'Contents/Frameworks').mkdir()
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'client'}))
        library_source = root / 'library.c'
        library_source.write_text('int fixture(void) { return 0; }\n')
        main_source = root / 'main.c'
        main_source.write_text('extern int fixture(void); int main(void) { return fixture(); }\n')
        library = app / 'Contents/Frameworks/libfixture.dylib'
        executable = app / 'Contents/MacOS/client'
        subprocess.run(['cc', '-dynamiclib', str(library_source), '-Wl,-install_name,@rpath/libfixture.dylib', '-o', str(library)], check=True)
        subprocess.run(['cc', str(main_source), str(library), '-Wl,-rpath,@executable_path/../Frameworks', '-o', str(executable)], check=True)
        report = validate(app)
        if report['mach_o_images'] != 2 or not any(x['resolved'] == 'Contents/Frameworks/libfixture.dylib' for x in report['loads']):
            raise AssertionError('real Mach-O dependency graph not established')
        subprocess.run(['install_name_tool', '-change', '@rpath/libfixture.dylib', '/private/not-shipped/libfixture.dylib', str(executable)], check=True)
        try:
            validate(app)
        except ValueError as error:
            if 'absolute non-system dependency' not in str(error):
                raise
        else:
            raise AssertionError('private native dependency was accepted')
        print('PASS: native lipo/otool graph resolves bundled dylib and rejects private load; no executable launched')


if __name__ == '__main__':
    main()
