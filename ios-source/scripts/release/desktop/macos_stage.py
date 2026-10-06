#!/usr/bin/env python3
"""Copy and deploy a macOS candidate; no source mutation, app launch or signing."""
import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from macos_validate import inside, inventory, validate
from macos_relocate import Relocator


def stage(source, destination, deployqt, qml, notices, report, library_roots=(),
          extra_libraries=(), vulkan_loader=None, vulkan_icd=None, minimum_os=None):
    source, destination = source.absolute(), destination.absolute()
    if (extra_libraries or vulkan_loader or vulkan_icd) and not library_roots:
        raise ValueError('runtime libraries require explicit approved library roots')
    if bool(vulkan_loader) != bool(vulkan_icd):
        raise ValueError('both Vulkan loader and ICD must be supplied')
    if destination.exists() or destination.is_symlink() or destination.suffix != '.app':
        raise ValueError('destination must be a new .app path')
    if inside(destination, source) or inside(source, destination):
        raise ValueError('source and candidate paths must not overlap')
    if inside(report, destination) or inside(report, source) or report.exists() or report.is_symlink():
        raise ValueError('report must be a new path outside source and candidate')
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise ValueError('candidate parent must be an existing real directory')
    if not deployqt.is_file() or deployqt.name != 'macdeployqt' or not qml.is_dir():
        raise ValueError('explicit macdeployqt tool and QML source directory required')
    # Read-only structural preflight; source's private Qt paths are allowed here only.
    inventory(source, check_qt_conf=False)
    for name in ('COPYING', 'THIRD_PARTY_NOTICES.txt', 'SOURCE_OFFER.txt'):
        path = notices / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            raise ValueError(f'missing release notice/source offer: {path}')
    shutil.copytree(source, destination, symlinks=True)
    try:
        # Absolute source-internal links still point into the source after copying.
        # Reject those before writing configuration, notices or deploying binaries.
        inventory(destination, check_qt_conf=False)
        notice_target = destination / 'Contents/Resources/ReleaseNotices'
        if notice_target.exists() or not inside(notice_target, destination):
            raise ValueError('candidate notice destination already exists or escapes bundle')
        notice_target.mkdir(parents=True)
        for name in ('COPYING', 'THIRD_PARTY_NOTICES.txt', 'SOURCE_OFFER.txt'):
            shutil.copy2(notices / name, notice_target / name)
        # Only the candidate receives a deployed Qt layout. Preserve all source bytes.
        for conf in (destination / 'Contents/Resources/qt.conf', destination / 'Contents/MacOS/qt.conf'):
            if conf.exists():
                conf.unlink()
        resource_conf = destination / 'Contents/Resources/qt.conf'
        resource_conf.write_text('[Paths]\nPrefix=\nPlugins=PlugIns\nQmlImports=Resources/qml\nQml2Imports=Resources/qml\nTranslations=Resources/translations\n')
        subprocess.run([str(deployqt.resolve()), str(destination), '-always-overwrite', '-no-strip',
                        '-qmldir=' + str(qml.resolve())], check=True)
        relocation = []
        if library_roots:
            relocator = Relocator(destination, library_roots)
            for library in extra_libraries:
                relocator.include(library)
            if vulkan_loader:
                relocator.include(vulkan_loader, 'libvulkan.1.dylib')
                manifest = json.loads(vulkan_icd.read_text())
                original_library = vulkan_icd.parent / manifest['ICD']['library_path']
                target = relocator.include(original_library, 'libMoltenVK.dylib')
                directory = destination / 'Contents/Resources/vulkan/icd.d'
                directory.mkdir(parents=True, exist_ok=True)
                manifest['ICD']['library_path'] = os.path.relpath(target, directory)
                (directory / 'MoltenVK_icd.json').write_text(json.dumps(manifest, indent=2) + '\n')
            relocation = relocator.run()
        plist = destination / 'Contents/Info.plist'
        with plist.open('rb') as stream:
            info = plistlib.load(stream)
        if minimum_os:
            info['LSMinimumSystemVersion'] = minimum_os
        if library_roots and vulkan_loader:
            env = info.get('LSEnvironment', {})
            for key in ('QT_VULKAN_LIB', 'VK_DRIVER_FILES', 'VK_ICD_FILENAMES'):
                env.pop(key, None)
        with plist.open('wb') as stream:
            plistlib.dump(info, stream)
        result = validate(destination, require_release_metadata=bool(library_roots))
        result['relocation'] = relocation
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        with report.open('x') as stream:
            json.dump({'status': 'FAILED', 'candidate': str(destination), 'reason': str(error),
                       'scope': 'incomplete unsigned candidate; not portable or release-ready'}, stream, indent=2)
        raise
    result['status'] = 'PORTABILITY_PASS_UNSIGNED'
    with report.open('x') as stream:
        json.dump(result, stream, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'candidate', 'macdeployqt', 'qml-dir', 'notices', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--library-root', type=Path, action='append', default=[])
    parser.add_argument('--extra-library', type=Path, action='append', default=[])
    parser.add_argument('--vulkan-loader', type=Path)
    parser.add_argument('--vulkan-icd', type=Path)
    parser.add_argument('--minimum-os')
    args = parser.parse_args()
    try:
        result = stage(args.source, args.candidate, args.macdeployqt, args.qml_dir, args.notices, args.report,
                       args.library_root, args.extra_library, args.vulkan_loader, args.vulkan_icd, args.minimum_os)
        print(f'PORTABILITY PASS: {result["mach_o_images"]} images; unsigned candidate {args.candidate}; runtime unverified')
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
