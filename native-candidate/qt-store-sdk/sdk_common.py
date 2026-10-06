"""Standard-library helpers for the public Qt SDK builder; no app-source reader."""

import hashlib
import json
import os
import re
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
MAX_DOWNLOAD_BYTES = 100_000_000


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_lock() -> dict:
    return json.loads((ROOT / 'dependencies.lock.json').read_text())


def sha256(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('required SHA-256 pin is missing or invalid')
    return value


def fetch(spec: dict, downloads: Path) -> Path:
    expected = sha256(spec.get('sha256'))
    url = spec['url']
    if not url.startswith('https://'):
        raise ValueError('download must use HTTPS')
    name = spec['filename']
    if not name or Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('invalid download filename')
    downloads.mkdir(parents=True, exist_ok=True)
    target = downloads / name
    if target.exists():
        if digest(target) != expected:
            raise ValueError(f'cached archive checksum mismatch: {name}')
        return target
    partial = target.with_name(name + '.partial')
    if partial.exists():
        raise ValueError(f'partial download already exists: {partial}')
    try:
        with urllib.request.urlopen(url, timeout=60) as response, partial.open('xb') as out:
            received = 0
            while block := response.read(1024 * 1024):
                received += len(block)
                if received > MAX_DOWNLOAD_BYTES:
                    raise ValueError('SDK tool/header download exceeds 100 MB bound')
                out.write(block)
        if digest(partial) != expected:
            raise ValueError(f'download checksum mismatch: {name}')
        partial.rename(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def run(command: list[str], *, cwd: Path | None = None, env: dict | None = None,
        timeout: int = 3600) -> None:
    print('+ ' + ' '.join(str(x) for x in command), flush=True)
    subprocess.run([str(x) for x in command], cwd=cwd, env=env, check=True, timeout=timeout)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + '\n')


def unpack(archive: Path, destination: Path) -> None:
    """Only called after verifying a dependency's committed SHA-256 pin."""
    destination.mkdir(parents=True, exist_ok=True)
    if archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                path = PurePosixPath(name.replace('\\', '/'))
                if path.is_absolute() or '..' in path.parts or ':' in name:
                    raise ValueError('unsafe dependency ZIP path')
            source.extractall(destination)
    elif archive.name.endswith('.tar.gz'):
        with tarfile.open(archive) as source:
            source.extractall(destination, filter='data')
    else:
        raise ValueError('unsupported dependency archive')


def tools_for(platform: str, work: Path) -> dict[str, Path]:
    result = {}
    lock = read_lock()['tools']
    for name in ('cmake', 'ninja'):
        dest = work / 'tools' / name
        unpack(fetch(lock[f'{name}-{platform}'], work / 'downloads'), dest)
        matches = list(dest.rglob(name + ('.exe' if platform == 'windows' else '')))
        matches = [p for p in matches if p.is_file() and (name == 'ninja' or p.parent.name == 'bin')]
        if len(matches) != 1:
            raise ValueError(f'cannot locate unique {name} in verified archive')
        matches[0].chmod(matches[0].stat().st_mode | 0o111)
        result[name] = matches[0]
    os.environ['PATH'] = os.pathsep.join([str(p.parent) for p in result.values()] + [os.environ['PATH']])
    return result
