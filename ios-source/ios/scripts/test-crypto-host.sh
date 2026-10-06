#!/bin/sh
# Real core tests with both crypto backends. This does not establish iOS linking or console interoperability.
# Requires CMake, a C/C++ compiler, protoc, Python protobuf, and host json-c/miniupnpc/libevent/OpenSSL.
# Run via agent-capture when required by the local development environment.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
build_root=${CHIAKI_CRYPTO_BUILD_DIR:-"$root/ios/build/crypto-host"}
cmake_bin=${CMAKE:-cmake}
ctest_bin=${CTEST:-ctest}
backend=${1:-both}
case "$backend" in
  both) backends="mbedtls openssl" ;;
  mbedtls|openssl) backends="$backend" ;;
  *) printf 'Usage: %s [both|mbedtls|openssl]\n' "$0" >&2; exit 2 ;;
esac
for backend in $backends; do
  use_mbedtls=OFF
  [ "$backend" != mbedtls ] || use_mbedtls=ON
  build="$build_root/$backend"
  "$cmake_bin" -S "$root" -B "$build" \
    -DCMAKE_BUILD_TYPE=Debug -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DCHIAKI_ENABLE_TESTS=ON -DCHIAKI_ENABLE_CLI=OFF -DCHIAKI_ENABLE_GUI=OFF \
    -DCHIAKI_ENABLE_ANDROID=OFF -DCHIAKI_ENABLE_BOREALIS=OFF \
    -DCHIAKI_ENABLE_SETSU=OFF -DCHIAKI_ENABLE_STEAMDECK_NATIVE=OFF \
    -DCHIAKI_ENABLE_SPEEX=OFF -DCHIAKI_ENABLE_RUDP=OFF \
    -DCHIAKI_ENABLE_FFMPEG_DECODER=OFF -DCHIAKI_ENABLE_PI_DECODER=OFF \
    -DCHIAKI_ENABLE_STEAM_SHORTCUT=OFF -DCHIAKI_LIB_ENABLE_OPUS=OFF \
    -DCHIAKI_USE_SYSTEM_NANOPB=OFF -DCHIAKI_USE_SYSTEM_JERASURE=OFF \
    -DCHIAKI_USE_SYSTEM_CURL=OFF -DCURL_USE_LIBPSL=OFF \
    -DCHIAKI_LIB_ENABLE_MBEDTLS="$use_mbedtls" \
    -DCHIAKI_LIB_MBEDTLS_EXTERNAL_PROJECT="$use_mbedtls" \
    -DCHIAKI_LIB_OPENSSL_EXTERNAL_PROJECT=OFF
  "$cmake_bin" --build "$build" --target chiaki-unit --parallel 2
  "$ctest_bin" --test-dir "$build" --output-on-failure --verbose
  printf '%s core suite passed: %s\n' "$backend" "$build"
done
