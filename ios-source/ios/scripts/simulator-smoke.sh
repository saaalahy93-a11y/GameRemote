#!/bin/sh
# Installs and launches the unsigned simulator build on one iPhone and one 13-inch iPad and
# captures light, dark and largest-text screenshots plus evidence.json. Requires full Xcode.
# It proves install + launch + first frame only; never device behaviour, networking or playback.
# Usage: simulator-smoke.sh [path-to-.app] [output-dir]
# Env:   SMOKE_IOS_VERSION=18.5 restricts the simulator runtime (default: newest installed iOS);
#        SMOKE_DEVICE_KIND=iphone or ipad restricts the device family (default: both);
#        SMOKE_WAIT=<seconds> settles the app after each launch (default 6).
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
die() { echo "simulator-smoke: $*" >&2; exit 2; }
status=0
fail() { echo "simulator-smoke: FAIL: $*" >&2; status=1; }

[ $# -le 2 ] || die 'Usage: simulator-smoke.sh [path-to-.app] [output-dir]'
xcrun --find simctl >/dev/null 2>&1 || die 'xcrun simctl not found; full Xcode with an iOS simulator runtime is required.'
command -v python3 >/dev/null || die 'python3 is required to parse simctl JSON'
wait_s=${SMOKE_WAIT:-6}
case "$wait_s" in ''|*[!0-9]*) die "SMOKE_WAIT must be whole seconds, got '$wait_s'";; esac

app=${1:-}
out=${2:-"$root/ios/build/simulator-evidence"}
if [ -z "$app" ]; then
  app="$root/ios/build/iphonesimulator/Debug-iphonesimulator/GameRemote.app"
  if [ ! -d "$app" ]; then
    app=$(find "$root/ios/build/iphonesimulator" -type d -name GameRemote.app 2>/dev/null | head -n 1)
    [ -n "$app" ] || die "No GameRemote.app under $root/ios/build/iphonesimulator; run ios/scripts/build.sh iphonesimulator first."
    echo "Default app path is missing; using $app"
  fi
fi
[ -f "$app/Info.plist" ] || die "Not an app bundle (no Info.plist): $app"
app=$(CDPATH='' cd -- "$app" && pwd)
mkdir -p "$out"
out=$(CDPATH='' cd -- "$out" && pwd)

plist() { /usr/libexec/PlistBuddy -c "Print :$1" "$app/Info.plist" 2>/dev/null; }
bundle_id=$(plist CFBundleIdentifier) || die "CFBundleIdentifier is missing from $app/Info.plist"
exe_name=$(plist CFBundleExecutable) || die "CFBundleExecutable is missing from $app/Info.plist"
# shellcheck disable=SC2016
case "$bundle_id|$exe_name" in '|'*|*'|'|*'$('*) die "Info.plist is not a processed build product (id='$bundle_id', executable='$exe_name')";; esac
[ -f "$app/$exe_name" ] || die "App executable is missing: $app/$exe_name"
archs=$(xcrun lipo -archs "$app/$exe_name") || die "lipo could not read $app/$exe_name"
host_arch=$(uname -m)
case " $archs " in *" $host_arch "*) ;; *) fail "executable architectures ($archs) do not include host $host_arch";; esac
echo "App: $app ($bundle_id, $archs)"

xcrun simctl list devices available -j >"$out/simctl-devices.json" || die 'xcrun simctl list failed'
SMOKE_IOS_VERSION=${SMOKE_IOS_VERSION:-} SMOKE_DEVICE_KIND=${SMOKE_DEVICE_KIND:-} python3 - "$out/simctl-devices.json" >"$out/devices.tsv" <<'PY' || die "No usable requested simulators; see $out/simctl-devices.json"
import json, os, re, sys
want = os.environ.get("SMOKE_IOS_VERSION", "")
kind_filter = os.environ.get("SMOKE_DEVICE_KIND", "")
if kind_filter not in ("", "iphone", "ipad"):
    sys.exit("SMOKE_DEVICE_KIND must be iphone, ipad, or empty for both")
