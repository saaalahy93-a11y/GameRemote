#!/usr/bin/env python3
"""Prepare or sign an MSIX from a deployed Qt directory. Never submits/publishes."""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PureWindowsPath

FOUNDATION = 'http://schemas.microsoft.com/appx/manifest/foundation/windows10'
UAP = 'http://schemas.microsoft.com/appx/manifest/uap/windows10'
DESKTOP = 'http://schemas.microsoft.com/appx/manifest/desktop/windows10'
RESCAP = 'http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities'


def contained_file(root, relative):
    path = PureWindowsPath(relative)
    if path.is_absolute() or path.drive or '..' in path.parts or not path.parts:
        raise ValueError(f'unsafe package path: {relative}')
    candidate = root.joinpath(*path.parts)
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'missing/escaping package file: {relative}')
    return candidate


def prepare(source, stage, identity):
    package_name, publisher, display, version, arch, executable, logo = [identity[x] for x in
        ('name', 'publisher', 'display_name', 'version', 'arch', 'executable', 'logo')]
    webengine = identity.get('webengine', 'enabled')
    if webengine not in ('enabled', 'disabled'):
        raise ValueError('WebEngine selection must be enabled or disabled')
    if not re.fullmatch(r'[A-Za-z0-9.-]{3,50}', package_name):
        raise ValueError('invalid package identity name')
    if not publisher.startswith('CN=') or not publisher.strip() or not display.strip() or not identity['publisher_display_name'].strip():
        raise ValueError('explicit certificate publisher and product display name required')
    if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', version) or any(int(x) > 65535 for x in version.split('.')):
        raise ValueError('version must have four components in range 0..65535')
    if PureWindowsPath(executable).parent != PureWindowsPath('.'):
        raise ValueError('main executable must be in deployment root for deterministic DLL resolution')
    if arch not in ('x64', 'arm64'):
        raise ValueError('architecture must be x64 or arm64')
    if not source.is_dir() or source.is_symlink() or source.resolve() == stage.resolve():
        raise ValueError('deployment source must be a real separate directory')
    if stage.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(stage.resolve()):
        raise ValueError('source and staging directories must not overlap')
    for path in source.rglob('*'):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError(f'links are not allowed in deployed package: {path}')
    required = [executable, logo, identity['logo_44'], identity['logo_150'], 'COPYING', 'THIRD_PARTY_NOTICES.txt', 'SOURCE_OFFER.txt',
                'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Qml.dll', 'Qt6Quick.dll', 'platforms/qwindows.dll']
    if webengine == 'enabled':
        required.extend(('Qt6WebEngineCore.dll', 'QtWebEngineProcess.exe'))
    for path in required:
        contained_file(source, path)
    # Metadata/assets must be prepared by the release owner, never synthesized as production identity.
    for name, dimensions in ((logo, (50, 50)), (identity['logo_44'], (44, 44)), (identity['logo_150'], (150, 150))):
        asset = contained_file(source, name)
        with asset.open('rb') as stream:
            header = stream.read(24)
        if asset.suffix.lower() != '.png' or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR' or len(header) != 24 or struct.unpack('>II', header[16:24]) != dimensions:
            raise ValueError(f'logo must be a prepared {dimensions[0]}x{dimensions[1]} PNG: {name}')
    for name in ('COPYING', 'THIRD_PARTY_NOTICES.txt', 'SOURCE_OFFER.txt'):
        if contained_file(source, name).stat().st_size == 0:
            raise ValueError(f'empty release notice: {name}')
    shutil.copytree(source, stage)
    try:
        for prefix, uri in (('', FOUNDATION), ('uap', UAP), ('desktop', DESKTOP), ('rescap', RESCAP)):
            ET.register_namespace(prefix, uri)
        def add(parent, tag, attrs=None):
            namespace, _, local = tag.partition(':')
            uri = {'uap': UAP, 'desktop': DESKTOP, 'rescap': RESCAP}.get(namespace, FOUNDATION)
            return ET.SubElement(parent, '{' + uri + '}' + (local or namespace), attrs or {})
        package = ET.Element('{' + FOUNDATION + '}Package', {'IgnorableNamespaces': 'uap rescap'})
        add(package, 'Identity', {'Name': package_name, 'Publisher': publisher, 'Version': version, 'ProcessorArchitecture': arch})
        props = add(package, 'Properties')
        add(props, 'DisplayName').text = display
        add(props, 'PublisherDisplayName').text = identity['publisher_display_name']
        add(props, 'Logo').text = logo.replace('/', '\\')
        deps = add(package, 'Dependencies')
        add(deps, 'TargetDeviceFamily', {'Name': 'Windows.Desktop', 'MinVersion': '10.0.19041.0', 'MaxVersionTested': '10.0.26100.0'})
        resources = add(package, 'Resources')
        add(resources, 'Resource', {'Language': 'en-us'})
        apps = add(package, 'Applications')
        app = add(apps, 'Application', {'Id': 'App', 'Executable': executable.replace('/', '\\'), 'EntryPoint': 'Windows.FullTrustApplication'})
        add(app, 'uap:VisualElements', {'DisplayName': display, 'Description': display, 'BackgroundColor': 'transparent',
                                     'Square150x150Logo': identity['logo_150'].replace('/', '\\'), 'Square44x44Logo': identity['logo_44'].replace('/', '\\')})
        capabilities = add(package, 'Capabilities')
        add(capabilities, 'Capability', {'Name': 'internetClient'})
        add(capabilities, 'rescap:Capability', {'Name': 'runFullTrust'})
        ET.ElementTree(package).write(stage / 'AppxManifest.xml', encoding='utf-8', xml_declaration=True)
    except Exception:
        shutil.rmtree(stage)
        raise


