#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
case "${1:-}" in
  --store-config)
    [ "$#" -eq 1 ] || { echo 'Usage: preflight.sh [--store-config]' >&2; exit 2; }
    # Pure public-metadata validation: no Xcode, network, signing or account access.
    host_python=${CHIAKI_HOST_PYTHON:-$(command -v python3)}
    exec "$host_python" -I "$root/ios/scripts/release_config.py" --store --from-environment
    ;;
  '') [ "$#" -eq 0 ] || { echo 'Usage: preflight.sh [--store-config]' >&2; exit 2; } ;;
  *) echo 'Usage: preflight.sh [--store-config]' >&2; exit 2 ;;
esac
if ! xcrun --sdk iphoneos --show-sdk-path >/dev/null 2>&1 || ! xcrun --sdk iphonesimulator --show-sdk-path >/dev/null 2>&1; then
  echo 'Full Xcode with iPhoneOS and iPhoneSimulator SDKs is required; Command Line Tools alone cannot build this app.' >&2
  exit 2
fi
command -v cmake >/dev/null || { echo 'CMake 3.28+ is required' >&2; exit 2; }
host_python=${CHIAKI_HOST_PYTHON:-}
host_protoc=${CHIAKI_HOST_PROTOC:-}
if [ -z "$host_python" ]; then
  host_python=$(command -v python3) || { echo 'Python 3 is required for nanopb' >&2; exit 2; }
fi
if [ -z "$host_protoc" ]; then
  host_protoc=$(command -v protoc) || { echo 'Host protoc is required for nanopb generation' >&2; exit 2; }
fi
"$host_python" -I "$root/scripts/release/verify_host_tools.py" --python "$host_python" --protoc "$host_protoc"
echo 'iOS build prerequisites found (signing/account/device access is not checked).'
