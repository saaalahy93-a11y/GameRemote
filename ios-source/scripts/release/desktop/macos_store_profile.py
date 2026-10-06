#!/usr/bin/env python3
"""Prepare sandbox inputs or check a candidate read-only; never build, sign or launch."""
import argparse
import hashlib
import json
import plistlib
import re
import sys
from pathlib import Path
from xml.parsers.expat import ExpatError

from macos_validate import inside, inventory


TEMPLATE = Path(__file__).resolve().parents[3] / 'gui/entitlements-appstore.plist'
ENTITLEMENTS_NAME = 'GameRemote.appstore.entitlements'
INFO_NAME = 'InfoPlist.additions.plist'
REQUIRED_ENTITLEMENTS = frozenset('com.apple.security.' + key for key in (
    'app-sandbox', 'network.client', 'network.server', 'device.microphone',
    'device.audio-input', 'device.usb', 'device.bluetooth', 'files.user-selected.read-write',
))
INFO_ADDITIONS = {
    'NSMicrophoneUsageDescription': 'GameRemote uses your microphone for voice chat.',
    'NSBluetoothAlwaysUsageDescription': 'GameRemote connects to Bluetooth game controllers for remote play.',
    'NSLocalNetworkUsageDescription': 'GameRemote discovers and streams from your console on your local network.',
}
REMAINING_GATES = [
    'Bind the selected Qt build/configuration evidence to the exact deployed Qt binaries.',
    'Use native open/save panels for user-selected file access; qualify persistent access separately.',
    'Qualify sandboxed discovery, registration, streaming, controller input, microphone, settings and file operations.',
    'Review Steam integration and all writes outside the sandbox container; no broad exceptions are supplied.',
    'Verify signed entitlements for the app and any helper processes with the assigned publisher identity.',
    'Complete Xcode/SDK, signing/provisioning, receipt/distribution, licence and App Store validation requirements.',
]
SCOPE = ('Static preparation inputs only. No signature, provisioning, sandbox runtime, '
         'loader closure, private-API audit or App Store acceptance is established.')


class UniqueDict(dict):
    def __setitem__(self, key, value):
        if key in self:
            raise ValueError(f'duplicate plist key: {key!r}')
        super().__setitem__(key, value)


def read_plist(path):
    try:
        data = plistlib.loads(path.read_bytes(), dict_type=UniqueDict)
    except (plistlib.InvalidFileException, ExpatError, TypeError) as error:
        raise ValueError(f'invalid plist: {path}') from error
    if not isinstance(data, dict):
        raise ValueError(f'plist root must be a dictionary: {path}')
    return dict(data)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_entitlements(data):
    if set(data) != REQUIRED_ENTITLEMENTS:
        raise ValueError('entitlement keys must exactly match the reviewed sandbox profile; '
                         f'missing={sorted(REQUIRED_ENTITLEMENTS - set(data))}, '
                         f'unknown={sorted(set(data) - REQUIRED_ENTITLEMENTS)}')
    if any(value is not True for value in data.values()):
        raise ValueError('every sandbox entitlement must be the plist boolean true')


def validate_descriptions(data):
    for key in INFO_ADDITIONS:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f'missing or malformed privacy description: {key}')


def new_output(path):
    if path.exists() or path.is_symlink():
        raise ValueError(f'output already exists: {path}')
    resolved = path.resolve()
    if any(part.suffix.lower() == '.app' for part in (path, *path.parents, resolved, *resolved.parents)):
        raise ValueError('output must be outside every .app bundle')
    if not resolved.parent.is_dir():
        raise ValueError('output parent must be an existing directory')
    return resolved


def prepare(output, template=TEMPLATE):
    output = new_output(output)
    entitlements = read_plist(template)
    validate_entitlements(entitlements)
    output.mkdir()
    # Only these three small files are created. No app or source tree is copied.
    with (output / ENTITLEMENTS_NAME).open('xb') as stream:
        plistlib.dump(entitlements, stream)
    with (output / INFO_NAME).open('xb') as stream:
        plistlib.dump(INFO_ADDITIONS, stream)
    manifest = {
        'format': 1, 'distribution': 'mac-app-store', 'status': 'PREPARED_NOT_SIGNED',
        'files': {name: digest(output / name) for name in (ENTITLEMENTS_NAME, INFO_NAME)},
        'scope': SCOPE, 'remaining_gates': REMAINING_GATES,
    }
    with (output / 'profile.json').open('x') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')
    return manifest


