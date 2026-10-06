# Local macOS baseline build

This local development baseline builds unmodified chiaki-ng revision
`a9a2805884cfa83865fdfcc09ca3ddfcd628aa42` (version 1.10.0) on Apple Silicon.
The execution branch is `prototype/native-client`. No application, submodule, or
Qt source patch was required. The development spending target is £0.

## Verified result

- `../build-baseline/gui/chiaki.app/Contents/MacOS/chiaki`: arm64 Mach-O executable.
- Both `chiaki` and `chiaki-unit` built successfully.
- CTest: 1/1 test target passed; µnit: **117/117 tests passed, zero skipped**.
- Native GUI launch verified by coordinator screenshot: home screen renders,
  local PS5 discovered as ready/unregistered, upstream Steam shortcut prompt shown.
- Renderer/decoder options: coordinator settings inspection pending at this record.
- Streaming, controller input, performance, Windows, Developer ID signing, notarization, and
  distribution packaging are separate qualifications. This build alone does not
  establish any of them.

Final packaged and ad-hoc signed executable SHA-256:
`cb4aef6206b9403098127f5ea22f93f40f94cef2391c8f1739b6993a3344af40`.
Bundled cpp-steam-tools dylib SHA-256:
`028fd3fd52102d2c53b0504c4e53945928186899b982a8de5e965b92ef6dab2d`.

The `.app` is a local build product linked to Homebrew libraries. Its task-built
`cpp-steam-tools` dylib is packaged inside `Contents/Frameworks`. Keep the build
folder and exact dependencies for reproducibility.
It is not a standalone redistributable bundle. Preserve this completed baseline;
never rebuild it after feature source changes. Use `../build-client` for the
feature build, with the same toolchain, dependencies, SDK and CMake arguments.
Do not upgrade shared dependencies between matched baseline/prototype tests.

## Host and exact versions

Verified on 4 October 2026:

| Component | Version |
| --- | --- |
| macOS / architecture | 26.5.1 (25F80), arm64 |
| Apple Clang / CLT | 21.0.0 (`clang-2100.1.1.101`) / 26.6.0.0.1781586589 |
| Explicit SDK | `/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk` |
| Homebrew | 7.0.6, prefix `/opt/homebrew` |
| Python | 3.14.7 |
| CMake wheel | 4.4.3 |
| Ninja wheel | 1.13.2; binary reports `1.13.2.git.kitware.jobserver-pipe-1` |
| Python protobuf / protoc | 5.29.6 / 29.6 |
| Qt base, declarative, SVG, shader tools, serial port, WebChannel, positioning, WebEngine | 6.11.2 |
| Qt tools | 6.11.2_1 |
| FFmpeg | 9.0.1_1 |
| libavcodec / libavformat / libavutil | 63.1.101 / 63.1.101 / 61.1.101 |
| libswresample / libswscale | 7.1.101 / 10.1.101 |
| OpenSSL | 3.6.3 |
| SDL2 compatibility / SDL3 | 2.32.70 / 3.4.16 |
| Opus / speexdsp | 1.6.1 / 1.2.1 |
| libplacebo / shaderc | 7.360.1 / 2026.4 |
| Vulkan headers / loader | 1.4.357.0 / 1.4.357.0 |
| MoltenVK runtime (added after the initial baseline build) | 1.4.2 |
| json-c / miniupnpc / libevent | 0.19 / 2.3.3 / 2.1.13 |
| pkgconf | 3.0.7 |
| dbus / double-conversion / md4c | 1.16.2_1 / 3.4.0 / 0.6.0 |
| gumbo-parser / litehtml | 0.14.1 / 0.10_1 |
| Preserved xz | 5.8.3 |

The source forces deployment target 13.0 on arm64, but several installed Homebrew
libraries require newer macOS (some 26.0). The linker reports these warnings.
**This build is qualified only on the recorded host; it is not a macOS 13 release.**
Qt's GuiPrivate module also ties the executable to this exact Qt build. Rebuild
both comparison binaries if Qt changes.

### Vulkan runtime on macOS

The Vulkan renderer additionally needs a Vulkan implementation over Metal:
MoltenVK. The Vulkan loader alone does not supply that driver. The coordinator
installed the previously absent Homebrew `molten-vk` 1.4.2 on 4 October 2026,
after the initial baseline build, with `HOMEBREW_NO_AUTO_UPDATE=1`,
`HOMEBREW_NO_INSTALL_UPGRADE=1` and `HOMEBREW_NO_INSTALL_CLEANUP=1`. The existing
`vulkan-loader` 1.4.357.0 was retained; no application rebuild is implied by this
runtime addition. Both matched renderer tests must use this same recorded runtime.

