#!/bin/sh
# Preserve .app executable modes through GitHub artifact storage. No signing or upload.
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
sdk=${1:-iphonesimulator}
case "$sdk" in
  iphonesimulator) configuration=Debug; label=simulator ;;
  iphoneos) configuration=Release; label=device-unsigned ;;
  *) echo 'Usage: package-app.sh [iphonesimulator|iphoneos]' >&2; exit 2 ;;
esac
app="$root/ios/build/$sdk/$configuration-$sdk/GameRemote.app"
out="$root/ios/build/packages"
roundtrip="$root/ios/build/package-verification/$sdk"
exe=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app/Info.plist")
case "$exe" in ''|*/*|..|.) echo 'Invalid bundle executable name' >&2; exit 2;; esac
[ -x "$app/$exe" ] || { echo 'Built app executable is missing or not executable' >&2; exit 1; }
for resource in Assets.car PrivacyInfo.xcprivacy AGPL-3.0-only-OpenSSL.txt ThirdPartyNotices.txt; do
  [ -s "$app/$resource" ] || { echo "Missing app resource: $resource" >&2; exit 1; }
done
mkdir -p "$out" "$roundtrip"
archive="$out/GameRemote-iOS-$label.tar.gz"
tar -czf "$archive" -C "$(dirname "$app")" GameRemote.app
tar -xzf "$archive" -C "$roundtrip"
diff -qr "$app" "$roundtrip/GameRemote.app"
[ -x "$roundtrip/GameRemote.app/$exe" ] || { echo 'Archive lost executable permission' >&2; exit 1; }
[ "$(stat -f '%Lp' "$app/$exe")" = "$(stat -f '%Lp' "$roundtrip/GameRemote.app/$exe")" ] || { echo 'Archive changed executable permissions' >&2; exit 1; }
(cd "$out" && shasum -a 256 "$(basename "$archive")" > "$(basename "$archive").sha256")
echo "Verified archive: $archive"
