# Build GameRemote for iPhone and iPad from this source package

This **r5 corresponding-source candidate** targets version **1.10.0, build 4**. It contains the iOS frontend, shared protocol core, four expanded vendor trees, five exact upstream source archives and retained licence notices. It has no Git database, application binary or publisher signing material.

Build4 changes production code: `lib/src/rpcrypt.c` reserves all 32 HMAC-SHA256 output bytes before copying the 16-byte protocol IV. Native commit `d2a49d168aa22aa1d0bd050f146edb6582d9b961` also updates the host sanitizer harness and crypto documentation and adds the 19-line unsigned device workflow. The release coordinator reports 9 real Remote Play vectors and 5 registration tests passed ASan/UBSan. The separately documented full-suite sanitizer run remains blocked by the existing MUnit zero-bound parameter issue; the focused result is not a full-suite pass. These tests were not rerun during source packaging.

Build3 was uploaded but held after the HMAC buffer defect. Its earlier receipts, README, building guide and source delta are retained under provenance/ as historical records. Their native-code reuse statements describe Build3 only. Build4 requires and uses a new native build.

## Actual publisher Build4 route: new native artifact and local signing

The successful device-only workflow run `37524826816` built native commit `d2a49d168aa22aa1d0bd050f146edb6582d9b961`. The local verification receipt identifies `GameRemote-1.10.0-build4.ipa`, SHA-256 `00be6d8cc925852f9298ca87e8c2949b15b627ddda8b5c8d065aa4d92bcc0ef3`. Frozen packaging commit `debc8f600729ec2c56a1b5ac4ebfbe5aedf2ed71` supplies the exact Build4 packaging recipe and tests. `provenance/build4-binary-provenance.json` records the filtered evidence and `SOURCE-MANIFEST.json` records every delivered source file.

`ios/scripts/repackage-verified-device.py` pins the new native archive SHA-256 `68a15a69aea24e93c0f9eb0e245052195f1bead2e820538d754c79066789e464`, unsigned executable SHA-256 `42c5f03c4a64298fde31521516279cb4937cac32207f60ff969bf369cf616907` and asset catalogue SHA-256 `ac6cf17a0a818d6cd95f73ae5c8c7ccfc39c7992f4939579e0eaa0503d0cc468`. The owner supplies that verified archive, the approved profile and an existing local signing identity. The source package includes the recipe and public identity/hash pins, while signing material and binary inputs remain with the owner. A fork can use the complete fresh-build instructions below.

The recipe applies the reviewed publisher metadata and privacy resources, deliberately leaves both encryption declaration keys absent in deferred mode, signs locally with DER entitlements, and verifies the app and IPA. Public configuration and resource hashes are retained in the receipt. The recipe does not establish physical-console playback or Apple acceptance.

For the owner reproduction route, set the four `gr_` path variables to the verified Build4 archive, approved profile, existing keychain and a fresh absolute output path. Then run:

```sh
export GR_IOS_BUNDLE_IDENTIFIER=com.ahmedalsalahy.gameremote
export GR_IOS_DEVELOPMENT_TEAM=4J27D8LXNK
export GR_IOS_VERSION=1.10.0
export GR_IOS_BUILD_NUMBER=4
export GR_IOS_PRIVACY_URL=https://saaalahy93-a11y.github.io/GameRemote/privacy.html
export GR_IOS_SUPPORT_URL=https://saaalahy93-a11y.github.io/GameRemote/support.html
export GR_IOS_SOURCE_URL=https://github.com/saaalahy93-a11y/GameRemote/releases/download/ios-1.10.0-build4-source-r5/GameRemote-iOS-1.10.0-build4-source-r5.tar.gz
export GR_IOS_EXPORT_CLASSIFICATION=defer-to-app-store-connect
python3 ios/scripts/repackage-verified-device.py \
  --archive "$gr_verified_build4_archive" \
  --profile "$gr_approved_profile" \
  --keychain "$gr_existing_keychain" \
  --output "$gr_fresh_absolute_output" \
  --execute-signing
```

The native workflow and signing evidence are supplied by the release coordinator. Source packaging verifies their identifiers and hashes against the frozen inputs and does not repeat signing or native work. Publication and availability at the exact source URL remain the release owner's next steps after independent r5 archive review.

## Host tools for a fresh source build

Use a Mac with full **Xcode 26.3**, iPhoneOS/iPhoneSimulator SDK **26.2**, Python **3.12**, CMake **3.31.6**, Python protobuf **5.29.6** and host protoc **29.6**. Apple supplies Xcode/SDK/system frameworks separately. The package does not include their implementations or host-tool binaries.

Select the actual installed Xcode path (adjust this example if needed):

