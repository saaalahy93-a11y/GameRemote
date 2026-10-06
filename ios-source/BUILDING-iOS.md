# Build GameRemote for iPhone and iPad from this source package

This **r2 source candidate** targets version **1.10.0, build 3**. It contains an iOS-only source selection, the shared protocol core, four expanded vendor trees and five unchanged upstream source archives. It contains no Git history, signing identity, profile or application binary. The retained upstream archives contain public cryptographic test fixtures; those are upstream source data, not publisher credentials.

The original development helpers still default to build 2. The commands below explicitly request build 3. The source manifest records the reviewed uncommitted signing, explicit codesign XML parsing, nanopb privacy-resource changes and the reviewed curl privacy-resource correction included in this snapshot. A future build must be checked against that manifest; this package does not claim to match the existing Build2 binaries.

## Host tools

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

## Configure and compile unsigned build 3

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
  -DCHIAKI_IOS_VERSION=1.10.0 -DCHIAKI_IOS_BUILD_NUMBER=3 \
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

The simpler existing `GR_IOS_VERSION=1.10.0 GR_IOS_BUILD_NUMBER=3 ios/scripts/build.sh <sdk>` route remains available, but its configure step fetches the pinned upstream Git/archive dependencies unless you have separately configured all FetchContent source overrides. The explicit commands above use the included source inputs.

## Signing and source identity

`ios/scripts/sign-and-export.py` and `ios/scripts/store-archive.py` retain the reviewed manual signing flow. Follow `docs/release/ios-store-profile.md` with real public URLs, a final export classification and an owner-controlled signing identity/profile. Never put credentials in this source tree or command arguments. No such credentials or final export answers are supplied here.

The signing helper reports `git rev-parse HEAD`; this package deliberately has no Git database. Before using that helper, create a new local Git repository and commit only the unpacked source package **before** creating build directories or supplying signing material. That fresh commit is a new source identity; preserve this package's archive hash and manifest alongside it. Alternatively use an approved committed checkout whose build inputs match this manifest. Do not claim the old base commit alone identifies these uncommitted changes.

The GitHub signing workflow is retained as source, requires explicit manual dispatch and a private environment, and uploads no app to Apple. It needs a real repository/ref and explicitly configured owner secrets; a history-free archive cannot execute GitHub Actions by itself.

## Expected resources and verification boundary

The next native app must contain its root `PrivacyInfo.xcprivacy`, exact AGPL/OpenSSL licence and `ThirdPartyNotices.txt`, and `nanopb_Privacy.bundle/PrivacyInfo.xcprivacy` byte-identical to `third-party/nanopb/spm_resources/PrivacyInfo.xcprivacy`. The new `ios/cmake/NanopbPrivacy.cmake` packages the upstream manifest separately; it does not rewrite the manifest.

Archive hashes, static source/resource closure and notice bytes are checked for this package. No Xcode build or old test suite was rerun while preparing it. The offline command sequence is derived from the actual CMake/build entry points and source pins; native execution of this exact source-package configuration remains unqualified. A subsequent candidate still needs its own signature/resource/binary validation, device playback evidence and matching public source/metadata.

## Licence and attribution

GameRemote is a modified derivative of chiaki-ng, based on Chiaki. Preserve `COPYING`, `LICENSES/AGPL-3.0-only-OpenSSL.txt`, the original author/copyright notices and all dependency notices. `notices/` contains exact licence copies plus the same nine-component notice text as the retained Build2 app; that notice equality does not establish binary equality. Mbed TLS and its framework retain their original dual-licence texts. This source package does not grant a different licence or establish compatibility between App Store binary terms and those obligations.

Any later privacy or metadata source change is a separate candidate. Regenerate the source snapshot and hashes after such a change; this sealed snapshot does not include future edits. The separate rights review leaves App Store binary distribution permission under current terms unresolved; source publication alone does not resolve that question.

## r2 curl privacy resource correction

The reviewed ios/cmake/CurlPrivacy.cmake helper also packages this pinned iOS integration’s manifest, ios/Dependencies/curl/PrivacyInfo.xcprivacy, as GameRemote.app/curl_Privacy.bundle/PrivacyInfo.xcprivacy. This is an integration-specific curl declaration, not an upstream general-purpose manifest. The app manifest also declares the reviewed file-metadata reason. Final Xcode aggregation and runtime behaviour remain unverified.

The r2 delta is recorded in SOURCE-DELTA.json: four project files changed and two were added, all at independently reviewed hashes. The five dependency archives and all other project source members are byte-identical to audited v1. The public project destination is https://github.com/saaalahy93-a11y/GameRemote; this package preparation does not publish a release or attest to a native binary match.
