# Store Qt SDK with GameRemote's Vulkan renderer

The standalone `build_sdk.py` entry point builds an arm64 Qt 6.9.3 SDK, not a GameRemote app.
It builds QtBase, QtSvg, QtShaderTools and QtDeclarative from the four archives
in `SHA256SUMS`. Both the original prefix and a relocated copy must pass the
Store/private-API guard and compile/link the Vulkan APIs used by GameRemote.
The probe prints the feature values without creating a Vulkan instance, device,
window or rendering work. This is SDK capability evidence, not a GPU test.

`build_sdk.py` downloads checksum-pinned Khronos Vulkan-Headers 1.4.357.0 from
`dependencies.lock.json`, validates the required headers and records the source
archive and header hashes in `evidence/vulkan-headers.json`. It supplies the
explicit include directory through `QT_VULKAN_INCLUDE_DIR`. The QtBase recipe
requires `-feature-vulkan` and passes `Vulkan_INCLUDE_DIR` to all module and
probe configurations. Missing headers or a disabled Qt Vulkan feature fail the
build. The previous SDK with SHA-256
`45a4253bac4191cfabc34d49ef43c6ff7f07900c9e3ac3e50731008af56328b8`
has `QT_FEATURE_vulkan=-1` and cannot build the current GameRemote renderer.

Qt's exact 6.9.3 `FindWrapVulkanHeaders.cmake` requires Vulkan headers for this
build; the app separately needs its selected Vulkan loader and MoltenVK runtime.
Consumers must supply compatible Vulkan headers in their dependency prefixes.
Rebuilding only QtGui would leave QtQuick's conditional Vulkan API unverified;
the recipe produces a fresh, consistent four-module SDK.

## Public-only input boundary

Publish only this directory's recipe, probes, tests and narrow dependency lock,
plus `.github/workflows/build-macos-store-sdk.yml`. Do not copy the private
multi-platform harness, app archive, source lock, inherited binaries, session
transcripts or internal release records. The SDK probe inspects the imported
QtCore headers directly; it never includes an app CMake file. The standalone
builder uses only Python's standard library and requires no pip packages.

`--app-source-reference-sha256` records a compatibility reference. The receipt
has `scope: qt-sdk-only` and explicitly states `archive_read: false` and
`application_built: false`; it does not claim to have checked app source bytes.
The separate app build must still verify its own actual source archive. SDK
inputs and hashes are recorded in `evidence/recipe-inputs.json`.

## Source and notice distribution

The successful artifact includes the SDK archive together with the exact four
Qt source archives and Vulkan-Headers source archive used by the build. These
are complete upstream archives, including embedded third-party sources. No
private application archive is included. `recipe.tar.gz` retains this directory's
explicit source/test files and the workflow, including its hidden `.github` path.

`distribution.json` binds the SDK, source archives, recipe, README and inventory
by SHA-256. It maps the original licence/notice and Qt attribution bytes in
`notices/` back to their archive members, and resolves every declared Qt
`LicenseFile` reference in these inputs. The notice collection deliberately
covers the complete upstream modules; it does not claim every optional platform
component is linked into the SDK. The source archives remain the full source
and upstream notice record.

`sdk-inventory.json` records every SDK member and regular-file hash, plus the
architecture and imports of each actual Mach-O file. Non-system absolute imports
are recorded explicitly for dependency inspection. This is static SDK evidence,
not an application or GPU runtime test. Missing/changed source inputs, incomplete
notice references or mismatched relocated SDK binaries fail packaging while
retaining the SDK only in the non-uploaded work directory. The workflow uploads
failure evidence and available source/notice material; it includes the SDK binary
only after the whole source kit is assembled. The included Qt licence texts and
attributions accompany the binary; a URL-only future source promise is not used.

## Bounded hosted run

After the SDK-only files are reviewed and published, manually dispatch
`build-macos-store-sdk.yml` in the public repository. The job's visibility guard
prevents it from running in a private repository. It uses the **standard**
`macos-15` arm64 runner, pinned Xcode 16.4/macOS SDK 15.5, Python 3.12.10 and
checksum-pinned CMake 3.30.9/Ninja 1.13.1. The selected runner must still have that
exact Xcode/SDK pair; the driver rejects an image mismatch. No signing identity,
provisioning profile or repository secret is needed. Keep `contents: read`,
checkout credential persistence disabled, and the SDK-only dispatch.

The workflow executes:

```sh
python native-candidate/qt-store-sdk/build_sdk.py \
  --work "$RUNNER_TEMP/gameremote-qt-sdk" \
  --output "$GITHUB_WORKSPACE/sdk-output" \
  --app-source-reference-sha256 "$APP_SOURCE_REFERENCE"
```

The reference must be a reviewed lowercase SHA-256, not a path. Both work and
output directories must be fresh and separate from the recipe. Failures retain
a failed receipt and available logs. Tool/header downloads have a 100 MB bound
and must match their pinned hashes before use.

The workflow bounds the native job at 120 minutes and its build step at 110
minutes. Compilation uses one worker. The last four-module SDK job took about
80 minutes; enabling Vulkan has not yet been timed. The recipe retains its
8,000,000,000-byte initial free-space floor and 3,000,000,000-byte intermediate
floor. These are planning guards, not measured peak-space guarantees.

Standard hosted runner compute is free for public repositories; larger runners
are billed. Artifact storage and retention still require attention to the
account's shared storage allowance. This workflow retains evidence and the
successful SDK/source kit for one day and adds no Actions cache. The earlier SDK
was about 44 MB, and the five retained source archives total about 94 MB before
notice/inventory overhead; the new complete artifact size is not yet known.
Download and verify the successful artifact and its receipt before selecting its new hash for an app
build. Publishing this recipe or a successful SDK does not qualify an app for
the App Store.

References:

- [Khronos Vulkan-Headers release](https://github.com/KhronosGroup/Vulkan-Headers/releases/tag/vulkan-sdk-1.4.357.0)
- [Qt 6.9 macOS requirements](https://doc.qt.io/archives/qt-6.9/macos.html)
- [Qt open-source distribution obligations](https://www.qt.io/development/open-source-lgpl-obligations)
- [GitHub Actions billing and storage](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [Standard GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
