#!/bin/sh
# Real UI interaction on disposable simulators. Never registers with a console.
# Uses the simulator models selected by simulator-smoke.sh; deletes only devices created here.
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
app="$root/ios/build/package-verification/iphonesimulator/GameRemote.app"
out="$root/ios/build/ui-evidence"
smoke="$root/ios/build/simulator-evidence"
command -v maestro >/dev/null || { echo 'Pinned Maestro CLI is required' >&2; exit 2; }
[ -d "$app" ] || { echo 'Run the simulator build and package round-trip first' >&2; exit 2; }
mkdir -p "$out"
python3 - "$smoke" > "$out/models.tsv" <<'PY'
import json
from pathlib import Path
import sys

smoke = Path(sys.argv[1])
devices = json.loads((smoke / 'simctl-devices.json').read_text())['devices']
for row in (smoke / 'devices.tsv').read_text().splitlines():
    kind, udid, *_ = row.split('\t')
    selected = [(runtime, device) for runtime, entries in devices.items() for device in entries if device['udid'] == udid]
    if len(selected) != 1 or not selected[0][1].get('deviceTypeIdentifier'):
        sys.exit(f'Missing simulator model for {kind}')
    runtime, device = selected[0]
    print('\t'.join((kind, device['deviceTypeIdentifier'], runtime)))
PY
created=
cleanup() {
  if [ -n "$created" ]; then
    xcrun simctl shutdown "$created" >/dev/null 2>&1 || true
    xcrun simctl delete "$created"
    created=
  fi
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
export MAESTRO_CLI_NO_ANALYTICS=true MAESTRO_CLI_ANALYSIS_NOTIFICATION_DISABLED=true
tab=$(printf '\t')
while IFS="$tab" read -r kind model runtime <&3; do
  echo "Testing $kind navigation and input validation on a disposable simulator"
  created=$(xcrun simctl create "GameRemote UI verification ($kind)" "$model" "$runtime")
  xcrun simctl bootstatus "$created" -b </dev/null
  xcrun simctl install "$created" "$app" </dev/null
  xcrun simctl ui "$created" appearance light </dev/null
  mkdir -p "$out/$kind"
  maestro --device "$created" test --format junit --output "$out/$kind/report.xml" \
    --debug-output "$out/$kind/debug" --test-output-dir "$out/$kind" "$root/ios/tests/ui" </dev/null
  cleanup
done 3<"$out/models.tsv"