The installation and symlink inspection confirm
`/opt/homebrew/etc/vulkan/icd.d/MoltenVK_icd.json` and
`/opt/homebrew/lib/libMoltenVK.dylib`, pointing into
`/opt/homebrew/Cellar/molten-vk/1.4.2`. The manifest refers to that dylib, advertises
Vulkan API 1.4.0 and marks it as a portability driver. A separate coordinator
probe then created a Vulkan instance with portability enumeration through the
default loader search and enumerated one device, `Apple M2`. That proves driver
availability; **the application's Vulkan selection, playback and stability
remain unverified**. The local review bundle still depends on this host runtime
and is not qualified for a clean machine.

Evidence: `../logs/20261004-103652-gbj866zb.log` (install),
`../logs/20261004-103758-1s1tq7z1.log` (manifest and dylib symlinks), and
`../logs/20261004-104207-xhu2wfy3.log` (Vulkan instance and device probe).

## Dependency setup

Run from this repository. All non-interactive build/check commands are captured:

```sh
export AI_AGENT_LOG_DIR="$(cd .. && pwd)/logs"
CAPTURE="$(command -v agent-capture)"
"$CAPTURE" git submodule update --init --recursive \
  test/munit third-party/nanopb third-party/jerasure \
  third-party/gf-complete third-party/curl third-party/cpp-steam-tools
python3 -m venv ../chiaki-python
"$CAPTURE" ../chiaki-python/bin/python -m pip install \
  protobuf==5.29.6 cmake==4.4.3 ninja==1.13.2
mkdir -p ../protoc-29.6
"$CAPTURE" curl -fL \
  https://github.com/protocolbuffers/protobuf/releases/download/v29.6/protoc-29.6-osx-aarch_64.zip \
  -o ../protoc-29.6/protoc.zip
"$CAPTURE" shasum -a 256 ../protoc-29.6/protoc.zip
unzip -q ../protoc-29.6/protoc.zip -d ../protoc-29.6
```

The 2,291,566-byte protoc archive SHA-256 is
`b9576b5fa1a1ef3fe13a8c91d9d8204b46545759bea5ae155cd6ba2ea4cdaeed`.
Protoc is isolated because installing Homebrew protobuf@29 would upgrade the
existing Abseil dependency. The Python tools are isolated in the venv.

The existing FFmpeg, OpenSSL, SDL, Opus, json-c, libevent and their dependencies
were preserved. Missing libraries were explicitly enumerated and installed:

```sh
export HOMEBREW_NO_AUTO_UPDATE=1
export HOMEBREW_NO_INSTALL_UPGRADE=1
export HOMEBREW_NO_INSTALL_CLEANUP=1
export HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1
"$CAPTURE" brew install --ignore-dependencies \
  pkgconf speexdsp miniupnpc shaderc vulkan-headers vulkan-loader libplacebo
"$CAPTURE" brew install --ignore-dependencies \
  dbus double-conversion md4c gumbo-parser litehtml \
  qtbase qtsvg qtdeclarative qtshadertools qtserialport qttools \
  qtwebchannel qtpositioning qtwebengine
```

These are the commands used on this host, not a general-purpose clean-machine
installer. Homebrew warns that `--ignore-dependencies` is an unsupported developer
option. Here every missing runtime dependency was enumerated first, and dynamic
loading of libplacebo, QtGui and QtWebEngineCore plus the full application build
was verified. On another machine, inspect the dry-run and installed versions;
do not blindly ignore missing dependencies or upgrade unrelated packages.
Current Homebrew formulae may differ from this version record. Exact reproduction
requires the recorded versions/bottles, not simply the latest formula names.

A normal `brew install qt@6 ...` dry-run proposed replacing ten installed
packages, including OpenSSL, despite `HOMEBREW_NO_INSTALL_UPGRADE=1`. That flag
does not prevent dependency upgrades. The replacing transaction was not run.
No services were enabled and no tap was trusted.

