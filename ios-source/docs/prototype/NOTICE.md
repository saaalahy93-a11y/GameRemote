# Local derivative and third-party notices

This local PS5 Remote Play prototype is a derivative of
[chiaki-ng](https://github.com/streetpea/chiaki-ng), based on upstream revision
`a9a2805884cfa83865fdfcc09ca3ddfcd628aa42` (1.10.0). Chiaki-ng builds on the
original Chiaki project. Preserve the upstream author, copyright, attribution,
and licence notices throughout the source and application.

The prototype begins as **AGPL-3.0-only**. The authoritative licence text remains
in [`COPYING`](../../COPYING); also preserve the existing OpenSSL additional
permission in
[`LICENSES/AGPL-3.0-only-OpenSSL.txt`](../../LICENSES/AGPL-3.0-only-OpenSSL.txt).
This notice does not replace those texts or grant a different licence.

The modified prototype application source is commit
`7cb24e78d501ee1ac136be4dff130e426ce589f1`; the source snapshot manifest identifies
the later documentation-only packaging commit. The changes provide an explicit
setup/home flow, guarded connection/recovery actions, persistent session errors,
diagnostics that distinguish unavailable values from valid zero, and a reactive
local PS5 configured-quality summary. This is a local review build; no binary or source publication was performed.

Before any distribution, provide the corresponding source for the exact binary,
its modifications, required third-party source/notices, and the exact scripts
and instructions needed to build/install it. Include [BUILD.md](BUILD.md), the
pinned source/submodule revisions, dependency versions and any subsequent build
adjustments. Retain the applicable AGPL network-interaction source offer where
required by the licence. The full licence texts govern these requirements.

Preserve the notices shipped with every bundled or linked component, including:

| Component | Existing notice/source location |
| --- | --- |
| nanopb | `third-party/nanopb/LICENSE.txt`, `AUTHORS.txt` |
| Jerasure | `third-party/jerasure/COPYING`, `AUTHORS` |
| GF-Complete | `third-party/gf-complete/COPYING`, `AUTHORS` |
| curl | `third-party/curl/COPYING`, `LICENSES/` |
| cpp-steam-tools | `third-party/cpp-steam-tools/LICENSE` |
| µnit (tests) | `test/munit/COPYING` |
| Qt and Qt WebEngine | Exact Qt module licence texts and WebEngine's third-party notices |
| FFmpeg and enabled codecs | Exact FFmpeg build's licence/configuration and component notices |
| OpenSSL, SDL2 compatibility, SDL3, Opus, SpeexDSP, libplacebo | Exact dependency source/licence packages |
| Vulkan loader/headers, shaderc, json-c, miniupnpc, libevent and other linked libraries | Exact dependency source/licence packages |

The local `.app` is not a self-contained distribution bundle. A release must
inventory the components actually included; this list is an orientation, not a
substitute for collecting their complete licences and corresponding source.

This project is not endorsed or certified by Sony Interactive Entertainment LLC.
PlayStation and PS5 names are used to identify compatible hardware; no endorsement
or ownership of those marks is claimed. No warranty is provided except where
separately required or offered under the governing licences.

## Local review deliverables

The review app retains the project AGPL/OpenSSL licence texts and notices from
the six macOS source submodules under `Contents/Resources/Notices`. Installed
Homebrew licence files and SPDX inventories are collected for bundled
components where present. An SPDX inventory is not a substitute for a licence
text or corresponding source, and a lack of installed notice files is explicitly
recorded in the packaging inventory.

The source archive preserves the exact committed derivative plus the initialized
pinned submodules. It excludes Git databases, settings, credentials, logs, build
products and tooling state. Unused Android/Switch submodules are recorded by pin.
It does not include all external Homebrew dependency source. Full Qt/WebEngine
third-party notices and dependency source/licence obligations still require
release review; this local collection does not establish redistribution
readiness. No external distribution was performed.

The host now also supplies MoltenVK 1.4.2 as an **external runtime driver** via
Homebrew's default Vulkan ICD search. Its installed Apache License 2.0 text and
SPDX inventory are preserved under `Notices/external-runtime/molten-vk/1.4.2`.
The driver binary and ICD manifest are not packaged in the app. A successful
standalone device probe does not verify application Vulkan playback or complete
all third-party source/notice obligations.
