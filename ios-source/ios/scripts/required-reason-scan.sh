#!/bin/sh
# Lists the Apple required-reason API symbols the built app actually imports, to keep
# App/PrivacyInfo.xcprivacy grounded in the binary. Reports only; it never fails the build.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
app=${1:-"$root/ios/build/iphonesimulator/Debug-iphonesimulator/GameRemote.app"}
[ -d "$app" ] || { echo "No app bundle at $app" >&2; exit 2; }
symbols='^_(stat|fstat|lstat|fstatat|getattrlist|getattrlistbulk|fgetattrlist|getattrlistat|statfs|fstatfs|statvfs|fstatvfs|mach_absolute_time)(\$.*)?$'
strings_wanted='^(systemUptime|activeInputModes|NSFileModificationDate|NSFileCreationDate|NSURLContentModificationDateKey|NSURLCreationDateKey|NSFileSystemFreeSize|NSFileSystemSize|NSURLVolumeAvailableCapacity.*|NSUserDefaults)$'
find "$app" -type f | while IFS= read -r file; do
  file "$file" | grep -q 'Mach-O' || continue
  echo "== ${file#"$app"/}"
  nm -u "$file" 2>/dev/null | awk '{print $NF}' | grep -E "$symbols" | sort -u || true
  strings - "$file" | grep -E "$strings_wanted" | sort -u || true
done
echo "== declared in PrivacyInfo.xcprivacy"
plutil -extract NSPrivacyAccessedAPITypes json -o - "$app/PrivacyInfo.xcprivacy" 2>/dev/null || echo "privacy manifest missing from the bundle"
