#!/usr/bin/env python3
"""Prepare an existing Flatpak manifest against an explicit source artifact; no build/publish."""
import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath


def prepare(manifest, archive, checksum, revision, app_id):
    import yaml  # PyYAML is required only for this entry point.
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('revision must be a full lowercase Git SHA')
    if not re.fullmatch(r'[0-9a-f]{64}', checksum):
        raise ValueError('sha256 must be 64 lowercase hex characters')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*){2,}', app_id):
        raise ValueError('invalid Flatpak app ID')
    digest = hashlib.sha256()
    with archive.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != checksum:
        raise ValueError('source archive checksum mismatch')
    with tarfile.open(archive) as source:
        members = source.getmembers()
        roots = set()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('unsafe source archive path')
            roots.add(path.parts[0])
            if member.issym() or member.islnk():
                target = PurePosixPath(member.linkname)
                if target.is_absolute() or '..' in target.parts:
                    raise ValueError('unsafe source archive link')
            elif not member.isfile() and not member.isdir():
                raise ValueError('unsupported source archive special file')
        if len(roots) != 1:
            raise ValueError('archive must contain one enclosing source directory')
        root = roots.pop()
        required = [f'{root}/RELEASE_SOURCE_REVISION', f'{root}/COPYING', f'{root}/CMakeLists.txt']
        for name in required:
            member = source.getmember(name)
            if not member.isfile() or member.size == 0:
                raise ValueError(f'missing source metadata: {name}')
        member = source.getmember(required[0])
        if member.size > 128:
            raise ValueError('invalid revision metadata')
        if source.extractfile(member).read().decode('ascii').strip() != revision:
            raise ValueError('archive revision metadata mismatch')
    data = yaml.safe_load(manifest.read_text())
    if data.get('app-id') != app_id:
        raise ValueError('requested app ID differs from manifest; branding migration requires separate review')
    modules = [x for x in data['modules'] if isinstance(x, dict) and x.get('name') == 'GameRemote']
    if len(modules) != 1:
        raise ValueError('expected exactly one GameRemote source module')
    modules[0]['sources'] = [{'type': 'archive', 'path': str(archive.resolve()), 'sha256': checksum}]

    def paths(value):
        if isinstance(value, dict):
            # Existing dependency patch sources are relative to the original manifest.
            if 'path' in value and value.get('type') in ('file', 'patch', 'archive', 'dir'):
                original = Path(value['path'])
                resolved = (manifest.parent / original).resolve()
                if not resolved.exists():
                    raise ValueError(f'missing manifest source: {resolved}')
                value['path'] = str(resolved)
            for child in value.values():
                paths(child)
        elif isinstance(value, list):
            for child in value:
                paths(child)
    paths(data)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--app-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        data = prepare(args.manifest, args.source, args.sha256, args.revision, args.app_id)
        with args.output.open('x') as stream:
            json.dump(data, stream, indent=2)
        print(f'Prepared {args.output}; runtime {data["runtime"]}//{data["runtime-version"]}; no build performed')
    except (ValueError, KeyError, OSError, ImportError, tarfile.TarError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
