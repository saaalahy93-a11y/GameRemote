# iOS manual signing and local IPA export

The owner has confirmed Apple team `4J27D8LXNK` and registered app identifier `com.ahmedalsalahy.gameremote`. The signing workflow uses those public identifiers. Version, build number, public URLs and the app's final export classification remain explicit owner inputs; this repository supplies no production URL or export answer.

`ios/scripts/sign-and-export.py` validates public configuration by default. Signing requires `--execute-signing`. The manual workflow is disabled by default and has no push, pull-request, scheduled or reusable trigger. Its export destination is always `export`: neither helper nor workflow uploads to App Store Connect or TestFlight, creates Apple credentials, or requests provisioning updates. The owner must separately authorize signing-secret setup and the hosted job before dispatching it.

## Development and store inputs

Unsigned `ios/scripts/build.sh` builds are unchanged. For **signed development device installation**, explicitly provide the first four values below and choose `--mode development`. Public links and export classification may remain empty. A development profile must include registered devices, the selected Apple Development certificate, and `get-task-allow=true`. The helper verifies a nonempty device list; it cannot establish that a particular intended phone is registered or that the app installs on it.

For **store distribution export**, choose `--mode store` and supply all eight values. Existing strict validation applies before any native command or credential access. Use an App Store distribution profile for the exact app identifier and the selected Apple Distribution certificate; development, ad hoc and enterprise profiles are rejected. An exported store IPA is not an App Store submission or proof of Apple's acceptance.

| Environment variable | Required value |
| --- | --- |
| `GR_IOS_BUNDLE_IDENTIFIER` | Registered app identifier; the workflow sets `com.ahmedalsalahy.gameremote` |
| `GR_IOS_DEVELOPMENT_TEAM` | Actual Apple team identifier; the workflow sets `4J27D8LXNK` |
| `GR_IOS_VERSION` | Owner-selected marketing version with three numeric parts |
| `GR_IOS_BUILD_NUMBER` | Owner-selected new build number; one to three numeric parts with 4/2/2 digit limits, first positive |
| `GR_IOS_PRIVACY_URL` | Public HTTPS policy covering this app and its final data practices; required for store export |
| `GR_IOS_SUPPORT_URL` | Public HTTPS support page with the publisher's maintained contact route; required for store export |
| `GR_IOS_SOURCE_URL` | Public HTTPS location providing the corresponding source for this exact distributed build; required for store export |
| `GR_IOS_EXPORT_CLASSIFICATION` | Owner's final `exempt` or `non-exempt` determination for the complete app's encryption; required for store export |

The validator rejects malformed values, placeholder/local hosts, IP endpoints, URL credentials and unresolved substitutions. Nonempty development links must also pass validation. These are syntax checks; they do not establish ownership, availability, policy accuracy or complete corresponding source. Settings and help expose configured links through the existing generated Info.plist.

