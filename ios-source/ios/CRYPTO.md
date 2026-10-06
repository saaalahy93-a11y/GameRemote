# iOS crypto dependency qualification — 6 October 2026

The core Mbed TLS backend now uses 3.6.7 from the official release archive,
SHA-256 `a7e8bcbec0e6f761b4af24f25677626b35f762f68eef79c08677a363212d11f6`.
The upstream 3.6 LTS branch is supported through March 2027. This replaces the
inherited 2.28.0 pin; no exploited vulnerability in GameRemote is asserted.

The migration removes private ECDH-context field access, retains entropy until
DRBG finalization, preserves imported keypairs, and uses the current one-shot
GCM interface. ECDH verifies the supplied HMAC-SHA256 over the raw uncompressed
public key, rejects malformed curve points and checks output capacities before
writing. The stream BANG caller already supplies the remote signature and the
session handshake key; rejection follows its existing failed-session path.

Recorded on-wire public keys, HMAC signatures, shared secrets and GMAC vectors
remain unchanged. Tests cover valid imported/generated keys, two-peer agreement,
tampered/truncated signatures, signed malformed points and output bounds. They
exercise real Mbed TLS and OpenSSL, rather than replacing cryptography with mocks.

| Check | Result | Coordinator evidence |
| --- | --- | --- |
| Mbed TLS 3.6.7 core suite | 108 passed; 1 existing platform socket skip | `work/logs/20261006-073018-y1ksjs9n.log` |
| OpenSSL 3.6.3 core suite | 119 passed; same socket skip | Same combined log |
| Mbed ECDH wrapper ASan/UBSan | 6 passed | `work/logs/20261006-073105-9r0az227.log` |
| OpenSSL ECDH wrapper ASan/UBSan | 5 passed | `work/logs/20261006-073105-dq0b9oso.log` |
| Independent C/crypto review | No actionable findings | Coordinator review record |

The socket skip reflects macOS clamping an oversized requested receive buffer;
no cryptography case is skipped. Sanitizer runs instrumented the wrapper/test
code, not the dependency binaries. Allocation failures were reviewed statically,
not injected. Host suites do not establish native iOS linking or physical
PS4/PS5 handshake, stream quality or controller behavior. Accepted macOS/Android
packages are separate unchanged binaries.

Run `ios/scripts/test-crypto-host.sh` with pinned host code-generation tools and
the documented host dependencies. Native iOS verification must use a full build
after these production changes, never reuse the earlier simulator archive.
Use `ios/scripts/build.sh` or the manual `release-ios.yml` workflow with
`continue_candidate=false`. Physical-device qualification and export/licence
decisions remain release gates.

References: [Mbed TLS 3.6.7](https://github.com/Mbed-TLS/mbedtls/releases/tag/mbedtls-3.6.7),
[upstream branch support policy](https://github.com/Mbed-TLS/mbedtls/blob/development/BRANCHES.md).
