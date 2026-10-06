#!/bin/sh
# Host-only checks. They never establish iOS linking, UIKit behaviour, networking or playback.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
app="$root/ios/App"; tests="$root/ios/tests"
build="$root/ios/build/host-tests"
host=arm64-apple-macos13.0
[ "$(uname -m)" = arm64 ] || host=x86_64-apple-macos13.0
mkdir -p "$build/include/gameremote"
printf '#pragma once\n#define CHIAKI_LIB_ENABLE_OPUS 1\n#define CHIAKI_LIB_ENABLE_PI_DECODER 0\n#define CHIAKI_LIB_ENABLE_FFMPEG_DECODER 0\n' > "$build/include/gameremote/config.h"
clang -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -fsanitize=address,undefined -g -I"$root/lib/include" -I"$root/ios/Bridge" -I"$build/include" "$root/ios/Bridge/GameRemoteBridge.c" "$tests/bridge_lifecycle.c" -o "$build/bridge-lifecycle"
"$build/bridge-lifecycle"
swiftc "$app/H264.swift" "$app/MediaState.swift" "$tests/main.swift" -o "$build/h264-tests"
"$build/h264-tests"
# Public build-time links: missing development configuration and valid/rejected URLs.
swiftc "$app/AppLinks.swift" "$tests/links/main.swift" -o "$build/link-tests"
"$build/link-tests"
python3 "$tests/test-release-config.py"
# Pure logic: field validation, saved-console index, input merge, typed phases, artwork paths.
swiftc -target "$host" "$app/SessionPhase.swift" "$app/ConsoleIndex.swift" "$app/InputAggregator.swift" "$app/ConsoleArtwork.swift" "$app/Theme.swift" "$app/TouchControlLayout.swift" "$tests/logic/main.swift" -o "$build/logic-tests"
"$build/logic-tests"
# The actual SessionModel against a scripted fake of the bridge ABI, with in-memory credentials.
model="$app/SessionModel.swift $app/SessionPhase.swift $app/ConsoleIndex.swift $app/InputAggregator.swift $app/Keychain.swift $tests/MediaHostStub.swift"
clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -I"$root/ios/Bridge" -I"$tests/fake" -c "$tests/fake/fake_bridge.c" -o "$build/fake_bridge.o"
# shellcheck disable=SC2086
swiftc -target "$host" -sanitize=address -I"$root/ios/Bridge" -I"$tests/fake" $model "$tests/model/main.swift" "$build/fake_bridge.o" -o "$build/model-tests"
"$build/model-tests"
# SwiftUI screens against macOS SwiftUI with the platform mirror; iOS-only calls live in Platform.swift.
ui="$app/GameRemoteApp.swift $app/HomeView.swift $app/RegistrationViews.swift $app/SupportViews.swift $app/AppLinks.swift $app/StreamView.swift $app/TouchControls.swift $app/TouchControlLayout.swift $app/ConsoleArtwork.swift $app/Theme.swift"
# shellcheck disable=SC2086
swiftc -typecheck -parse-as-library -target "$host" -I"$root/ios/Bridge" $ui $model "$tests/PlatformHostStub.swift"
python3 "$tests/typecheck-media-host.py" "$build/MediaCoreHost.swift"
swiftc -typecheck "$build/MediaCoreHost.swift" "$app/H264.swift" "$app/MediaState.swift"
# Parsing can detect syntax errors without pretending host macOS has UIKit/SwiftUI iOS APIs.
swiftc -frontend -parse "$app"/*.swift
python3 "$tests/check-target.py"
# test-release-config.py parses the generated Info.plist for both profiles.
plutil -lint "$app/PrivacyInfo.xcprivacy"