This app includes protocol cryptography as well as HTTPS. Do not infer its export answer from HTTPS alone. `exempt` writes `ITSAppUsesNonExemptEncryption=false`; `non-exempt` writes `true`. No answer is inferred, and no `ITSEncryptionExportComplianceCode` is invented. Complete any required documentation for the final candidate before submission. See [Apple's export-compliance key guidance](https://help.apple.com/xcode/mac/current/en.lproj/dev0dc15d044.html).

## Configuration-only checks

With only the public environment values set, these commands perform no signing or export and read no signing credentials:

```sh
python3 ios/scripts/sign-and-export.py --mode development
python3 ios/scripts/sign-and-export.py --mode store
```

The existing store-only configuration preflight also remains available without Xcode or network access:

```sh
ios/scripts/preflight.sh --store-config
```

## Authorized signing inputs

The `ios-signing` GitHub environment must be configured by the owner before a signing run. Set environment review/branch restrictions appropriate for trusted release code, then select the matching development or distribution identity/profile before each mode's run. No environment, secret or certificate is provisioned by this change.

| Setting | Purpose |
| --- | --- |
| Environment variable `GR_IOS_SIGNING_IDENTITY` | Explicit 40-digit SHA-1 certificate fingerprint, not an automatic certificate selector |
| Secret `GR_IOS_CERTIFICATE_P12_BASE64` | Base64 of an existing PKCS#12 containing that certificate and private key |
| Secret `GR_IOS_CERTIFICATE_PASSWORD` | Nonempty PKCS#12 password; control characters are rejected |
| Secret `GR_IOS_PROFILE_BASE64` | Base64 of the existing matching `.mobileprovision` |

The workflow takes version and build number from required dispatch inputs, the confirmed team/app identifier from its explicit configuration, and optional public links/export classification from the same-named `GR_IOS_*` environment variables. Store mode requires every public value. Signing secrets are exposed only to the signing step; they are removed from native/build child environments. The helper checks profile team, exact app identifier, expiry, iOS platform, mode, certificate membership and UUID before importing the certificate.

For an authorized local run, select full Xcode 26.3 and the pinned host generators from [the iOS build guide](ios.md), provide the public values and signing secrets through the owner's approved secret mechanism, and choose fresh absolute output/state paths. Do not put secret values in command arguments or checked-in files. The explicit invocation is:

```sh
python3 ios/scripts/sign-and-export.py "$SIGNING_OUTPUT" \
  --mode development --state "$SIGNING_STATE" --execute-signing
```

Use `--mode store` only with the complete store inputs and a matching store distribution identity/profile. The lower-level `store-archive.py` also defaults to validation only and accepts explicit `--identity`, `--profile-uuid`, `--keychain` and `--execute-signing` arguments for an already prepared manual signing context. It produces an archive only; prefer `sign-and-export.py` for temporary credential setup, stronger archive/IPA checks and cleanup.

## Hosted execution and cleanup

`.github/workflows/ios-signing-export.yml` requires manual `execute_signing=true`, a private repository, and the `ios-signing` environment. It selects Xcode 26.3 / iPhoneOS SDK 26.2, Python 3.12, protobuf 5.29.6, CMake 3.31.6 and the existing checksum-pinned protoc 29.6 archive. Setup is bounded to five minutes; archive to thirty minutes and export to ten minutes, with at most two build jobs. The job limit is fifty minutes. There are no automatic build retries.

A fresh build and DerivedData directory are used for each attempt. Configure probes and static-library dependencies keep `CODE_SIGNING_ALLOWED=NO`. CMake applies the manual style, certificate fingerprint, profile UUID and temporary keychain only to `GameRemoteIOS`. The archive command enables the app through the custom `GR_IOS_ARCHIVE_SIGNING=YES` variable; it never globally applies the profile or signing permission to dependency targets. That variable defaults to `NO` on the app target, so even a cached manual configuration remains unsigned unless the archive command explicitly enables it. ExportOptions sets manual signing, the same certificate/profile, `destination=export`, no version/build rewriting and no symbol upload. The selected Xcode must advertise the required current export methods in `xcodebuild -help`; unsupported versions fail instead of silently falling back.

The helper runs one bounded phase at a time and starts each phase runner in a separate process session. On cancellation it forwards termination once, then waits for the runner to terminate and reap its child group before credential cleanup. Invoke the helper directly as above; nesting another short-grace deadline runner around it can interrupt this cleanup.

The helper creates a random temporary keychain and installs the profile in Xcode's current user provisioning-profile directory. It refuses to overwrite an existing profile with the same UUID. Password-bearing `security` commands travel through its interactive stdin, not process arguments. Credential tool output is captured and withheld from build logs. Decoded files and cleanup state use mode 0600; the temporary directory uses mode 0700.

Normal completion, exceptions and handled SIGINT/SIGTERM attempt to delete the installed profile and keychain, restore the previous keychain search list, and delete temporary credential files. Profile cleanup checks file identity and content ownership, and checkpoints successful cleanup steps so a retry preserves a replacement profile or an already restored search list. Cleanup errors fail the run and retain the non-secret state file for a retry. An `always()` workflow step independently retries cleanup after failures/timeouts, before artifact retention. If a local process is forcibly killed, run:

```sh
python3 ios/scripts/sign-and-export.py --cleanup-state "$SIGNING_STATE"
```

An uncatchable kill or lost runner can prevent application-level cleanup; the hosted workflow uses a disposable GitHub runner, not a persistent self-hosted machine. Raw signing/build logs, keychains, standalone profiles, PKCS#12 files, cleanup state and DerivedData are never artifact paths.

## IPA validation and retained evidence

Both the archive and exported app are checked for configured Info.plist values, device platform, executable, assets, privacy manifest and licence notices. The stronger export path verifies the full code signature, team and signed team entitlement, app identifier, mode entitlements, selected certificate fingerprint, embedded profile UUID and validity, arm64 architecture and iOS Mach-O platform. The IPA must have exactly `Payload/GameRemote.app`; unsafe, duplicate and symlink archive entries and excessive expansion are rejected. Case and Unicode filename aliases, including implicit ancestor directories, are rejected before extraction.

Only after validation **and cleanup** succeed does the helper create `deliverables/GameRemote.ipa` and `deliverables/verification.json`. The report contains public release identity/version, checkout HEAD commit, SHA-256, toolchain, completed verification categories and `uploaded_to_apple=false`. The `source_commit` field records checkout HEAD; it does not attest uncommitted local edits. The hosted path uses a fresh checkout of the selected workflow ref. The workflow retains only those two files for seven days, accessible to readers of the private repository. The signed app necessarily embeds its provisioning profile: artifact access includes the app and its embedded profile metadata, which can include team/certificate details and development device identifiers. No standalone profile or credential log is retained.

## Verification boundary and source references

`ios/tests/test_apple_signing.py` exercises public requirements, both profile modes, secret command handling, cleanup success/failures, replacement preservation, actual ZIP/file processing, export options and artifact gating using synthetic files and mocked Apple tools. It also runs a real, small host CMake configuration to inspect app/dependency target properties and real harmless child processes to verify deadlines, parent cancellation and process-group SIGINT cleanup. The affected tests in `ios/tests/test-release-config.py` exercise manual archive arguments and development/store separation. These establish code contracts only. Actual PKCS#12 import, Apple signature verification, Xcode archive/export, phone installation, launch/gameplay, production URLs and Apple's store validation still require separate authorized native evidence; no signing run was performed while implementing this helper.

Apple documents [Xcode 26.3 and SDK 26.2](https://developer.apple.com/documentation/xcode-release-notes/xcode-26_3-release-notes), [the provisioning-profile directory introduced in Xcode 16](https://developer.apple.com/documentation/xcode-release-notes/xcode-16-release-notes), [command-line archive/export](https://developer.apple.com/library/archive/technotes/tn2339/_index.html) and [app distribution](https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases). The `security -i` input format/EOF status is checked against [Apple's Security command implementation](https://github.com/apple-oss-distributions/Security/blob/main/SecurityTool/macOS/security.c). GitHub documents [temporary signing material and runner cleanup](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications).

## nanopb privacy resource

Apple's [required third-party SDK list](https://developer.apple.com/support/third-party-SDK-requirements/) includes nanopb at every version. CMake builds its C sources here, so Apple's separate signature requirement for SDKs supplied as binary dependencies does not apply to this dependency path; the final app still requires normal signing. The SDK's existing `spm_resources/PrivacyInfo.xcprivacy` is copied unchanged into `GameRemote.app/nanopb_Privacy.bundle`, with resource-bundle metadata. It remains separate from the app's own manifest. No dependency code, version or privacy answers change.

The focused `test_real_bundle_packages_app_and_dependency_manifests_separately` regression builds a tiny host C bundle and compares all packaged manifests byte for byte. It does not build the iOS app or establish App Store acceptance. The next authorized iOS archive must be inspected for both dependency bundles and included in Xcode's combined privacy report.

## curl privacy resource and scope

Apple requires [SDK code to declare its own required-reason APIs](https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api). The pinned, source-built curl contains `stat`/`fstat`, so `curl_Privacy.bundle` carries this integration's separate manifest. The app-root declaration remains for the executable containing that static code. [C617.1](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitype) covers file metadata inside the app container; this is not an upstream or general-purpose curl manifest, nor a declaration that timestamps are collected or transmitted.

The vendored tree identifies itself as curl `8.11.0-DEV`. `HTTP_ONLY` disables its `file://` protocol; the iOS configuration disables SSH and uses Secure Transport, which ignores build-time CA file defaults. Remaining metadata routines check regular-file type, permissions or size for optional cookie/HSTS/Alt-Svc persistence, MIME file parts and explicit TLS certificate filenames. No current core caller configures those file options. The iOS bridge leaves `holepunch_session` null and uses direct console registration/streaming; it does not expose the PSN curl path. These are source/call-path findings, not observed runtime file access.

The manifest preserves no tracking and no collected data for this integration and limits any file-metadata use to the app container. Reassess it before enabling file-backed curl options, PSN flows, another TLS backend or a new dependency version; the manifest does not enforce a path restriction at runtime. No curl flags, networking or cryptography change here. The packaging regression checks the exact curl declaration and separate app/nanopb resources; final Xcode privacy aggregation and App Store validation remain unverified.