```sh
export DEVELOPER_DIR=/Applications/Xcode_26.3.app/Contents/Developer
python3 -m venv .build-tools
.build-tools/bin/python3 -m pip install protobuf==5.29.6 cmake==3.31.6
curl --fail --location --silent --show-error \
  https://github.com/protocolbuffers/protobuf/releases/download/v29.6/protoc-29.6-osx-universal_binary.zip \
  --output .build-tools/protoc-29.6.zip
printf '%s\n' '8ff5d44fd913d4cb29d5a000cb3835624cd5b7f113a4c94ce151bfa0ae9aab25  .build-tools/protoc-29.6.zip' | shasum -a 256 --check
unzip -q .build-tools/protoc-29.6.zip -d .build-tools/protoc
export CHIAKI_HOST_PYTHON="$PWD/.build-tools/bin/python3"
export CHIAKI_HOST_PROTOC="$PWD/.build-tools/protoc/bin/protoc"
export PATH="$PWD/.build-tools/bin:$PWD/.build-tools/protoc/bin:$PATH"
ios/scripts/preflight.sh
```

The older root `scripts/fetch-protoc.sh` is a Linux/upstream tool and is intentionally not included or used by this iOS source package. The authoritative host-tool check is `scripts/release/verify_host_tools.py`.

## Unpack the included dependency sources

Run from the extracted package root. The paths must be fresh. Verify the retained archives before extraction:

```sh
shasum -a 256 --check vendor-sources/SHA256SUMS
gr_src="$PWD"
gr_vendor="$gr_src/.vendor-source"
mkdir "$gr_vendor"
tar -xf "vendor-sources/opus-ddbe48383984d56acd9e1ab6a090c54ca6b735a6.tar.gz" -C "$gr_vendor"
tar -xf "vendor-sources/libevent-5df3037d10556bfcb675bc73e516978b75fc7bc7.tar.gz" -C "$gr_vendor"
tar -xf "vendor-sources/json-c-b4c371fa0cbc4dcbaccc359ce9e957a22988fb34.tar.gz" -C "$gr_vendor"
tar -xf "vendor-sources/miniupnp-b55145ec095652289a59c33603f3abafee898273.tar.gz" -C "$gr_vendor"
tar -xf "vendor-sources/mbedtls-3.6.7.tar.bz2" -C "$gr_vendor"
```

The `third-party/curl`, `third-party/nanopb`, `third-party/gf-complete` and `third-party/jerasure` directories are already expanded source. Do not run `git submodule update` in this history-free package. The inherited `.gitmodules` file is provenance, not an instruction to replace those trees.

## Configure and compile unsigned build 4

The explicit FetchContent overrides below use every included upstream archive and prevent dependency fetching during configure. The fixed Opus package-version value replaces Git tag metadata absent from the source archive; it does not modify the upstream files. Other archive contents remain unchanged.

For an arm64 device build:

```sh
gr_sdk=iphoneos
gr_arch=arm64
gr_build="$gr_src/ios/build/public-$gr_sdk"
cmake -S "$gr_src/ios" -B "$gr_build" -G Xcode \
  -DCMAKE_TOOLCHAIN_FILE="$gr_src/ios/cmake/ios.cmake" \
  -DCMAKE_OSX_SYSROOT="$gr_sdk" -DCMAKE_OSX_ARCHITECTURES="$gr_arch" \
  -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO \
  -DCHIAKI_IOS_STORE_RELEASE=OFF \
  -DCHIAKI_IOS_BUNDLE_IDENTIFIER=com.ahmedalsalahy.gameremote \
  -DCHIAKI_IOS_DEVELOPMENT_TEAM=4J27D8LXNK \
  -DCHIAKI_IOS_VERSION=1.10.0 -DCHIAKI_IOS_BUILD_NUMBER=4 \
  -DPYTHON_EXECUTABLE="$CHIAKI_HOST_PYTHON" -DPython_EXECUTABLE="$CHIAKI_HOST_PYTHON" \
  -DPROTOC="$CHIAKI_HOST_PROTOC" -Dnanopb_PROTOC_PATH="$CHIAKI_HOST_PROTOC" \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DFETCHCONTENT_FULLY_DISCONNECTED=ON \
  -DOPUS_PACKAGE_VERSION=1.5.2 \
  -DFETCHCONTENT_SOURCE_DIR_IOS_OPUS="$gr_vendor/opus-ddbe48383984d56acd9e1ab6a090c54ca6b735a6" \
  -DFETCHCONTENT_SOURCE_DIR_IOS_EVENT="$gr_vendor/libevent-5df3037d10556bfcb675bc73e516978b75fc7bc7" \
  -DFETCHCONTENT_SOURCE_DIR_IOS_JSON="$gr_vendor/json-c-b4c371fa0cbc4dcbaccc359ce9e957a22988fb34" \
  -DFETCHCONTENT_SOURCE_DIR_IOS_UPNP="$gr_vendor/miniupnp-b55145ec095652289a59c33603f3abafee898273" \
  -DFETCHCONTENT_SOURCE_DIR_MBEDTLS="$gr_vendor/mbedtls-3.6.7"
cmake --build "$gr_build" --config Release --target GameRemoteIOS --parallel 2 -- CODE_SIGNING_ALLOWED=NO
```

