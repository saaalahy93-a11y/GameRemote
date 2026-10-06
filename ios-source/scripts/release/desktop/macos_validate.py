#!/usr/bin/env python3
"""Read-only, conservative macOS bundle portability gate; never repairs or signs."""
import argparse
import configparser
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

MACH_MAGIC = {bytes.fromhex(x) for x in ('feedface', 'cefaedfe', 'feedfacf', 'cffaedfe', 'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}
LOADS = {'LC_LOAD_DYLIB', 'LC_LOAD_WEAK_DYLIB', 'LC_REEXPORT_DYLIB', 'LC_LOAD_UPWARD_DYLIB', 'LC_LAZY_LOAD_DYLIB'}


def inside(path, root):
    return path.resolve().is_relative_to(root.resolve())


def system(path):
    # Frameworks/libraries on the sealed OS volume may live only in dyld's cache.
    normalized = os.path.normpath(path)
    return normalized.startswith(('/System/Library/', '/usr/lib/'))


def validate_qt_conf(path, bundle):
    conf = configparser.ConfigParser()
    conf.read(path)
    enclosing = next((parent for parent in path.parents if parent.suffix == '.app'), None)
    if enclosing is None:
        raise ValueError(f'qt.conf has no app context: {path}')
    base = enclosing / 'Contents'
    for section in conf.sections():
        if section.lower() not in ('paths', 'effectivepaths'):
            continue
        prefix = conf.get(section, 'prefix', fallback='')
        values = [('prefix', prefix)] + [(key, value) for key, value in conf.items(section) if key != 'prefix']
        for key, value in values:
            for item in value.split(','):
                item = item.strip()
                if item.startswith(('/', '~')) or re.match(r'^[A-Za-z]:', item):
                    raise ValueError(f'private/absolute qt.conf path: {path}: {key}')
                candidate = base / item if key == 'prefix' else base / prefix / item
                if not inside(candidate, bundle):
                    raise ValueError(f'escaping qt.conf path: {path}: {key}')


def inventory(bundle, check_qt_conf=True):
    if bundle.is_symlink() or not bundle.is_dir() or bundle.suffix != '.app':
        raise ValueError('bundle must be a real .app directory')
    binaries = []
    for directory, dirs, files in os.walk(bundle, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                if not inside(path, bundle) or not path.exists():
                    raise ValueError(f'escaping or broken symlink: {path}')
                if path.is_file() and name == 'qt.conf' and check_qt_conf:
                    validate_qt_conf(path, bundle)
                continue
            if path.is_file():
                if name == 'qt.conf' and check_qt_conf:
                    validate_qt_conf(path, bundle)
                with path.open('rb') as stream:
                    if stream.read(4) in MACH_MAGIC:
                        binaries.append(path.resolve())
    if not binaries:
        raise ValueError('bundle contains no Mach-O images')
    return sorted(set(binaries))


def parse_load_commands(output):
    """Parse otool -l per architecture; LC_ID_DYLIB is deliberately not a load."""
    result = {}
    arch = 'native'
    command = None
    for line in output.splitlines():
        match = re.search(r'\(architecture ([^)]+)\):$', line)
        if match:
            arch = match.group(1)
            command = None
        result.setdefault(arch, {'dependencies': [], 'rpaths': []})
        words = line.strip().split()
        if words[:1] == ['cmd'] and len(words) == 2:
            command = words[1]
        elif command in LOADS and line.strip().startswith('name '):
            result[arch]['dependencies'].append(line.strip()[5:].rsplit(' (offset ', 1)[0])
        elif command == 'LC_RPATH' and line.strip().startswith('path '):
            result[arch]['rpaths'].append(line.strip()[5:].rsplit(' (offset ', 1)[0])
        elif command == 'LC_BUILD_VERSION' and words[:1] == ['minos']:
            result[arch]['minimum_os'] = words[1]
        elif command == 'LC_VERSION_MIN_MACOSX' and words[:1] == ['version']:
            result[arch]['minimum_os'] = words[1]
    # A universal header before its first architecture is not an image.
    if len(result) > 1 and result.get('native') == {'dependencies': [], 'rpaths': []}:
        result.pop('native')
    return result


def expand(value, image, executable):
    if value.startswith('@loader_path/'):
        return image.parent / value[len('@loader_path/'):]
    if value.startswith('@executable_path/'):
        return executable.parent / value[len('@executable_path/'):]
    if value.startswith('/'):
        return Path(value)
    raise ValueError(f'unsupported loader path: {value}')


def resolve(dependency, image, executable, rpaths, bundle):
    if dependency.startswith('/'):
        if system(dependency):
            return None
        raise ValueError(f'absolute non-system dependency: {image}: {dependency}')
    candidates = ([p / dependency[7:] for p in rpaths] if dependency.startswith('@rpath/')
                  else [expand(dependency, image, executable)])
    for candidate in candidates:
        if not inside(candidate, bundle):
            raise ValueError(f'loader search escapes bundle: {image}: {candidate}')
        if candidate.is_file():
            return candidate.resolve()
    raise ValueError(f'unresolved dependency: {image}: {dependency}')


def executable_for(image, bundle):
    # Helpers have their own @executable_path; frameworks use the enclosing app.
    for parent in image.parents:
        if parent.suffix == '.app' and inside(parent, bundle):
            plist = parent / 'Contents/Info.plist'
            with plist.open('rb') as stream:
                name = plistlib.load(stream).get('CFBundleExecutable')
            if not name or '/' in name or '\\' in name:
                raise ValueError(f'invalid CFBundleExecutable: {plist}')
            executable = parent / 'Contents/MacOS' / name
            if not executable.is_file() or not inside(executable, bundle):
                raise ValueError(f'missing/escaping app executable: {executable}')
            return executable.resolve()
    raise ValueError(f'no app context: {image}')


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+){0,2}', value):
        raise ValueError(f'invalid minimum system version: {value!r}')
    parts = tuple(int(part) for part in value.split('.'))
    return parts + (0,) * (3 - len(parts))


def validate_runtime_config(bundle):
    runtime_images = []
    runtime_keys = {'QT_VULKAN_LIB', 'VK_DRIVER_FILES', 'VK_ICD_FILENAMES',
                    'QT_PLUGIN_PATH', 'QML_IMPORT_PATH', 'QML2_IMPORT_PATH',
                    'DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH', 'QTWEBENGINEPROCESS_PATH'}
    for plist in bundle.rglob('Info.plist'):
        with plist.open('rb') as stream:
            info = plistlib.load(stream)
        for key, value in info.get('LSEnvironment', {}).items():
            if key in runtime_keys:
                raise ValueError(f'nonportable runtime environment in plist: {plist}: {key}')
    icd = bundle / 'Contents/Resources/vulkan/icd.d/MoltenVK_icd.json'
    if icd.exists():
        value = json.loads(icd.read_text())['ICD']['library_path']
        library = icd.parent / value
        if Path(value).is_absolute() or not inside(library, bundle) or not library.is_file():
            raise ValueError(f'nonportable Vulkan ICD library: {icd}')
        loader = bundle / 'Contents/Frameworks/libvulkan.1.dylib'
        if not loader.is_file() or not inside(loader, bundle):
            raise ValueError('bundled Vulkan ICD has no bundled loader')
        runtime_images = [loader.resolve(), library.resolve()]
    return runtime_images


def validate(bundle, inspect=None, require_release_metadata=False):
    inventory(bundle.absolute())  # Check the user-supplied root before canonicalizing.
    bundle = bundle.resolve()
    runtime_images = validate_runtime_config(bundle)
    images = inventory(bundle)
    for image in runtime_images:
        if image not in images:
            raise ValueError(f'Vulkan runtime is not an inventoried Mach-O image: {image}')
    if inspect is None:
        def inspect(path):
            arches = subprocess.check_output(['lipo', '-archs', str(path)], text=True).strip().split()
            if not arches:
                raise ValueError(f'cannot establish Mach-O architectures: {path}')
            result = {}
            for arch in arches:
                parsed = parse_load_commands(subprocess.check_output(['otool', '-arch', arch, '-l', str(path)], text=True))
                if len(parsed) != 1:
                    raise ValueError(f'ambiguous load command architecture: {path}: {arch}')
                result[arch] = next(iter(parsed.values()))
            return result
    metadata = {path: inspect(path) for path in images}
    minimum_os = None
    if require_release_metadata:
        with (bundle / 'Contents/Info.plist').open('rb') as stream:
            minimum_os = plistlib.load(stream).get('LSMinimumSystemVersion')
        declared = version_tuple(minimum_os)
        for image, slices in metadata.items():
            for arch, info in slices.items():
                required = version_tuple(info.get('minimum_os'))
                if required > declared:
                    raise ValueError(f'dependency minimum OS exceeds app declaration: {image}: {arch}: {info["minimum_os"]} > {minimum_os}')
    records, visited = [], set()

    def visit(image, executable, arch, inherited):
        key = (image, executable, arch, tuple(inherited))
        if key in visited:
            return
        visited.add(key)
        info = metadata.get(image, {}).get(arch)
        if info is None:
            raise ValueError(f'missing Mach-O architecture {arch}: {image}')
        own = []
        for value in info['rpaths']:
            path = expand(value, image, executable)
            if not inside(path, bundle):
                raise ValueError(f'nonportable RPATH: {image}: {value}')
            own.append(path.resolve())
        # dyld searches the current loader first, then its loader chain.
        paths = list(dict.fromkeys(own + inherited))
        for dependency in info['dependencies']:
            target = resolve(dependency, image, executable, paths, bundle)
            records.append({'image': str(image.relative_to(bundle)), 'executable': str(executable.relative_to(bundle)),
                            'architecture': arch, 'dependency': dependency,
                            'resolved': str(target.relative_to(bundle)) if target else 'system'})
            if target:
                # Deduplicated search stack bounds cycles without changing order.
                visit(target, executable, arch, paths)

    roots = sorted({executable_for(image, bundle) for image in images})
    for executable in roots:
        if executable not in metadata:
            raise ValueError(f'app executable is not a Mach-O image: {executable}')
        for arch in metadata.get(executable, {}):
            visit(executable, executable, arch, [])
    # These images are loaded at runtime, so the executable's linked graph does
    # not establish either their architecture coverage or their dependencies.
    for image in runtime_images:
        executable = executable_for(image, bundle)
        for arch, entry in metadata[executable].items():
            inherited = [expand(x, executable, executable).resolve() for x in entry['rpaths']]
            visit(image, executable, arch, inherited)
    reached = {(key[0], key[1], key[2]) for key in visited}
    # Include dlopen plugins/orphan images, not just the main executable graph.
    for image in images:
        executable = executable_for(image, bundle)
        for arch in metadata[image]:
            if (image, executable, arch) not in reached:
                entry = metadata[executable].get(arch)
                if entry is None:
                    raise ValueError(f'plugin architecture absent in app: {image}: {arch}')
                inherited = [expand(x, executable, executable).resolve() for x in entry['rpaths']]
                visit(image, executable, arch, inherited)
    return {'bundle': str(bundle), 'mach_o_images': len(images), 'executables': len(roots), 'loads': records,
            'minimum_system_version': minimum_os,
            'scope': 'static loader portability; signing, notarization and runtime not validated'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if inside(args.report, args.bundle):
        parser.error('report must be outside the bundle')
    try:
        report = validate(args.bundle, require_release_metadata=True)
        with args.report.open('x') as stream:
            json.dump(report, stream, indent=2)
        print(f"PASS: {report['mach_o_images']} images; report: {args.report}")
    except (ValueError, OSError, subprocess.CalledProcessError, configparser.Error, plistlib.InvalidFileException) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