kinds = (kind_filter,) if kind_filter else ("iphone", "ipad")
best = {}
for runtime, devices in json.load(open(sys.argv[1], encoding="utf-8"))["devices"].items():
    match = re.search(r"SimRuntime\.iOS-(\d+(?:-\d+)*)$", runtime)
    if not match:
        continue
    version = tuple(int(part) for part in match.group(1).split("-"))
    text = ".".join(str(part) for part in version)
    if want and text != want and not text.startswith(want + "."):
        continue
    for device in devices:
        name = device.get("name", "")
        device_type = device.get("deviceTypeIdentifier") or ""
        kind_source = device_type + " " + name
        kind = "iphone" if "iPhone" in kind_source else "ipad" if "iPad" in kind_source else None
        if kind is None or device.get("isAvailable") is False or not device.get("udid"):
            continue
        # App Store's required iPad capture family is 13-inch. Never silently use
        # an 11-inch layout and label it a store-sized capture.
        if kind == "ipad" and not re.match(
                r"^com\.apple\.CoreSimulator\.SimDeviceType\.iPad-(Pro|Air)-13-inch(?:-|$)", device_type):
            continue
        model = re.search(r"iPhone (\d+)", name)
        # Newest runtime wins. iPhone: not Pro Max, newest numbered model, Pro before Plus/e/SE.
        # iPad: a 13-inch Pro before Air. Name breaks ties deterministically.
        if kind == "iphone":
            rank = (version, "Pro Max" not in name, int(model.group(1)) if model else 0, name.endswith(" Pro"), name)
        else:
            rank = (version, "iPad-Pro-" in device_type, True, False, name)
        if kind not in best or rank > best[kind][0]:
            best[kind] = (rank, device["udid"], device.get("state") or "Unknown", text, name)
missing = [kind for kind in kinds if kind not in best]
if missing:
    sys.exit("simulator-smoke: no available iOS %s simulator: %s" % (want or "(any)", ", ".join(missing)))
for kind in kinds:
    print("\t".join((kind,) + best[kind][1:]))
PY

tab=$(printf '\t')
stamp="$out/.smoke-started"
: >"$stamp"; : >"$out/captures.tsv"
booted=
# Shuts down only a simulator this script booted; one that was already Booted is left running.
cleanup() { [ -z "$booted" ] || xcrun simctl shutdown "$booted" >/dev/null 2>&1 || true; booted=; }
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

record() { printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$kind" "$name" "$udid" "$runtime" "$1" "$2" "$3" "$4" >>"$out/captures.tsv"; }
diagnostics() {
  xcrun simctl spawn "$udid" log show --predicate "process == \"$exe_name\"" --last 1m --style compact \
    >"$out/$1-log.txt" 2>&1 </dev/null || echo "simulator-smoke: log show failed for $1" >&2
}
# A simulator app is an ordinary host process, so the pid printed by `simctl launch` is a host pid.
# It counts as running if the simulator's launchd lists the launched pid.
# This avoids inspecting process arguments, which can contain unrelated secrets.
is_running() {
  xcrun simctl spawn "$udid" launchctl list 2>/dev/null </dev/null | awk -v p="$1" '$1 == p { f = 1 } END { exit !f }'
}
capture() {
  label="$kind-$1"; shot="$label.png"; pid=; running=false; launched=
  rm -f "$out/$shot"
  echo "$label: terminating any previous app instance"
  xcrun simctl terminate "$udid" "$bundle_id" >/dev/null 2>&1 </dev/null || true
  # Prints "<bundle id>: <pid>" on success.
  echo "$label: launching app"
  if launched=$(xcrun simctl launch "$udid" "$bundle_id" 2>"$out/$label-launch.err" </dev/null); then
    pid=${launched##*: }
    case "$pid" in ''|*[!0-9]*) pid=;; esac
  fi
  [ -s "$out/$label-launch.err" ] || rm -f "$out/$label-launch.err"
  echo "$label: launch returned pid=${pid:-none}; settling for ${wait_s}s"
  sleep "$wait_s"
  echo "$label: checking launched process"
  if [ -n "$pid" ] && is_running "$pid"; then running=true; fi
  echo "$label: process running=$running; capturing screen"
  xcrun simctl io "$udid" screenshot "$out/$shot" </dev/null || { fail "screenshot failed for $label"; shot=; }
  if [ "$running" != true ]; then
    fail "$bundle_id is not running on $name ($1) ${wait_s}s after launch; launch output: ${launched:-none}"
    diagnostics "$label"
  fi
  record "$1" "$shot" "$pid" "$running"
  echo "$label: pid=${pid:-none} running=$running screenshot=${shot:-none}"
}

while IFS="$tab" read -r kind udid state runtime name <&3; do
  echo "== $kind: $name, iOS $runtime, $udid (initially $state)"
  [ "$state" = Booted ] || booted=$udid
  # bootstatus -b boots the device if needed and blocks until it is ready for installs and launches.
  xcrun simctl bootstatus "$udid" -b </dev/null || { fail "could not boot $name"; record boot-failed '' '' false; cleanup; continue; }
  echo "$kind: boot complete; installing app"
  xcrun simctl install "$udid" "$app" </dev/null || {
    fail "install failed on $name"; record install-failed '' '' false; diagnostics "$kind-install"; cleanup; continue; }
  echo "$kind: app installed"
  for look in light dark; do
    echo "$kind: setting $look appearance"
    xcrun simctl ui "$udid" appearance "$look" </dev/null || fail "could not set $look appearance on $name"
    capture "$look"
  done
  xcrun simctl ui "$udid" appearance light </dev/null || fail "could not restore light appearance on $name"
  echo "$kind: setting largest text size"
  xcrun simctl ui "$udid" content_size accessibility-extra-extra-extra-large </dev/null || fail "could not set largest text size on $name"
  capture accessibility-xxxl
  # "large" is the iOS default Dynamic Type size.
  xcrun simctl ui "$udid" content_size large </dev/null || fail "could not reset text size on $name"
  xcrun simctl terminate "$udid" "$bundle_id" >/dev/null 2>&1 </dev/null || true
  cleanup
done 3<"$out/devices.tsv"

if [ "$status" -ne 0 ]; then
  sleep 5 # crash reports for simulator processes are written to the host asynchronously
  find "$HOME/Library/Logs/DiagnosticReports" -type f -name "*$exe_name*" -newer "$stamp" -exec cp {} "$out/" \; 2>/dev/null || true
fi
rm -f "$stamp"

xcode=$(xcodebuild -version 2>/dev/null | tr '\n' ' ' | sed 's/ *$//')
sdk=$(xcrun --sdk iphonesimulator --show-sdk-version 2>/dev/null) || sdk=
python3 - "$out" "${xcode:-unknown}" "${sdk:-unknown}" "$host_arch" "$app" "$bundle_id" "$exe_name" "$archs" "$status" <<'PY' || fail 'could not write evidence.json'
import json, os, sys
out, xcode, sdk, host_arch, app, bundle_id, executable, archs, status = sys.argv[1:10]
devices = {}
with open(os.path.join(out, "captures.tsv"), encoding="utf-8") as rows:
    for row in rows.read().splitlines():
        kind, name, udid, runtime, variant, shot, pid, running = row.split("\t")
        device = devices.setdefault(udid, {"kind": kind, "name": name, "udid": udid, "runtime": "iOS " + runtime, "captures": []})
        device["captures"].append({"variant": variant, "screenshot": shot or None, "pid": int(pid) if pid else None, "running": running == "true"})
evidence = {
    "passed": status == "0", "scope": "unsigned simulator build: install, launch and first frame only",
    "xcode": xcode, "simulatorSdk": sdk, "hostArchitecture": host_arch, "appPath": app, "bundleIdentifier": bundle_id,
    "executable": executable, "executableArchitectures": archs.split(), "devices": list(devices.values()),
}
with open(os.path.join(out, "evidence.json"), "w", encoding="utf-8") as handle:
    json.dump(evidence, handle, indent=2)
    handle.write("\n")
PY

[ "$status" -eq 0 ] || { echo "simulator-smoke: FAILED; screenshots, evidence.json and diagnostics are in $out" >&2; exit 1; }
echo "Simulator smoke passed for every selected device; evidence in $out"