For a simulator, use `gr_sdk=iphonesimulator` and `gr_arch=$(uname -m)` before the same commands, with its separate build directory. Do not reuse an SDK's CMake build directory for the other SDK. The unsigned app is under `ios/build/public-<sdk>/Release-<sdk>/GameRemote.app`; its executable should retain its executable mode.

The bundle identifier and team shown above are public identifiers for the intended publisher candidate, not credentials. For your own signed fork, use identifiers and signing assets you control. This unsigned build does not install or launch on a physical iPhone and is not an App Store upload.

The simpler existing `GR_IOS_VERSION=1.10.0 GR_IOS_BUILD_NUMBER=4 ios/scripts/build.sh <sdk>` route remains available, but its configure step fetches the pinned upstream Git/archive dependencies unless you have separately configured all FetchContent source overrides. The explicit commands above use the included source inputs.

## Signing and source identity

`ios/scripts/sign-and-export.py` and `ios/scripts/store-archive.py` retain the reviewed manual signing flow. Follow `docs/release/ios-store-profile.md` with real public URLs, an explicit export declaration mode and an owner-controlled signing identity/profile. Never put credentials in this source tree or command arguments. No such credentials or final export answers are supplied here.

For local archive/export while the questionnaire remains pending, the supported explicit setting is `GR_IOS_EXPORT_CLASSIFICATION=defer-to-app-store-connect` (or `CHIAKI_IOS_EXPORT_CLASSIFICATION=defer-to-app-store-connect` for direct CMake configuration). This mode omits both `ITSAppUsesNonExemptEncryption` and `ITSEncryptionExportComplianceCode`; archive and IPA checks reject either key being present. Missing or unrecognized store values remain errors. The other accepted modes remain `exempt` and `non-exempt` and require the owner's actual classification. The deferred choice does not assert an exemption or supply a compliance code. Complete the App Store Connect questionnaire and any required documentation for the final candidate before submission.

The signing report records `export_declaration_pending=true` and `submission_ready=false`. The separately delivered Build4 IPA uses the new native artifact described above and was signed locally. Source packaging did not run native compilation or signing and has not demonstrated byte-identical reproduction from this standalone archive.

The signing helper reports `git rev-parse HEAD`; this package deliberately has no Git database. Before using that helper, create a new local Git repository and commit only the unpacked source package **before** creating build directories or supplying signing material. That fresh commit is a new source identity; preserve this package's archive hash and manifest alongside it. Alternatively use an approved committed checkout whose build inputs match this manifest. Do not claim the old base commit alone identifies the later reviewed changes. The source-owner commit hash above is a provenance reference; it does not turn this history-free, iOS-only selection into a full checkout of that commit.

The GitHub signing workflow is retained as source, requires explicit manual dispatch and a private environment, and uploads no app to Apple. It needs a real repository/ref and explicitly configured owner secrets; a history-free archive cannot execute GitHub Actions by itself.

## Expected resources and verification boundary

The app must contain the root `PrivacyInfo.xcprivacy`, AGPL/OpenSSL licence, `ThirdPartyNotices.txt`, `nanopb_Privacy.bundle/PrivacyInfo.xcprivacy` and `curl_Privacy.bundle/PrivacyInfo.xcprivacy`. The nanopb resource preserves its upstream source; the curl resource is the pinned integration declaration from `ios/Dependencies/curl/PrivacyInfo.xcprivacy`. Their separate binary checks are recorded in the public receipt.

Every r5 archive member is compared with approved r4 for bytes, type, mode, link target and other non-size metadata. Only the explicitly listed source and packaging/provenance delta may differ. Four vendor trees, all five upstream archives and every licence/notice member remain byte-identical. Existing source closure and sanitization evidence is inherited only for unchanged members; new source and public receipts are checked for restricted paths and credential markers. The standalone from-source commands are retained from the reviewed package with build 4 selected, but executing these exact offline commands and reproducing a signed IPA byte for byte remain unverified.

## Licence and historical provenance

GameRemote is a modified derivative of chiaki-ng, based on Chiaki. Preserve `COPYING`, `LICENSES/AGPL-3.0-only-OpenSSL.txt`, `docs/prototype/NOTICE.md`, original author/copyright text and `notices/`. Mbed TLS and its framework retain their original dual-licence texts. Known public upstream cryptographic test fixtures are source data. The separate distribution-rights review, export questionnaire, Apple processing and physical-device playback remain outside this source-packaging result.

`provenance/HISTORY.md` explains the retained r2/r3/r4 records and Build3 hold. `provenance/BASE-REVIEW-r4.json` is approval of the exact base archive, not r5 approval. This new r5 archive requires its own independent delta review. Future source/privacy/metadata changes require a new snapshot and hashes.