Use Vulkan-enabled Qt. The initially tried official Qt 6.8.3 macOS kit defines
`QT_FEATURE_vulkan -1` and cannot build this upstream. Homebrew Qt 6.11.2's bottle
was checked for `QVulkanInstance` and `QT_FEATURE_vulkan 1` before installation.
The unused official kit remains in `../qt/6.8.3` (7.0GB) and is not in the final
prefix path. It can be considered for cleanup after the complete prototype work.
SDK 15.4 was selected after the initial older-Qt build hit the removed SDK26 AGL
linker stub; the same SDK is retained for consistent baseline/feature builds.

Pinned submodules:

| Path | Revision |
| --- | --- |
| test/munit | `cfc3717cc0cff59ea1e88d5ea13e93621157f3cb` |
| third-party/nanopb | `cad3c18ef15a663e30e3e43e3a752b66378adec1` |
| third-party/jerasure | `505ccb4bc69eee8d7ea40a6089a056b99671134f` |
| third-party/gf-complete | `fa54a4670a5705c84abf6c24b92b0cd479625478` |
| third-party/curl | `b1ef0e1a01c0bb6ee5367bd9c186a603bde3615a` |
| third-party/cpp-steam-tools | `d36565f8eaca113efd454efe714126cd77a01512` |

Android and Switch submodules are not needed for this macOS build.

## Configure, build and test

```sh
export PATH="$PWD/../protoc-29.6/bin:$PWD/../chiaki-python/bin:$PATH"
"$CAPTURE" ../chiaki-python/bin/cmake --fresh -S . -B ../build-baseline -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_SYSROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
  -DCHIAKI_ENABLE_CLI=OFF \
  -DCHIAKI_ENABLE_STEAMDECK_NATIVE=OFF \
  -DCHIAKI_ENABLE_TESTS=ON \
  -DPYTHON_EXECUTABLE="$PWD/../chiaki-python/bin/python" \
  -DCMAKE_PREFIX_PATH="/opt/homebrew;/opt/homebrew/opt/openssl@3;$PWD/../protoc-29.6"
"$CAPTURE" ../chiaki-python/bin/cmake --build ../build-baseline \
  --target chiaki chiaki-unit
"$CAPTURE" ../chiaki-python/bin/ctest --test-dir ../build-baseline --output-on-failure
```

The baseline was built before feature edits. For subsequent feature work, change
both `-B`/`--build`/`--test-dir` paths to `../build-client`; leave all other
configuration and dependencies matched. The CLI and Steam Deck native integration
are disabled; GUI, tests, FFmpeg, SDL controller support, WebEngine, Steam shortcut
support, and Speex are enabled. The build uses the pinned bundled curl, nanopb,
Jerasure and GF-Complete.

Package the task-built library inside the app, then sign and verify the local
bundle before launching through the native GUI. Run once after the fresh link;
`-delete_rpath` requires the original, canonical build-directory path:

```sh
mkdir -p ../build-baseline/gui/chiaki.app/Contents/Frameworks
cp -p ../build-baseline/third-party/cpp-steam-tools/libcpp-steam-tools.dylib \
  ../build-baseline/gui/chiaki.app/Contents/Frameworks/
"$CAPTURE" install_name_tool \
  -change @rpath/libcpp-steam-tools.dylib \
  @executable_path/../Frameworks/libcpp-steam-tools.dylib \
  -delete_rpath "$(cd ../build-baseline/third-party/cpp-steam-tools && pwd)" \
  ../build-baseline/gui/chiaki.app/Contents/MacOS/chiaki
"$CAPTURE" codesign --force --sign - \
  ../build-baseline/gui/chiaki.app/Contents/Frameworks/libcpp-steam-tools.dylib
"$CAPTURE" codesign --force --entitlements gui/entitlements.xml --sign - \
  ../build-baseline/gui/chiaki.app
"$CAPTURE" codesign --verify --deep --strict --verbose=2 ../build-baseline/gui/chiaki.app
open ../build-baseline/gui/chiaki.app
```

The CMake-linked bundle initially failed signature verification with "code has no
resources but signature indicates they must be present". The local ad-hoc signing
step corrects this and verification passes. It is not Developer ID signing or
notarization. Apply the same packaging/signing steps with every `build-baseline`
path changed to `build-client`. A native launch also stalled inside dyld before
`main()` while resolving the task-built dylib outside the bundle under Documents;
a bounded `--help` diagnostic launched under Codex loaded that exact library and
exited successfully. Packaging it inside the app removed that external-library
access and the native GUI subsequently rendered successfully. No privacy permissions or system security settings were changed.

