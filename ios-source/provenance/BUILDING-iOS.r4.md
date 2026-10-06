# Build GameRemote for iPhone and iPad from this source package

This **r4 corresponding-source candidate** targets version **1.10.0, build 3**. It contains an iOS-only source selection, the shared protocol core, four expanded vendor trees and five unchanged upstream source archives. It contains no Git history, certificate/private-key material, profile or application binary. The retained upstream archives contain public cryptographic test fixtures; those are upstream source data, not publisher credentials.

The original development helpers still default to build 2. The from-source commands below explicitly request build 3 and remain available for a fresh build. The actual publisher Build3 candidate reused the previously verified Build2 native code and assets, applied the reviewed metadata/privacy-resource updates, and was signed locally. No new CI/native build or key export was used for that candidate. SOURCE-MANIFEST.json records the exact delivered source; the frozen packaging source commit is `5c1df97059d541c6fc1295abbabd51a415980e26`. This package contains no repository history.

## Actual publisher Build3 route: verified artifact reuse and local signing

The existing local verification report identifies `GameRemote-1.10.0-build3.ipa` with SHA-256 `4d390f97d09195312b4989de84d73dcea5934b7d880dd4b38310c11787c95104`. Its native code came from commit `7e9e397e07f677282beb1af76448d587f79f300e`; reviewed metadata/privacy-resource inputs came from `432b5e8f72e42c0b47f6568f8a9560e4d0b678e9`. Independent source review approved reuse because compiled code, assets and dependency inputs did not change between those source states. The four-file r4 delta adds the exact packaging recipe and focused tests and corrects certificate extraction in the signing verifier; it changes no app production source, dependency source or notice text.

`ios/scripts/repackage-verified-device.py` requires the exact verified Build2 device archive SHA-256 `7a122500a92eceb6c8a4fdf27e6db115957424a05233d2246d8960fdf0fe1148`, native executable SHA-256 `4890e80bed94e09e8ddacfdb03a5270b58b72985ed1003da260e3b555fa95daa` and asset catalogue SHA-256 `0b48206ca937a036491603b7470093a4f2c86cbc7355c6123f6de3f382aab908`. It also pins the approved publisher's profile hash and public certificate fingerprint. It accepts this exact publisher candidate, with the owner's existing local key and profile; those assets and the base binary archive are not included in this public source package. Use the from-source instructions below for a fresh build or a fork.

The recipe updates the bundle identifier, version/build and three public URLs, removes both encryption declaration keys for the explicit deferred mode, installs the root/nanopb/curl privacy manifests, embeds the approved profile and signs locally with DER entitlements. It verifies the app and IPA and checks that the original archive/profile and privacy manifests remain unchanged. This reviewed base app has no embedded Swift runtime dylibs or nested executable code; the recipe rejects Frameworks or PlugIns rather than inventing runtime support from another toolchain.

For the owner-controlled reproduction route, supply the verified archive/profile, existing keychain and a fresh absolute output path in the four `gr_` path variables before running this command. These variables contain paths, not exported private-key contents:

```sh
export GR_IOS_BUNDLE_IDENTIFIER=com.ahmedalsalahy.gameremote
export GR_IOS_DEVELOPMENT_TEAM=4J27D8LXNK
export GR_IOS_VERSION=1.10.0
export GR_IOS_BUILD_NUMBER=3
export GR_IOS_PRIVACY_URL=https://saaalahy93-a11y.github.io/GameRemote/privacy.html
export GR_IOS_SUPPORT_URL=https://saaalahy93-a11y.github.io/GameRemote/support.html
export GR_IOS_SOURCE_URL=https://github.com/saaalahy93-a11y/GameRemote/releases/download/ios-1.10.0-build3-source-r4/GameRemote-iOS-1.10.0-build3-source-r4.tar.gz
export GR_IOS_EXPORT_CLASSIFICATION=defer-to-app-store-connect
python3 ios/scripts/repackage-verified-device.py \
  --archive "$gr_verified_build2_archive" \
  --profile "$gr_approved_profile" \
  --keychain "$gr_existing_keychain" \
  --output "$gr_fresh_absolute_output" \
  --execute-signing
```

This is the route documented by `provenance/build3-binary-provenance.json`. No new unsigned publisher archive helper/workflow is part of this r4 delta. Local signature/package verification passed in the existing release evidence; this packaging task did not rerun it. The deferred export questionnaire, Apple processing and physical-device playback remain unverified, and `submission_ready` remains `false`. Source URL availability is not asserted until the release owner publishes and verifies the exact archive.

The from-source build route follows. It is preserved independently of the artifact-reuse recipe; a fresh build has its own output hashes and requires its own binary/signature/resource validation.

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

`ios/scripts/sign-and-export.py` and `ios/scripts/store-archive.py` retain the reviewed manual signing flow. Follow `docs/release/ios-store-profile.md` with real public URLs, an explicit export declaration mode and an owner-controlled signing identity/profile. Never put credentials in this source tree or command arguments. No such credentials or final export answers are supplied here.