def validate_profile(profile):
    if profile.is_symlink() or not profile.is_dir():
        raise ValueError('profile must be a real directory')
    if {path.name for path in profile.iterdir()} != {ENTITLEMENTS_NAME, INFO_NAME, 'profile.json'}:
        raise ValueError('profile must contain exactly its two plists and profile.json')
    for name in (ENTITLEMENTS_NAME, INFO_NAME, 'profile.json'):
        if (profile / name).is_symlink() or not (profile / name).is_file():
            raise ValueError(f'profile file must be a regular file: {name}')
    manifest = json.loads((profile / 'profile.json').read_text())
    if (not isinstance(manifest, dict) or type(manifest.get('format')) is not int
            or manifest.get('format') != 1 or manifest.get('distribution') != 'mac-app-store'):
        raise ValueError('unsupported sandbox profile format/distribution')
    if manifest.get('status') != 'PREPARED_NOT_SIGNED':
        raise ValueError('profile cannot claim signing or Store acceptance')
    expected = {name: digest(profile / name) for name in (ENTITLEMENTS_NAME, INFO_NAME)}
    if manifest.get('files') != expected:
        raise ValueError('profile file hashes do not match its manifest')
    validate_entitlements(read_plist(profile / ENTITLEMENTS_NAME))
    additions = read_plist(profile / INFO_NAME)
    if set(additions) != set(INFO_ADDITIONS):
        raise ValueError('profile privacy keys must exactly match the reviewed additions')
    validate_descriptions(additions)
    return expected


def qt_configuration(path):
    # This inspects the explicitly supplied generated qconfig.h. It does not prove
    # that an arbitrary header belongs to the Qt binaries inside the candidate.
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', path.read_text(), flags=re.S)
    flags = re.findall(r'^\s*#\s*define\s+QT_FEATURE_appstore_compliant\s+(-?\d+)\s*$', source, re.M)
    versions = re.findall(r'^\s*#\s*define\s+QT_VERSION_STR\s+"([0-9.]+)"\s*$', source, re.M)
    if flags != ['1']:
        raise ValueError('selected Qt qconfig.h must define QT_FEATURE_appstore_compliant exactly once as 1')
    if len(versions) != 1 or not re.fullmatch(r'6\.9\.\d+', versions[0]):
        raise ValueError('this profile requires explicit Qt 6.9.x configuration evidence')
    return {'version': versions[0], 'qconfig_sha256': digest(path),
            'scope': 'supplied header only; deployed binary provenance remains a release gate'}


def preflight(app, profile, qt_header, expected_bundle_id):
    if not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', expected_bundle_id):
        raise ValueError('expected bundle ID must be explicit reverse-DNS text')
    files = validate_profile(profile)
    failures = []
    result = {'app': str(app.resolve()), 'profile_files': files,
              'expected_bundle_id': expected_bundle_id, 'scope': SCOPE,
              'remaining_gates': REMAINING_GATES}
    try:
        images = inventory(app)
        result['mach_o_images_inventoried'] = len(images)
        webengine = sorted(str(path.relative_to(app.resolve())) for path in images
                           if 'qtwebengine' in str(path.relative_to(app.resolve())).lower())
        if webengine:
            failures.append('Qt WebEngine is incompatible with this Mac App Store profile: ' + ', '.join(webengine))
        info_path = app / 'Contents/Info.plist'
        info = read_plist(info_path)
        result['info_plist_sha256'] = digest(info_path)
        if info.get('CFBundleIdentifier') != expected_bundle_id:
            failures.append('candidate bundle ID differs from the explicitly selected bundle ID')
        for key in INFO_ADDITIONS:
            try:
                validate_descriptions({**INFO_ADDITIONS, key: info.get(key)})
            except ValueError as error:
                failures.append(str(error))
    except (ValueError, OSError) as error:
        failures.append(str(error))
    try:
        result['qt_configuration'] = qt_configuration(qt_header)
    except (ValueError, OSError) as error:
        failures.append(str(error))
    result['failures'] = failures
    result['status'] = 'PREFLIGHT_BLOCKED' if failures else 'PREFLIGHT_INPUTS_PASS'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('prepare', help='write three small unsigned profile input files')
    create.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('preflight', help='read candidate/profile/configuration; record blockers')
    for name in ('app', 'profile', 'qt-config-header', 'report'):
        check.add_argument('--' + name, type=Path, required=True)
    check.add_argument('--expected-bundle-id', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            result = prepare(args.output)
        else:
            report = new_output(args.report)
            if inside(report, args.app) or inside(report, args.profile):
                raise ValueError('report must be outside candidate and profile')
            result = preflight(args.app, args.profile, args.qt_config_header, args.expected_bundle_id)
            with report.open('x') as stream:
                json.dump(result, stream, indent=2)
                stream.write('\n')
        print(result['status'] + ': ' + SCOPE)
        for failure in result.get('failures', []):
            print('BLOCKER: ' + failure)
        return 1 if result['status'] == 'PREFLIGHT_BLOCKED' else 0
    except (ValueError, OSError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