Do not capture account entry, registration codes, credentials, or saved settings
in terminal logs. Renderer, decoder, resolution, frame rate and controller
transport should be recorded without account values for a matched comparison.
The intended session is the user's own PS5 on the local network. User confirmed
Remote Play enabled and the controller connected over USB; hardware behavior
still requires observation.

## Evidence

Full logs are under the outer workspace `work/logs` (the directory selected by
`AI_AGENT_LOG_DIR`), with the following stable basenames:

| Evidence | Log |
| --- | --- |
| Final clean configuration | `20261004-082854-2nh3s4j3.log` |
| Final application + unit build | `20261004-082927-cd2eb7s0.log` |
| Final CTest (1/1 target) | `20261004-083047-vlf739_l.log` |
| Executable hash, architecture, dependency versions, clean source | `20261004-083048-nnu4fybw.log` |
| Final dependency paths and packaged hashes | `20261004-083515-_10tcrzd.log` |
| Deep strict bundle signature verification | `20261004-083501-uosm5ogz.log` |
| Native library installation | `20261004-081616-uv9xdvww.log` |
| Compatible Qt module installation | `20261004-082717-5p255011.log` |
| QtGui dynamic load | `20261004-082841-34dtkgpj.log` |
| QtWebEngineCore dynamic load | `20261004-082904-g6pk02su.log` |

Detailed µnit results remain in
`../build-baseline/Testing/Temporary/LastTest.log`. Captured summaries truncate
long compiler output; the full logs retain all warnings and failures. Existing
warnings include OpenSSL/FFmpeg/Qt deprecations, unchecked upstream file-open
results, private Qt API version coupling, and deployment-target mismatch.

## Initial prototype software verification and local review packaging

The Task 5 packaged feature application source was commit
`054cd29f729d1bf6d2972271f5a93ee1b9eeb3a4`. Its later documentation-only packaging
commit is identified in that source archive's `SOURCE-MANIFEST.json`; application
code in that package was unchanged from that feature commit. The final-review
quality-summary fix changed the home QML; the current refresh is identified below.
The `../build-client` configuration uses the exact host/toolchain recorded above and leaves
`../build-baseline` untouched.

The Task 5 build check completed without a relink (`ninja: no work to do`). The
three CTest targets passed: QML **60 results** (46 behavior/data rows and 14
initialization/cleanup calls), diagnostic **7 results**, and core **117 tests**.
QML sessions/controller shortcuts and diagnostic producer delivery are mocked;
the native application/hardware qualifications are tracked in
[VALIDATION.md](VALIDATION.md).

```sh
export AI_AGENT_LOG_DIR="$(cd .. && pwd)/logs"
CAPTURE="$(command -v agent-capture)"
"$CAPTURE" ../chiaki-python/bin/cmake --build ../build-client \
  --target chiaki chiaki-unit chiaki-gui-quick-tests chiaki-diagnostic-tests
"$CAPTURE" ../chiaki-python/bin/ctest --test-dir ../build-client --output-on-failure
"$CAPTURE" git diff --check
```

No repository-provided dependency vulnerability-audit command was found in the
tracked script/workflow inventory or CMake entry points. No new scanner was
installed and dependency vulnerability status is unverified.

The local output is `../../outputs/RemotePlayPrototype.app`. The initial guarded
copy used the already-tested feature bundle; Task 5 then reran the build and
CTest before completing packaging. The build check confirmed no source/binary
change. An existing output must never be overwritten for a new packaging run:

```sh
"$CAPTURE" sh -c 'test ! -e "$1" && ditto "$2" "$1"' _ \
  ../../outputs/RemotePlayPrototype.app ../build-client/gui/chiaki.app
"$CAPTURE" /opt/homebrew/Cellar/qtbase/6.11.2/bin/macdeployqt \
  ../../outputs/RemotePlayPrototype.app \
  -qmldir="$PWD/gui/src/qml" -libpath=/opt/homebrew/lib
```

`macdeployqt` packages the task-built `libcpp-steam-tools.dylib` as well as Qt and
linked third-party libraries. Its library-path rewrites and stripping mean the
packaged executable has a different hash from the CMake output. The exact
packaging result and limitations are in [VALIDATION.md](VALIDATION.md).

Source preservation uses `git archive` for the final main-repository commit
**and separately for each of the six initialized pinned macOS/test submodules**,
combining their contents at their normal paths. A bare main-repository archive
is insufficient. The archive inventory is checked for the application source,
all six submodule contents, reproduction documentation and licence notices.
Only committed files are included. Git databases, `.serena`, ignored SDD state,
local settings, credentials, logs and build trees are excluded. The unused
Android/Switch submodules are recorded by commit but are not included.

