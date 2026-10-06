#!/usr/bin/env python3
"""Exercise signing rejection paths without reading or creating signing credentials."""
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
environment = os.environ.copy()
for name in ('CHIAKI_KEYSTORE', 'CHIAKI_STORE_PASSWORD', 'CHIAKI_KEY_ALIAS', 'CHIAKI_KEY_PASSWORD'):
    environment.pop(name, None)
environment['CHIAKI_RELEASE_SIGNING'] = 'true'
cases = [
    (None, 'Signing requires a publisher-owned releaseApplicationId'),
    ('org.example.remoteplayprototype', 'Signing requires a publisher-owned releaseApplicationId'),
    ('com.metallic.chiaki', 'Signing requires a publisher-owned releaseApplicationId'),
    ('org.example.signingguardfixture', 'Missing required signing environment variable: CHIAKI_KEYSTORE'),
]
for application_id, expected in cases:
    command = ['./gradlew', '--no-daemon', '--max-workers=2', 'help']
    if application_id:
        command.append('-PreleaseApplicationId=' + application_id)
    result = subprocess.run(command, cwd=root / 'android', env=environment,
                            capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    print(output)
    if result.returncode == 0 or expected not in output:
        print(f'FAIL signing rejection for {application_id or "missing identity"}', file=sys.stderr)
        sys.exit(1)
    print(f'PASS signing rejection: {application_id or "missing identity"}')
print('All four signing guard checks passed; no credentials were supplied')
