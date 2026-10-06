"""Build and relocate the real Qt SDK; this does not qualify a Store app."""
import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from sdk_common import (
    ROOT,
    digest,
    fetch,
    read_lock,
    run,
    tools_for,
    unpack,
    write_json,
)
from sdk_distribution import RECIPE_FILES, assemble_distribution


def prepare_vulkan_headers(spec: dict, work: Path, evidence: Path) -> Path:
    archive = fetch(spec, work / 'downloads')
    destination = work / 'vulkan-headers'
    unpack(archive, destination)
    headers = list(destination.glob('*/include/vulkan/vulkan.h'))
    if len(headers) != 1:
        raise ValueError('pinned Vulkan-Headers archive must contain one include/vulkan/vulkan.h')
    include = headers[0].parent.parent.resolve(strict=True)
    for name in ('vulkan/vulkan.h', 'vulkan/vulkan_core.h', 'vulkan/vk_platform.h'):
        header = (include / name).resolve(strict=True)
        if not header.is_relative_to(destination.resolve()) or not header.is_file():
            raise ValueError('Vulkan header escaped its verified source archive')
    write_json(evidence / 'vulkan-headers.json', {
        'version': spec['version'], 'url': spec['url'], 'archive_sha256': digest(archive),
        'include': str(include), 'purpose': 'Qt SDK compile-time headers; not the app Vulkan runtime',
        'headers': [{'path': str(path.relative_to(include)), 'sha256': digest(path)}
                    for path in sorted(include.rglob('*.h'))],
    })
    return include


def prepare_macos_vulkan_headers(vulkan_include: Path, spec: dict, work: Path, evidence: Path) -> Path:
    """Add Qt Cocoa's exact MoltenVK wrapper header to a separate include tree."""
    archive = fetch(spec, work / 'downloads')
    member_name = f'MoltenVK-{spec["version"]}/MoltenVK/MoltenVK/API/mvk_vulkan.h'
    with tarfile.open(archive, 'r:gz') as source:
        try:
            member = source.getmember(member_name)
        except KeyError as error:
            raise ValueError('pinned MoltenVK archive is missing mvk_vulkan.h') from error
        if not member.isfile() or not 0 < member.size <= 64 * 1024:
            raise ValueError('MoltenVK wrapper header must be a bounded regular file')
        contents = source.extractfile(member).read()
    include = work / 'macos-vulkan-include'
    shutil.copytree(vulkan_include, include)
    (include / 'MoltenVK').mkdir()
    header = include / 'MoltenVK/mvk_vulkan.h'
    header.write_bytes(contents)
    write_json(evidence / 'moltenvk-headers.json', {
        'version': spec['version'], 'url': spec['url'], 'archive_sha256': digest(archive),
        'source_member': member_name, 'header': 'MoltenVK/mvk_vulkan.h', 'header_sha256': digest(header),
        'include': str(include), 'khronos_include_origin': str(vulkan_include),
        'purpose': 'Qt Cocoa compile-time wrapper; no MoltenVK runtime library is built or linked',
    })
    return include


def verify_macos_vulkan_headers(include: Path, evidence: Path) -> None:
    """Fail before Qt compilation if Cocoa's header or surface API is absent."""
    probe = evidence / 'macos-vulkan-headers.mm'
    probe.write_text('#include <MoltenVK/mvk_vulkan.h>\n'
                     'static_assert(VK_USE_PLATFORM_MACOS_MVK == 1);\n'
                     'static_assert(sizeof(VkMacOSSurfaceCreateInfoMVK) > 0);\n'
                     'static_assert(sizeof(PFN_vkCreateMacOSSurfaceMVK) > 0);\n')
    run(['/usr/bin/xcrun', '--sdk', 'macosx', 'clang++', '-x', 'objective-c++', '-std=c++17',
         '-arch', 'arm64', '-fsyntax-only', '-I', str(include), str(probe)], timeout=60)
    write_json(evidence / 'macos-vulkan-header-check.json', {
        'status': 'passed', 'probe_sha256': digest(probe), 'include': str(include),
        'scope': 'Objective-C++ header/type compilation only; no linking, GPU or runtime execution',
    })