The source archive covers this derivative and its pinned macOS source
submodules. External Homebrew dependency source and full licence/notice
completeness have not been qualified for redistribution. Preserve installed
notices in `Contents/Resources/Notices`, keep this bundle for local review, and
complete dependency source/notice collection before any distribution.

The first QML scan omitted the separately imported WebEngine QML module. The
second deployment pass used the existing `scripts/qtwebengine_import.qml`:

```sh
"$CAPTURE" /opt/homebrew/Cellar/qtbase/6.11.2/bin/macdeployqt \
  ../../outputs/RemotePlayPrototype.app \
  -qmldir="$PWD/scripts" -libpath=/opt/homebrew/lib
```

Both passes completed successfully. The second pass warned that `qt.conf`
already existed. Its contents were inspected and already specify
`Plugins = PlugIns`, `Imports = Resources/qml`, and `QmlImports = Resources/qml`.
The `QtWebEngine` QML plugin, helper process, ICU data and resource packs are
present. Presence alone does not prove runtime WebEngine initialization.

Recursive Mach-O inspection (`otool -L` and `otool -l`, excluding each dylib's
own `LC_ID_DYLIB`) found 169 binary files. The main executable references system
and bundled dependencies, with `@rpath/libcpp-steam-tools.dylib` resolved through
`@executable_path/../Frameworks`. QtWebEngineProcess still directly references
eight Homebrew Qt frameworks; three Homebrew library RPATH directories remain
across the bundle. This is a **local-machine review build**, not a self-contained
or portable distribution. No app launch was performed by packaging.

After collecting notices and provenance resources, sign the local bundle with
its existing application entitlements, then verify it:

```sh
"$CAPTURE" codesign --force --entitlements gui/entitlements.xml --sign - \
  ../../outputs/RemotePlayPrototype.app
"$CAPTURE" codesign --verify --deep --strict --verbose=2 \
  ../../outputs/RemotePlayPrototype.app
```

The final source/packaging manifest and handoff beside the app identify the
source archive, its SHA-256, the packaged executable SHA-256 and final signing
logs. Signing establishes local code/resource integrity, not runtime acceptance,
Developer ID status, notarization or licence completeness.

## Current review package after the configured-quality fix

Current application source: `7cb24e78d501ee1ac136be4dff130e426ce589f1`. The
subsequent documentation-only refresh commit is identified in the adjacent
package/source manifests and archive `SOURCE-MANIFEST.json`. The source snapshot
is taken at that documentation commit; all application/test source remains exact
to the application commit above.

The application was rebuilt, including QML resource regeneration and relink,
before packaging (`20261004-104344-fjvlnuuc.log`). Full verbose CTest passed all
3/3 targets (`20261004-104402-_7tb_3pv.log`): **66 QML results** comprising 52
behavior/data rows plus 14 hooks, seven diagnostic results, and 117 core tests.
Packaging reuses that evidence after verifying the raw executable SHA-256 is
`322c1723e85c9aa1b79aba21d9102c238bf9920964cd6dda929326124b839ad0`. No relevant
source/build changes justify another build/test run.

The earlier package/source/manifests are preserved under
`../package-history-5dabfc863328`. The refreshed output is `RemotePlayPrototype-7cb24e7.app`. A fresh
macdeployqt pass stalled on a host child process, including blocked process
inspection/signalling. The final app instead uses a separate path and the prior
verified two-pass Qt/runtime payload. All copied payload files were compared by
SHA-256 before provenance updates; only the executable was replaced from
`build-client` and its load paths/RPATHs rebased to the previously verified map.
Notice/provenance resources are refreshed, then recursive load-path inspection
and final ad-hoc signing/verification are repeated. The incomplete
`RemotePlayPrototype.app` attempt is not the review app. Its final exact hashes and verification
log names are in `outputs/RemotePlayPrototype-package-manifest.json` relative to
the outer workspace. No native launch is performed by packaging.

MoltenVK 1.4.2 remains outside the bundle. Its default-loader Apple M2 probe
passed as recorded above; the current application setting remains OpenGL according
to the coordinator. No saved settings are read by this packaging task. Vulkan
application selection/playback is unverified. Installed Apache-2.0 licence and
SPDX files for this external runtime are retained with the bundle notices, without
copying the driver binary or ICD configuration. The local-machine and incomplete
redistribution qualification remain unchanged.
