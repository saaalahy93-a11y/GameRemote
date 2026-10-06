#!/bin/bash
# Isolated Qt 6.9.3 build; use agent-capture as shown in README.md.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
TOOL_BIN=${QT_CMAKE_TOOL_BIN:?Use build_sdk.py to select verified CMake and Ninja tools}
DOWNLOADS="$ROOT/downloads"
SOURCE="$ROOT/source"
BUILD="$ROOT/build"
PREFIX="$ROOT/prefix"
export PATH="$TOOL_BIN:$PATH"
export CMAKE_BUILD_PARALLEL_LEVEL=1

require_space() {
    python3 - "$ROOT" "$1" <<'PY'
import shutil
import sys

free = shutil.disk_usage(sys.argv[1]).free
required = int(sys.argv[2])
print(f"Free disk: {free:,} bytes; stage floor: {required:,} bytes")
if free < required:
    raise SystemExit("Insufficient free disk for this bounded stage")
PY
}

require_xcode() {
    # DEVELOPER_DIR may select an already-installed Xcode for this command.
    # Never substitute a version or disable Qt's upstream SDK checks.
    /usr/bin/xcrun xcodebuild -version
    /usr/bin/xcrun --sdk macosx --show-sdk-version
}

require_vulkan_headers() {
    if [[ -z ${QT_VULKAN_INCLUDE_DIR:-} || ${QT_VULKAN_INCLUDE_DIR:0:1} != / ]]; then
        printf 'QT_VULKAN_INCLUDE_DIR must select checksum-verified Vulkan-Headers\n' >&2
        return 1
    fi
    test -f "$QT_VULKAN_INCLUDE_DIR/vulkan/vulkan.h"
    test -f "$QT_VULKAN_INCLUDE_DIR/vulkan/vulkan_core.h"
    test -f "$QT_VULKAN_INCLUDE_DIR/vulkan/vk_platform.h"
}

verify_downloads() {
    (cd "$DOWNLOADS" && /usr/bin/shasum -a 256 -c "$ROOT/SHA256SUMS")
}

download() {
    require_space 200000000
    mkdir -p "$DOWNLOADS"
    local hash filename extra actual
    while read -r hash filename extra; do
        if [[ -n "$extra" ]]; then
            printf 'Invalid checksum manifest entry\n' >&2
            return 1
        fi
        if [[ -f "$DOWNLOADS/$filename" ]]; then
            actual=$(/usr/bin/shasum -a 256 "$DOWNLOADS/$filename")
            if [[ ${actual%% *} == "$hash" ]]; then
                printf 'Verified cached archive: %s\n' "$filename"
                continue
            fi
            printf 'Existing archive failed SHA256: %s\n' "$filename" >&2
            return 1
        fi
        /usr/bin/curl --fail --location --connect-timeout 20 --max-time 600 \
            --output "$DOWNLOADS/$filename.partial" \
            "https://download.qt.io/archive/qt/6.9/6.9.3/submodules/$filename"
        actual=$(/usr/bin/shasum -a 256 "$DOWNLOADS/$filename.partial")
        if [[ ${actual%% *} != "$hash" ]]; then
            printf 'Downloaded archive failed SHA256: %s\n' "$filename" >&2
            return 1
        fi
        mv -- "$DOWNLOADS/$filename.partial" "$DOWNLOADS/$filename"
    done < "$ROOT/SHA256SUMS"
    verify_downloads
}

extract_sources() {
    require_space 3000000000
    verify_downloads
    mkdir -p "$SOURCE"
    local module target staging
    for module in qtbase qtsvg qtshadertools qtdeclarative; do
        target="$SOURCE/$module-everywhere-src-6.9.3"
        if [[ -d "$target" ]]; then
            printf 'Source already exists; preserving: %s\n' "$target"
            continue
        fi
        staging="$SOURCE/.unpack-$module"
        if [[ -e "$staging" ]]; then
            printf 'Partial extraction exists; inspect before retry: %s\n' "$staging" >&2
            return 1
        fi
        mkdir "$staging"
        /usr/bin/tar -xJf "$DOWNLOADS/$module-everywhere-src-6.9.3.tar.xz" -C "$staging"
        mv -- "$staging/$module-everywhere-src-6.9.3" "$target"
        rmdir "$staging"
    done
}

configure_base() {
    require_vulkan_headers
    require_xcode
    test -x "$SOURCE/qtbase-everywhere-src-6.9.3/configure"
    mkdir -p "$BUILD/qtbase"
    (
        cd "$BUILD/qtbase"
        "$SOURCE/qtbase-everywhere-src-6.9.3/configure" \
            -prefix "$PREFIX" -release -shared -opensource -confirm-license \
            -feature-appstore-compliant -feature-vulkan -nomake examples -nomake tests -no-pch \
            -- -DCMAKE_OSX_ARCHITECTURES=arm64 -DQT_BUILD_DOCS=OFF \
            "-DVulkan_INCLUDE_DIR=$QT_VULKAN_INCLUDE_DIR" \
            "-DCMAKE_MAKE_PROGRAM=$(command -v ninja)"
    )
}

verify_prefix() {
    require_vulkan_headers
    # Compile against the fresh SDK and require genuine generated feature values.
    # The component lookup also checks that the four-module SDK is connected.
    "$PREFIX/bin/qt-cmake" -S "$ROOT/probe" -B "$BUILD/probe" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release "-DCMAKE_MAKE_PROGRAM=$(command -v ninja)" \
        "-DVulkan_INCLUDE_DIR=$QT_VULKAN_INCLUDE_DIR"
    cmake --build "$BUILD/probe" --parallel 1
    "$BUILD/probe/qt_store_probe"
}

build_all() {
    require_xcode
    # Conservative planning floor, not a measured peak or a space guarantee.
    require_space 8000000000
    local module
    for module in qtbase qtsvg qtshadertools qtdeclarative; do
        test -f "$SOURCE/$module-everywhere-src-6.9.3/CMakeLists.txt"
    done
    configure_base
    cmake --build "$BUILD/qtbase" --parallel 1
    cmake --install "$BUILD/qtbase"
    for module in qtsvg qtshadertools qtdeclarative; do
        require_space 3000000000
        "$PREFIX/bin/qt-cmake" \
            -S "$SOURCE/$module-everywhere-src-6.9.3" -B "$BUILD/$module" -G Ninja \
            -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
            "-DCMAKE_INSTALL_PREFIX=$PREFIX" "-DCMAKE_MAKE_PROGRAM=$(command -v ninja)" \
            -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_DOCS=OFF \
            "-DVulkan_INCLUDE_DIR=$QT_VULKAN_INCLUDE_DIR" \
            -DBUILD_WITH_PCH=OFF
        cmake --build "$BUILD/$module" --parallel 1
        cmake --install "$BUILD/$module"
    done
    verify_prefix
}

case ${1:-preflight} in
    preflight)
        require_vulkan_headers
        require_xcode
        cmake --version
        ninja --version
        require_space 8000000000
        ;;
    download) download ;;
    verify-downloads) verify_downloads ;;
    sources) extract_sources ;;
    configure) configure_base ;;
    build) build_all ;;
    verify) verify_prefix ;;
    *) printf 'Usage: bash %s {preflight|download|verify-downloads|sources|configure|build|verify}\n' "$0" >&2; exit 2 ;;
esac
