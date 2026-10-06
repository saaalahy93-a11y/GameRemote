#!/usr/bin/env python3
"""Real nested-app/transitive-library fixture; executes only generated test code."""
import hashlib
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

from macos_relocate import Relocator
from macos_validate import validate


def main():
    if sys.platform != 'darwin':
        raise RuntimeError('native relocation fixture requires macOS command-line tools')
    with tempfile.TemporaryDirectory(prefix='gameremote-relocation-') as directory:
        root = Path(directory).resolve()
        deps = root / 'dependencies'
        deps.mkdir()
        (deps / 'b.c').write_text('int b(void) { return 7; }\n')
        (deps / 'a.c').write_text('extern int b(void); int a(void) { return b(); }\n')
        (root / 'main.c').write_text('extern int a(void); int main(void) { return a() != 7; }\n')
        b, a = deps / 'libb.dylib', deps / 'liba.dylib'
        for source, target, links in ((deps / 'b.c', b, []), (deps / 'a.c', a, [str(b)])):
            subprocess.run(['cc', '-dynamiclib', str(source), *links,
                            '-Wl,-headerpad_max_install_names', '-Wl,-install_name,' + str(target),
                            '-o', str(target)], check=True)
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (a, b)}
        app = root / 'Client.app'
        helper = app / 'Contents/Frameworks/Helper.app'
        executables = []
        for bundle in (app, helper):
            binary = bundle / 'Contents/MacOS/client'
            binary.parent.mkdir(parents=True)
            (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps({
                'CFBundleExecutable': 'client', 'LSMinimumSystemVersion': '26.0'}))
            subprocess.run(['cc', str(root / 'main.c'), str(a), '-Wl,-headerpad_max_install_names',
                            '-o', str(binary)], check=True)
            executables.append(binary)
        report = Relocator(app, [deps]).run()
        if not any(record.get('source') == str(b) for record in report):
            raise AssertionError('transitive dependency was not copied')
        if any(hashlib.sha256(p.read_bytes()).hexdigest() != before[p] for p in (a, b)):
            raise AssertionError('relocation changed source library bytes')
        deps.rename(root / 'source-no-longer-at-original-path')
        for image in sorted(app.rglob('*')):
            if image.is_file() and image.suffix == '.dylib':
                subprocess.run(['codesign', '--force', '--sign', '-', str(image)], check=True)
        for executable in executables:
            subprocess.run(['codesign', '--force', '--sign', '-', str(executable)], check=True)
        result = validate(app, require_release_metadata=True)
        if result['executables'] != 2 or result['mach_o_images'] != 4:
            raise AssertionError('nested app or transitive library missing')
        for executable in executables:
            subprocess.run([str(executable)], check=True)
        print('PASS: generated main/helper execute using two bundled transitive libraries after source removal; original library hashes preserved')


if __name__ == '__main__':
    main()