def build(work: Path, evidence: Path) -> Path:
    lock = read_lock()['macos']
    os.environ['DEVELOPER_DIR'] = lock['developer_dir']
    xcode = subprocess.check_output(['xcrun', 'xcodebuild', '-version'], text=True)
    sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-version'], text=True).strip()
    if not xcode.startswith('Xcode ' + lock['xcode'] + '\n') or sdk != lock['sdk']:
        raise ValueError('selected Xcode or macOS SDK differs from lock')
    write_json(evidence / 'toolchain.json', {'xcode': xcode, 'sdk': sdk})
    tools = tools_for('macos', work)
    vulkan_include = prepare_vulkan_headers(lock['vulkan_headers'], work, evidence)
    vulkan_include = prepare_macos_vulkan_headers(vulkan_include, lock['moltenvk_headers'], work, evidence)
    verify_macos_vulkan_headers(vulkan_include, evidence)
    recipe = work / 'qt-store-sdk'
    shutil.copytree(ROOT, recipe, ignore=shutil.ignore_patterns('__pycache__'))
    os.environ['QT_CMAKE_TOOL_BIN'] = str(tools['cmake'].parent)
    os.environ.pop('GAMEREMOTE_SOURCE', None)
    os.environ['QT_VULKAN_INCLUDE_DIR'] = str(vulkan_include)
    for phase in ('preflight', 'download', 'sources', 'build'):
        run(['bash', str(recipe / 'build-qt693.sh'), phase], timeout=6600)
    shutil.copy2(recipe / 'build/probe/gameremote-mac-app-store-qt.json', evidence)
    shutil.copy2(recipe / 'build/qtbase/CMakeCache.txt', evidence / 'qtbase-CMakeCache.txt')
    prefix = recipe / 'prefix'
    package = work / 'GameRemote-Qt-6.9.3-appstore-arm64.tar.gz'
    with tarfile.open(package, 'w:gz') as output:
        output.add(prefix, arcname='Qt-6.9.3-appstore-arm64')
    relocated = work / 'relocated'
    unpack(package, relocated)
    new_prefix = relocated / 'Qt-6.9.3-appstore-arm64'
    prefix.rename(recipe / 'prefix-hidden')
    run([str(new_prefix / 'bin/qt-cmake'), '-S', str(recipe / 'probe'), '-B', str(work / 'relocation-probe'),
         '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_OSX_ARCHITECTURES=arm64',
         '-DCMAKE_MAKE_PROGRAM=' + str(tools['ninja']),
         '-DVulkan_INCLUDE_DIR=' + str(vulkan_include)])
    run(['cmake', '--build', str(work / 'relocation-probe'), '--parallel', '1'])
    run([str(work / 'relocation-probe/qt_store_probe')])
    shutil.copy2(work / 'relocation-probe/gameremote-mac-app-store-qt.json', evidence / 'relocated-qt-guard.json')
    return package


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build only the public, unsigned Qt Store SDK')
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--app-source-reference-sha256', required=True,
                        help='Compatibility reference only; no app archive is read or built')
    args = parser.parse_args(argv)
    if not re.fullmatch('[0-9a-f]{64}', args.app_source_reference_sha256):
        raise ValueError('application source reference must be a lowercase SHA-256')
    if platform.system() != 'Darwin' or platform.machine().lower() not in ('arm64', 'aarch64'):
        raise ValueError('Qt SDK requires a native arm64 macOS runner')
    work, output = args.work.resolve(), args.output.resolve()
    if (work.exists() or output.exists() or args.work.is_symlink() or args.output.is_symlink()
            or work.is_relative_to(output) or output.is_relative_to(work)
            or any(path.is_relative_to(ROOT) or ROOT.is_relative_to(path) for path in (work, output))):
        raise ValueError('SDK work/output must be fresh, separate directories outside the recipe')
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    evidence = output / 'evidence'
    evidence.mkdir()
    record = {'target': 'macos-qt-store', 'scope': 'qt-sdk-only', 'status': 'IN_PROGRESS',
              'app_source_reference': {'sha256': args.app_source_reference_sha256,
                                       'archive_read': False, 'application_built': False},
              'store_qualified': False, 'gameplay_qualified': False, 'signed_for_distribution': False}
    try:
        write_json(evidence / 'recipe-inputs.json', {
            'files': [{'path': name, 'sha256': digest(ROOT / name)} for name in RECIPE_FILES],
            'python': sys.version, 'runner_image': os.environ.get('ImageVersion'),
            'harness_commit': os.environ.get('GITHUB_SHA'),
        })
        shutil.copy2(ROOT / 'dependencies.lock.json', evidence)
        package = build(work, evidence)
        if not package.resolve().is_relative_to(work) or not package.is_file():
            raise ValueError('SDK builder returned an unexpected package')
        # The workflow always uploads output, including on failure. Keep the
        # binary in non-uploaded work until its complete source kit is ready.
        distribution = assemble_distribution(package, work, output)
        packages = output / 'packages'
        packages.mkdir()
        result = packages / package.name
        shutil.move(package, result)
        record.update(status='native-candidate-passed', package=result.name, sha256=digest(result),
                      distribution=distribution)
        write_json(evidence / 'candidate.json', record)
        print('Qt SDK original/relocated probes passed; no application source was read or built.')
        return 0
    except BaseException as error:
        record.update(status='FAILED', failure=str(error) or type(error).__name__, retained_incomplete_output=True)
        write_json(evidence / 'candidate.json', record)
        raise


if __name__ == '__main__':
    sys.exit(main())
