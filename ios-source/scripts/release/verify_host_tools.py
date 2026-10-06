#!/usr/bin/env python3
"""Check an explicitly selected protoc/Python pair, then generate and import a probe."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROTOC_VERSION = '29.6'
PYTHON_PROTOBUF_VERSION = '5.29.6'


def executable(path: str) -> str:
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('Host tool must be an absolute path to an executable: ' + str(path))
    # Preserve the virtualenv's interpreter path; resolving its symlink loses the venv.
    return str(path)


def verify(python: str, protoc: str) -> None:
    python, protoc = executable(python), executable(protoc)
    compiler = subprocess.run([protoc, '--version'], check=True, capture_output=True, text=True).stdout.strip()
    if compiler != 'libprotoc ' + PROTOC_VERSION:
        raise ValueError('Expected protoc ' + PROTOC_VERSION + '; found ' + compiler)
    runtime = subprocess.run(
        [python, '-I', '-c', 'import google.protobuf,json; print(json.dumps(google.protobuf.__version__))'],
        check=True, capture_output=True, text=True,
    ).stdout
    if json.loads(runtime) != PYTHON_PROTOBUF_VERSION:
        raise ValueError('Expected Python google.protobuf ' + PYTHON_PROTOBUF_VERSION + '; found ' + runtime.strip())
    with tempfile.TemporaryDirectory(prefix='chiaki-protobuf-probe-') as directory:
        source = Path(directory) / 'probe.proto'
        source.write_text('syntax = "proto3"; message Probe { string marker = 1; }\n')
        subprocess.run([protoc, '-I' + directory, '--python_out=' + directory, str(source)], check=True)
        subprocess.run([
            python, '-I', '-c',
            ('import sys; sys.path.insert(0,sys.argv[1]); import probe_pb2; '
             'assert probe_pb2.Probe(marker="compatible").marker == "compatible"'), directory,
        ], check=True)
    print('PASS host protoc 29.6 / Python protobuf 5.29.6; generated module imported successfully')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True)
    parser.add_argument('--protoc', required=True)
    args = parser.parse_args()
    try:
        verify(args.python, args.protoc)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('FAIL host code-generation preflight: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
