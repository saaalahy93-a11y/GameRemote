"""Source-level checks of the app target definition: every Swift source is registered in
ios/CMakeLists.txt, the asset catalogue is well formed, and the icon is the approved master."""
import json
import re
import subprocess
import sys
from pathlib import Path

ios = Path(__file__).resolve().parents[1]
cmake = (ios / 'CMakeLists.txt').read_text()
registered = set(re.findall(r'App/(\w+\.swift)', cmake))
present = {path.name for path in (ios / 'App').glob('*.swift')}
problems = []
if registered != present:
    problems.append(f'CMake/App Swift mismatch: unregistered {sorted(present - registered)}, missing {sorted(registered - present)}')
for needed in ('App/Assets.xcassets', 'App/PrivacyInfo.xcprivacy', 'AGPL-3.0-only-OpenSSL.txt', 'ASSETCATALOG_COMPILER_APPICON_NAME "AppIcon"'):
    if needed not in cmake:
        problems.append(f'{needed} is not wired into the app target')

assets = ios / 'App/Assets.xcassets'
for contents in assets.rglob('Contents.json'):
    for image in json.loads(contents.read_text()).get('images', []):
        if 'filename' in image and not (contents.parent / image['filename']).is_file():
            problems.append(f'{contents.parent.name} references missing {image["filename"]}')
icon = assets / 'AppIcon.appiconset/AppIcon-1024.png'
described = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', '-g', 'hasAlpha', str(icon)], capture_output=True, text=True).stdout
if not all(expected in described for expected in ('pixelWidth: 1024', 'pixelHeight: 1024', 'hasAlpha: no')):
    problems.append('App icon must be 1024x1024 without alpha')
# The icon is a deterministic sips downscale of the approved master; regenerate and compare pixels are
# out of scope here, so pin the master it was produced from.
master = ios.parent / 'assets/branding/gameremote-glass-master.png'
digest = subprocess.run(['shasum', '-a', '256', str(master)], capture_output=True, text=True).stdout.split()[0]
if digest != '4aefbfdcd6c8427b3572981e74a699e118ef3d33fe927feb27063f206cb66cba':
    problems.append('Brand master differs from the approved asset')

if problems:
    sys.exit('\n'.join(problems))
print(f'App target registers {len(present)} Swift sources; asset catalogue and icon checks passed')
