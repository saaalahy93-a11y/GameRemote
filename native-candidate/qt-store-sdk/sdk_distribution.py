"""Bind a Qt SDK to retained upstream sources, licence texts and its recipe."""

import hashlib
import json
import posixpath
import re
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

from sdk_common import ROOT, digest, read_lock, sha256, write_json

QT_MODULES = ('qtbase', 'qtsvg', 'qtshadertools', 'qtdeclarative')
RECIPE_FILES = ('README.md', 'SHA256SUMS', 'build-qt693.sh', 'build_sdk.py', 'sdk_common.py',
                'sdk_distribution.py', 'dependencies.lock.json', 'probe/CMakeLists.txt',
                'probe/main.cpp', 'test_sdk.py', 'test_distribution.py')
MACH_MAGIC = {bytes.fromhex(value) for value in
              ('feedface', 'cefaedfe', 'feedfacf', 'cffaedfe', 'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}


def source_inputs(work, recipe, lock):
    pins = {}
    for line in (recipe / 'SHA256SUMS').read_text().splitlines():
        value, name = line.split()
        if name in pins or Path(name).name != name:
            raise ValueError('ambiguous Qt source checksum manifest')
        pins[name] = sha256(value)
    expected = {name + '-everywhere-src-6.9.3.tar.xz' for name in QT_MODULES}
    if set(pins) != expected:
        raise ValueError('source kit must contain the exact four Qt module archives')
    result = [{'component': name, 'version': '6.9.3', 'sha256': pins[filename],
               'url': 'https://download.qt.io/archive/qt/6.9/6.9.3/submodules/' + filename,
               'file': work / 'qt-store-sdk/downloads' / filename}
              for name in QT_MODULES for filename in [name + '-everywhere-src-6.9.3.tar.xz']]
    for component, key in (('Vulkan-Headers', 'vulkan_headers'), ('MoltenVK', 'moltenvk_headers')):
        spec = lock['macos'][key]
        result.append({'component': component, 'version': spec['version'],
                       'sha256': sha256(spec['sha256']), 'url': spec['url'],
                       'file': work / 'downloads' / spec['filename']})
    for item in result:
        if not item['file'].is_file() or digest(item['file']) != item['sha256']:
            raise ValueError('source kit archive missing or checksum changed: ' + item['component'])
    return result


def license_references(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'LicenseFile':
                values = item if isinstance(item, list) else [item]
                for reference in values:
                    if not isinstance(reference, str) or not reference.strip():
                        raise ValueError('unrecognized Qt LicenseFile reference')
                    yield reference
            else:
                yield from license_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from license_references(item)


def collect_notices(archive, output):
    """Use opaque content hashes as filenames, avoiding path/case alias writes."""
    selected, available, attributions = {}, set(), []
    with tarfile.open(archive, 'r|*') as source:
        for member in source:
            if not member.isfile():
                continue
            if member.name in available:
                raise ValueError('duplicate source archive member')
            available.add(member.name)
            path = PurePosixPath(member.name)
            attribution = path.name in ('qt_attribution.json', 'qt_attributions.json')
            notice = (any(part.lower() == 'licenses' for part in path.parts)
                      or re.match(r'(?i)^(licen[cs]e|copying|notice|copyright)(?:$|[._-])', path.name))
            if not (attribution or notice):
                continue
            if member.size > 4 * 1024 ** 2:
                raise ValueError('notice member exceeds the 4 MiB bound')
            data = source.extractfile(member).read()
            selected[member.name] = data
            if attribution:
                # Qt 6.9.3 contains literal newlines in some attribution strings.
                # Preserve the original bytes and permit those JSON string controls.
                attributions.append((member.name, json.loads(data, strict=False)))
    references = []
    needed = set()
    for origin, data in attributions:
        for reference in license_references(data):
            target = posixpath.normpath(str(PurePosixPath(origin).parent / reference))
            if target not in available:
                raise ValueError(f'Qt LicenseFile is absent from its retained archive: {origin}: {reference}')
            references.append({'attribution': origin, 'reference': reference, 'member': target})
            needed.add(target)
    missing = needed - selected.keys()
    if missing:
        with tarfile.open(archive, 'r|*') as source:
            for member in source:
                if member.name in missing:
                    if not member.isfile() or member.size > 4 * 1024 ** 2:
                        raise ValueError('referenced licence text is not a bounded regular file')
                    selected[member.name] = source.extractfile(member).read()
    if not selected or needed - selected.keys():
        raise ValueError('source archive has no complete extractable notice set')
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for name, data in sorted(selected.items()):
        value = hashlib.sha256(data).hexdigest()
        path = output / (value + '.txt')
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError('notice content-address collision')
        else:
            path.write_bytes(data)
        records.append({'member': name, 'file': 'notices/' + path.name,
                        'sha256': value, 'bytes': len(data)})
    return {'texts': records, 'license_references': references}


def inspect_macho(path):
    def read(*args):
        return subprocess.check_output(args, text=True, timeout=15)

    architectures = read('/usr/bin/lipo', '-archs', str(path)).strip().split()
    if architectures != ['arm64']:
        raise ValueError('SDK Mach-O does not contain exactly the expected arm64 slice')
    identities = read('/usr/bin/otool', '-D', str(path)).splitlines()[1:]
    imports = [line.strip().split(' (compatibility')[0]
               for line in read('/usr/bin/otool', '-L', str(path)).splitlines()[1:]]
    imports = [name for name in imports if name not in identities]
    external = [name for name in imports if name.startswith('/')
                and not name.startswith(('/usr/lib/', '/System/Library/'))]
    return {'architectures': architectures, 'imports': imports,
            'non_system_absolute_imports': external}


def sdk_inventory(archive, prefix):
    records, binaries = [], []
    expanded = 0
    with tarfile.open(archive, 'r|gz') as source:
        for member in source:
            path = PurePosixPath(member.name)
            if (not path.parts or path.parts[0] != prefix.name or '..' in path.parts
                    or path.is_absolute() or len(records) >= 100_000):
                raise ValueError('unexpected SDK archive member')
            row = {'member': member.name, 'mode': member.mode, 'bytes': member.size}
            if member.isfile():
                expanded += member.size
                if expanded > 3 * 1024 ** 3:
                    raise ValueError('SDK inventory exceeds 3 GiB expanded bound')
                stream = source.extractfile(member)
                header = stream.read(4)
                value = hashlib.sha256(header)
                while block := stream.read(1024 * 1024):
                    value.update(block)
                row.update(type='file', sha256=value.hexdigest())
                if header in MACH_MAGIC:
                    actual = prefix.joinpath(*path.parts[1:]).resolve(strict=True)
                    if not actual.is_relative_to(prefix) or digest(actual) != row['sha256']:
                        raise ValueError('relocated SDK binary differs from the packaged SDK')
                    binary = {'member': member.name, 'sha256': row['sha256'], **inspect_macho(actual)}
                    binaries.append(binary)
            elif member.isdir():
                row['type'] = 'directory'
            elif member.issym() or member.islnk():
                row.update(type='symlink' if member.issym() else 'hardlink', target=member.linkname)
            else:
                raise ValueError('unsupported SDK archive member')
            records.append(row)
    if not binaries:
        raise ValueError('SDK inventory contains no Mach-O binaries')
    return {'members': records, 'mach_o': binaries, 'expanded_regular_bytes': expanded,
            'scope': 'Actual SDK archive bytes and dependencies; no app or GPU runtime qualification'}


def assemble_distribution(archive, work, output, recipe=ROOT, workflow=None):
    specs = source_inputs(work, recipe, read_lock() if recipe == ROOT else
                          json.loads((recipe / 'dependencies.lock.json').read_text()))
    workflow = workflow or recipe.parents[1] / '.github/workflows/build-macos-store-sdk.yml'
    required_space = sum(item['file'].stat().st_size for item in specs) + 32 * 1024 ** 2
    if shutil.disk_usage(output).free < required_space:
        raise ValueError('insufficient space for retained SDK source/notice kit')
    sources = output / 'sources'
    sources.mkdir()
    inventory = sdk_inventory(archive, work / 'relocated/Qt-6.9.3-appstore-arm64')
    write_json(output / 'sdk-inventory.json', inventory)
    rows = []
    for spec in specs:
        target = sources / spec['file'].name
        shutil.copy2(spec['file'], target)
        if digest(target) != spec['sha256']:
            raise ValueError('retained source archive changed during copy')
        notices = collect_notices(target, output / 'notices')
        rows.append({key: value for key, value in spec.items() if key != 'file'} |
                    {'file': 'sources/' + target.name, 'bytes': target.stat().st_size, **notices})
    recipe_rows = []
    with tarfile.open(output / 'recipe.tar.gz', 'w:gz') as source:
        for name in RECIPE_FILES:
            file = recipe / name
            member = 'SDK-Recipe/native-candidate/qt-store-sdk/' + name
            source.add(file, arcname=member, recursive=False)
            recipe_rows.append({'member': member, 'sha256': digest(file)})
        member = 'SDK-Recipe/.github/workflows/build-macos-store-sdk.yml'
        source.add(workflow, arcname=member, recursive=False)
        recipe_rows.append({'member': member, 'sha256': digest(workflow)})
    (output / 'README.txt').write_text(
        'Qt 6.9.3 Store SDK distribution kit\n\n'
        'Qt includes components under the GNU LGPL and other upstream licences.\n'
        'Full upstream licence texts and Qt third-party attributions are in notices/;\n'
        'distribution.json maps every text to its retained source archive/member.\n'
        'sources/ contains the complete, exact four Qt module archives, Vulkan-Headers\n'
        'and MoltenVK source archives used by this build, including upstream licences.\n'
        'Only the MoltenVK wrapper header is used; no MoltenVK runtime is built or linked.\n'
        'recipe.tar.gz contains the build scripts, pinned inputs, tests and workflow.\n'
        'distribution.json binds these materials to the SDK binary archive by SHA-256.\n'
        'sdk-inventory.json records the actual SDK member hashes, arm64 Mach-O files and\n'
        'imports. Inspect its non-system absolute imports when supplying dependencies.\n'
        'This kit contains no GameRemote application source or application binary.\n'
        'The app source hash in the SDK receipt is an unbuilt compatibility reference.\n'
        'SDK checks do not qualify an app, GPU runtime, publisher signing or Store upload.\n')
    result = {'scope': 'SDK binary with exact upstream source archives, notices and build recipe',
              'sdk': {'file': 'packages/' + archive.name, 'sha256': digest(archive)},
              'sdk_inventory': {'file': 'sdk-inventory.json', 'sha256': digest(output / 'sdk-inventory.json')},
              'readme': {'file': 'README.txt', 'sha256': digest(output / 'README.txt')},
              'sources': rows, 'recipe': {'file': 'recipe.tar.gz', 'sha256': digest(output / 'recipe.tar.gz'),
                                         'files': recipe_rows}, 'private_app_source_included': False}
    write_json(output / 'distribution.json', result)
    return {'file': 'distribution.json', 'sha256': digest(output / 'distribution.json'),
            'source_archives': len(rows), 'notice_records': sum(len(row['texts']) for row in rows),
            'mach_o_files': len(inventory['mach_o'])}
