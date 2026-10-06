#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
format=${1:-apk}
case "$format" in
  apk) task=assembleRelease; pattern='app-release*.apk' ;;
  aab) task=bundleRelease; pattern='app-release*.aab' ;;
  *) echo 'Usage: build.sh [apk|aab]' >&2; exit 2 ;;
esac
: "${ANDROID_HOME:=${ANDROID_SDK_ROOT:-}}"
: "${ANDROID_HOME:?Set ANDROID_HOME to the SDK containing API 36, NDK 28.2 and CMake 3.22.1}"
export ANDROID_HOME
: "${GRADLE_USER_HOME:=$root/android/.release-cache/gradle}"
export GRADLE_USER_HOME
export CMAKE_BUILD_PARALLEL_LEVEL=2
: "${CHIAKI_HOST_PYTHON:?Set CHIAKI_HOST_PYTHON to an absolute virtualenv interpreter with protobuf==5.29.6}"
: "${CHIAKI_HOST_PROTOC:?Set CHIAKI_HOST_PROTOC to the absolute pinned protoc 29.6 executable}"
"$CHIAKI_HOST_PYTHON" -I "$root/scripts/release/verify_host_tools.py" --python "$CHIAKI_HOST_PYTHON" --protoc "$CHIAKI_HOST_PROTOC"
"$CHIAKI_HOST_PYTHON" -I "$root/scripts/release/android/generate_notices.py" --check
# Nanopb's plugin uses /usr/bin/env python3 and may invoke protoc internally.
# Bind CMake variables as well as PATH; cached CMake discovery must not win.
export PATH="$(dirname "$CHIAKI_HOST_PYTHON"):$(dirname "$CHIAKI_HOST_PROTOC"):$PATH"
unset PYTHONHOME PYTHONPATH
if [[ "$format" == aab ]]; then
  : "${BUNDLETOOL_JAR:?Set BUNDLETOOL_JAR to the official pinned bundletool jar for AAB packaging validation}"
  [[ -f "$BUNDLETOOL_JAR" ]] || { echo 'Bundletool jar is missing' >&2; exit 1; }
fi
for package in platforms/android-36 build-tools/36.0.0 ndk/28.2.13676358 cmake/3.22.1; do
  [[ -d "$ANDROID_HOME/$package" ]] || { echo "Missing SDK package: $package" >&2; exit 1; }
done
# Gradle itself uses local.properties for SDK lookup. Do not let an unreviewed local
# properties file become a release input; this entry point requires explicit env.
[[ ! -e "$root/android/local.properties" ]] || { echo 'Release build requires a checkout without android/local.properties' >&2; exit 1; }
args=()
[[ -z "${CHIAKI_APPLICATION_ID:-}" ]] || args+=("-PreleaseApplicationId=$CHIAKI_APPLICATION_ID")
[[ -z "${CHIAKI_VERSION_CODE:-}" ]] || args+=("-PreleaseVersionCode=$CHIAKI_VERSION_CODE")
[[ -z "${CHIAKI_VERSION_NAME:-}" ]] || args+=("-PreleaseVersionName=$CHIAKI_VERSION_NAME")
cd "$root/android"
./gradlew --no-daemon --max-workers=2 ":app:$task" "${args[@]}"
if [[ "$format" == apk ]]; then directory=app/build/outputs/apk/release; else directory=app/build/outputs/bundle/release; fi
artifacts=()
while IFS= read -r artifact; do artifacts+=("$artifact"); done < <(find "$directory" -maxdepth 1 -name "$pattern" -type f)
[[ ${#artifacts[@]} -eq 1 ]] || { echo 'Expected exactly one release artifact; clean stale outputs' >&2; exit 1; }
"$CHIAKI_HOST_PYTHON" "$root/scripts/release/android/validate_native.py" "${artifacts[0]}" --sdk "$ANDROID_HOME"
