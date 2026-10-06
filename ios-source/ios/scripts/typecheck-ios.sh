#!/bin/sh
# Typechecks every app Swift source against the real iOS simulator SDK. Seconds, not a build:
# it reports all Swift errors at once before the dependency build starts. Requires full Xcode.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
sdk=$(xcrun --sdk iphonesimulator --show-sdk-path)
xcrun --sdk iphonesimulator swiftc -typecheck -parse-as-library -swift-version 5 \
  -sdk "$sdk" -target "$(uname -m)-apple-ios16.0-simulator" \
  -I "$root/ios/Bridge" "$root"/ios/App/*.swift
echo "App Swift sources typecheck against $(basename "$sdk")"