For local archive/export while the questionnaire remains pending, the supported explicit setting is `GR_IOS_EXPORT_CLASSIFICATION=defer-to-app-store-connect` (or `CHIAKI_IOS_EXPORT_CLASSIFICATION=defer-to-app-store-connect` for direct CMake configuration). This mode omits both `ITSAppUsesNonExemptEncryption` and `ITSEncryptionExportComplianceCode`; archive and IPA checks reject either key being present. Missing or unrecognized store values remain errors. The other accepted modes remain `exempt` and `non-exempt` and require the owner's actual classification. The deferred choice does not assert an exemption or supply a compliance code. Complete the App Store Connect questionnaire and any required documentation for the final candidate before submission.

The signing report records the chosen mode, `export_declaration_pending=true` for deferred declarations, and `submission_ready=false`. The separately delivered publisher IPA was signed locally through the artifact-reuse recipe above; no binary or signing material is included in this source archive. A fresh from-source build of r4 has not been run by this packaging task.

The signing helper reports `git rev-parse HEAD`; this package deliberately has no Git database. Before using that helper, create a new local Git repository and commit only the unpacked source package **before** creating build directories or supplying signing material. That fresh commit is a new source identity; preserve this package's archive hash and manifest alongside it. Alternatively use an approved committed checkout whose build inputs match this manifest. Do not claim the old base commit alone identifies the later reviewed changes. The source-owner commit hash above is a provenance reference; it does not turn this history-free, iOS-only selection into a full checkout of that commit.

The GitHub signing workflow is retained as source, requires explicit manual dispatch and a private environment, and uploads no app to Apple. It needs a real repository/ref and explicitly configured owner secrets; a history-free archive cannot execute GitHub Actions by itself.

## Expected resources and verification boundary

The next native app must contain its root `PrivacyInfo.xcprivacy`, exact AGPL/OpenSSL licence and `ThirdPartyNotices.txt`, and `nanopb_Privacy.bundle/PrivacyInfo.xcprivacy` byte-identical to `third-party/nanopb/spm_resources/PrivacyInfo.xcprivacy`. The new `ios/cmake/NanopbPrivacy.cmake` packages the upstream manifest separately; it does not rewrite the manifest.

Every archive member is compared with approved r3 for bytes, type and mode; two approved source replacements, two source additions and the listed packaging/provenance documents are the only differences. Prior static source/resource closure and notice audits are inherited for unchanged bytes, as recorded in SOURCE-DELTA.json. No Xcode build or old test suite was rerun while preparing it. The offline command sequence is derived from the actual CMake/build entry points and source pins; native execution of this exact source-package configuration remains unqualified. A subsequent candidate still needs its own signature/resource/binary validation, device playback evidence and matching public source/metadata.

## Licence and attribution

GameRemote is a modified derivative of chiaki-ng, based on Chiaki. Preserve `COPYING`, `LICENSES/AGPL-3.0-only-OpenSSL.txt`, the original author/copyright notices and all dependency notices. `notices/` contains exact licence copies plus the same nine-component notice text as the retained Build2 app; that notice equality does not establish binary equality. Mbed TLS and its framework retain their original dual-licence texts. This source package does not grant a different licence or establish compatibility between App Store binary terms and those obligations.

Any later privacy or metadata source change is a separate candidate. Regenerate the source snapshot and hashes after such a change; this sealed snapshot does not include future edits. The separate rights review leaves App Store binary distribution permission under current terms unresolved; source publication alone does not resolve that question.

## Retained r2 curl privacy resource correction

The reviewed ios/cmake/CurlPrivacy.cmake helper also packages this pinned iOS integration’s manifest, ios/Dependencies/curl/PrivacyInfo.xcprivacy, as GameRemote.app/curl_Privacy.bundle/PrivacyInfo.xcprivacy. This is an integration-specific curl declaration, not an upstream general-purpose manifest. The app manifest also declares the reviewed file-metadata reason. Final Xcode aggregation and runtime behaviour remain unverified.

The earlier six-file curl delta is preserved in provenance/SOURCE-DELTA.r2.json as historical evidence. Its source changes, all five dependency archives and all four expanded vendor trees remain intact.

## Retained r3 deferred export declaration delta

The earlier seven-file deferred export declaration delta is preserved as historical evidence in provenance/SOURCE-DELTA.r3.json. The r3 archive was independently approved at its exact hash; provenance/BASE-REVIEW-r3.json records that review. All those changes remain present. SOURCE-DELTA.json now records the four-file r4 packaging/verifier delta. This newly assembled r4 archive requires its own independent delta review.

The planned source archive URL already embedded in the separately signed IPA is https://github.com/saaalahy93-a11y/GameRemote/releases/download/ios-1.10.0-build3-source-r4/GameRemote-iOS-1.10.0-build3-source-r4.tar.gz. This packaging task performs no upload or publication. The outer delivery receipt binds this source archive's hash to the existing IPA hash; no byte-identical fresh build or App Store acceptance is claimed.