def validate_dlls(stage, system_dlls, dumpbin='dumpbin'):
    """Require every static/delay import to be packaged or explicitly OS-provided."""
    approved = {name.lower() for name in system_dlls}
    if not approved or any(not re.fullmatch(r'[A-Za-z0-9_.-]+\.dll', x) for x in approved):
        raise ValueError('reviewed nonempty OS DLL allowlist required')
    images = [p for p in stage.rglob('*') if p.suffix.lower() in ('.dll', '.exe')]
    for image in images:
        output = subprocess.check_output([dumpbin, '/DEPENDENTS', str(image)], text=True)
        if 'Image has the following dependencies:' not in output and 'Image has the following delay load dependencies:' not in output:
            raise ValueError(f'cannot establish DLL dependency inventory: {image}')
        imports = re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$', output, re.MULTILINE | re.IGNORECASE)
        for name in imports:
            if name.lower() in approved or name.lower().startswith(('api-ms-win-', 'ext-ms-win-')):
                continue
            # Windows loader: importing image directory then main executable directory.
            found = any(any(p.name.lower() == name.lower() and p.is_file() for p in directory.iterdir())
                        for directory in (image.parent, stage))
            if not found:
                raise ValueError(f'missing runtime DLL: {image.relative_to(stage)}: {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    for field in ('name', 'publisher', 'display-name', 'publisher-display-name', 'version', 'executable', 'logo', 'logo-44', 'logo-150'):
        parser.add_argument('--' + field, required=True)
    parser.add_argument('--arch', choices=('x64', 'arm64'), required=True)
    parser.add_argument('--webengine', choices=('enabled', 'disabled'), default='enabled',
                        help='match the deployed build; disabled permits builds without Qt WebEngine (default: enabled)')
    parser.add_argument('--prepare-only', action='store_true', help='create an unsigned input directory; no MSIX')
    parser.add_argument('--system-dlls', type=Path, help='JSON list of reviewed OS-provided DLL filenames')
    parser.add_argument('--certificate-thumbprint', help='existing CurrentUser certificate store SHA1 identifier; never a PFX/password')
    parser.add_argument('--timestamp-url', help='approved RFC3161 timestamp URL')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if not args.prepare_only:
            if os.name != 'nt' or not args.certificate_thumbprint or not args.output or not args.system_dlls or not args.timestamp_url:
                raise ValueError('signed packaging requires Windows, output, certificate thumbprint, timestamp URL and OS DLL inventory')
            if not re.fullmatch(r'[A-Fa-f0-9]{40}', args.certificate_thumbprint):
                raise ValueError('invalid certificate thumbprint')
            if not args.timestamp_url.startswith('https://'):
                raise ValueError('timestamp URL must be HTTPS')
            if args.output.exists() or args.output.suffix.lower() != '.msix':
                raise ValueError('output must be a new .msix path')
            if args.output.resolve().is_relative_to(args.stage.resolve()):
                raise ValueError('package output must be outside staging directory')
            for command in ('MakeAppx.exe', 'SignTool.exe', 'dumpbin'):
                if not shutil.which(command):
                    raise ValueError(f'missing Windows SDK/MSVC tool: {command}')
        prepare(args.deployment, args.stage, vars(args))
        if args.prepare_only:
            print(f'Prepared unsigned package inputs: {args.stage}; runtime DLLs/signing not validated')
            return 0
        validate_dlls(args.stage, json.loads(args.system_dlls.read_text()))
        try:
            subprocess.run(['MakeAppx.exe', 'pack', '/v', '/h', 'SHA256', '/d', str(args.stage), '/p', str(args.output)], check=True)
            subprocess.run(['SignTool.exe', 'sign', '/fd', 'SHA256', '/sha1', args.certificate_thumbprint,
                            '/tr', args.timestamp_url, '/td', 'SHA256', str(args.output)], check=True)
            subprocess.run(['SignTool.exe', 'verify', '/pa', '/v', str(args.output)], check=True)
        except Exception:
            args.output.unlink(missing_ok=True)  # Never leave an unsigned/failed artifact labelled as ready.
            raise
        print(f'Signed and signature-verified: {args.output}; installation/runtime not validated')
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
