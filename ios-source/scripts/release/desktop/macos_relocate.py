#!/usr/bin/env python3
"""Relocate a staged bundle only, using explicitly allowed dependency roots."""
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

from macos_validate import executable_for, expand, inside, inventory, parse_load_commands, system


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect(path):
    return subprocess.check_output(['otool', '-l', str(path)], text=True)


def identity(path):
    """Install-name edits preserve UUIDs; compare all slices before reusing a target."""
    uuids = frozenset(re.findall(r'^\s*uuid ([A-Fa-f0-9-]+)\s*$', inspect(path), re.M))
    if not uuids:
        raise ValueError(f'Mach-O UUID unavailable: {path}')
    return uuids


def framework_path(path):
    for parent in path.parents:
        if parent.suffix == '.framework':
            return parent
    return None


def verify_tree(path):
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(directory) / name
            if item.is_symlink() and (not item.exists() or not inside(item, path)):
                raise ValueError(f'escaping or broken source symlink: {item}')


def verify_framework_content(source, destination):
    """Require deployed runtime resources, allowing macdeployqt's SDK stripping."""
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError(f'incomplete/conflicting framework: {destination}')
    verify_tree(source)
    verify_tree(destination)
    omitted = {'Headers', 'PrivateHeaders', 'Modules', '_CodeSignature'}
    debug_image = source.stem + '_debug'
    for directory, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [name for name in dirs if name not in omitted and not name.endswith('.dSYM')]
        for name in dirs + files:
            item = Path(directory) / name
            relative = item.relative_to(source)
            # Runtime data and nested helper bundles are deployed; headers,
            # module maps, signatures and build-system .prl files need not be.
            if item.suffix == '.prl' or name == debug_image:
                continue
            # Empty source directories add no runtime content; nonempty
            # directories are checked through their files and required aliases.
            if item.is_dir() and not item.is_symlink():
                continue
            target = destination / relative
            if not target.exists() or item.is_dir() != target.is_dir():
                raise ValueError(f'incomplete framework runtime resource: {target}')


class Relocator:
    def __init__(self, bundle, roots):
        inventory(bundle, check_qt_conf=False)
        self.bundle = bundle.resolve()
        self.frameworks = self.bundle / 'Contents/Frameworks'
        self.frameworks.mkdir(exist_ok=True)
        self.roots = [root.resolve(strict=True) for root in roots]
        self.sources = {}
        self.origins = {}
        self.records = []

    def include(self, source, name=None):
        original = source
        source = source.resolve(strict=True)
        if not any(inside(source, root) for root in self.roots):
            raise ValueError(f'dependency outside approved roots: {source}')
        if source in self.sources:
            return self.sources[source]
        framework = framework_path(source)
        if name and (Path(name).name != name or name in ('.', '..')):
            raise ValueError('extra library name must be a filename')
        target = (self.frameworks / framework.name / source.relative_to(framework)
                  if framework else self.frameworks / (name or original.name))
        if target.exists():
            if not inside(target, self.bundle) or identity(source) != identity(target):
                raise ValueError(f'conflicting dependency target: {target}')
            if framework:
                verify_framework_content(framework, self.frameworks / framework.name)
        elif framework:
            destination = self.frameworks / framework.name
            if destination.exists():
                raise ValueError(f'incomplete/conflicting framework: {destination}')
            verify_tree(framework)
            shutil.copytree(framework, destination, symlinks=True)
        else:
            shutil.copy2(source, target)
        target = target.resolve(strict=True)
        self.sources[source] = target
        self.origins[target] = source
        self.records.append({'source': str(source), 'source_sha256': digest(source),
                             'target': str(target.relative_to(self.bundle))})
        return target

    def origin_for(self, image):
        if image in self.origins:
            return self.origins[image]
        # macdeployqt can copy a standalone library before this relocator sees
        # it. Recover provenance only from exact approved-root library names.
        if image.parent != self.frameworks or image.suffix != '.dylib':
            return None
        candidates = {candidate.resolve() for root in self.roots
                      for candidate in (root / image.name, root / 'lib' / image.name)
                      if candidate.is_file() and any(inside(candidate, approved) for approved in self.roots)}
        if not candidates:
            return None
        image_identity = identity(image)
        matches = [candidate for candidate in sorted(candidates) if identity(candidate) == image_identity]
        if len(matches) > 1:
            raise ValueError(f'ambiguous approved source for staged library: {image}')
        if not matches:
            return None
        self.origins[image] = matches[0]
        return matches[0]

    def dependency(self, value, image, paths):
        executable = executable_for(image, self.bundle)
        if value.startswith('/'):
            return None if system(value) else self.include(Path(value))
        if value.startswith('@rpath/'):
            candidates = []
            for path in paths:
                if not path.startswith('@rpath'):
                    candidates.append(expand(path, image, executable) / value[7:])
            candidates.append(self.frameworks / value[7:])
        else:
            candidates = [expand(value, image, executable)]
        for candidate in candidates:
            if candidate.is_file():
                if inside(candidate, self.bundle):
                    return candidate.resolve()
                return self.include(candidate)
        origin = self.origin_for(image)
        if origin:
            source_candidates = []
            if value.startswith('@rpath/'):
                metadata = parse_load_commands(inspect(origin))
                for info in metadata.values():
                    for path in info['rpaths']:
                        if path.startswith(('@loader_path/', '/')):
                            source_candidates.append(expand(path, origin, executable) / value[7:])
                source_candidates.append(origin.parent / value[7:])
            elif value.startswith('@loader_path/'):
                source_candidates.append(origin.parent / value[len('@loader_path/'):])
            for candidate in source_candidates:
                if candidate.is_file():
                    return self.include(candidate)
        raise ValueError(f'unresolved relocation input: {image}: {value}')

    def run(self):
        processed = set()
        while True:
            pending = [p for p in inventory(self.bundle, check_qt_conf=False) if p not in processed]
            if not pending:
                break
            for image in pending:
                text = inspect(image)
                metadata = parse_load_commands(text)
                paths = list(dict.fromkeys(p for info in metadata.values() for p in info['rpaths']))
                args, changes = [], []
                dependencies = dict.fromkeys(d for info in metadata.values() for d in info['dependencies'])
                for old in dependencies:
                    target = self.dependency(old, image, paths)
                    if target:
                        new = '@loader_path/' + os.path.relpath(target, image.parent)
                        if old != new:
                            args += ['-change', old, new]
                            changes.append({'from': old, 'to': new})
                for path in paths:
                    try:
                        portable = inside(expand(path, image, executable_for(image, self.bundle)), self.bundle)
                    except ValueError:
                        portable = False
                    if not portable:
                        args += ['-delete_rpath', path]
                # Relative RPATH also supports a library loaded by name at runtime.
                local = '@loader_path/' + os.path.relpath(self.frameworks, image.parent)
                if local not in paths:
                    args += ['-add_rpath', local]
                if re.search(r'^\s*cmd LC_ID_DYLIB\s*$', text, re.M):
                    args += ['-id', '@rpath/' + os.path.relpath(image, self.frameworks)]
                if args:
                    subprocess.run(['install_name_tool', *args, str(image)], check=True)
                processed.add(image)
                if changes:
                    self.records.append({'image': str(image.relative_to(self.bundle)), 'rewrites': changes})
        for record in self.records:
            if 'target' in record:
                record['target_sha256'] = digest(self.bundle / record['target'])
        return self.records
