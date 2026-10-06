#!/bin/sh
set -eu
sdk=${1:-iphonesimulator}
case "$sdk" in iphoneos|iphonesimulator) ;; *) echo 'Usage: build.sh [iphoneos|iphonesimulator]' >&2; exit 2;; esac
root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
"$root/ios/scripts/preflight.sh"
if [ ! -f "$root/third-party/curl/CMakeLists.txt" ]; then
  echo 'Initialize pinned submodules first: git submodule update --init --recursive' >&2; exit 2
fi
build="$root/ios/build/$sdk"
configuration=${GR_IOS_CONFIGURATION:-Debug}
case "$configuration" in Debug|Release) ;; *) echo 'GR_IOS_CONFIGURATION must be Debug or Release' >&2; exit 2;; esac
architecture=arm64
[ "$sdk" != iphonesimulator ] || architecture=$(uname -m)
jobs=${CMAKE_BUILD_PARALLEL_LEVEL:-2}
case "$jobs" in ''|*[!0-9]*|0) echo 'CMAKE_BUILD_PARALLEL_LEVEL must be a positive integer' >&2; exit 2;; esac
host_python=${CHIAKI_HOST_PYTHON:-$(command -v python3)}
host_protoc=${CHIAKI_HOST_PROTOC:-$(command -v protoc)}
PATH="$(dirname "$host_python"):$(dirname "$host_protoc"):$PATH"
export PATH
unset PYTHONHOME PYTHONPATH
echo "Configuring $sdk / $architecture ($configuration)"
cmake -S "$root/ios" -B "$build" -G Xcode \
  -DCMAKE_TOOLCHAIN_FILE="$root/ios/cmake/ios.cmake" \
  -DCMAKE_OSX_SYSROOT="$sdk" -DCMAKE_OSX_ARCHITECTURES="$architecture" \
  -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO \
  -DCHIAKI_IOS_STORE_RELEASE=OFF \
  -DCHIAKI_IOS_BUNDLE_IDENTIFIER="${GR_IOS_BUNDLE_IDENTIFIER-org.example.RemotePlayPrototype.iOS}" \
  -DCHIAKI_IOS_DEVELOPMENT_TEAM="${GR_IOS_DEVELOPMENT_TEAM-}" \
  -DCHIAKI_IOS_VERSION="${GR_IOS_VERSION-1.10.0}" \
  -DCHIAKI_IOS_BUILD_NUMBER="${GR_IOS_BUILD_NUMBER-2}" \
  -DCHIAKI_IOS_PRIVACY_URL="${GR_IOS_PRIVACY_URL-}" \
  -DCHIAKI_IOS_SUPPORT_URL="${GR_IOS_SUPPORT_URL-}" \
  -DCHIAKI_IOS_SOURCE_URL="${GR_IOS_SOURCE_URL-}" \
  -DCHIAKI_IOS_EXPORT_CLASSIFICATION="${GR_IOS_EXPORT_CLASSIFICATION-}" \
  -DPYTHON_EXECUTABLE="$host_python" -DPython_EXECUTABLE="$host_python" \
  -DPROTOC="$host_protoc" -Dnanopb_PROTOC_PATH="$host_protoc" \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DFETCHCONTENT_QUIET=OFF
echo "Building $sdk / $architecture with $jobs compile jobs"
cmake --build "$build" --config "$configuration" --target GameRemoteIOS --parallel "$jobs" -- CODE_SIGNING_ALLOWED=NO
