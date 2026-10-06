"""Sign the verified native HMAC-fix device artifact as publisher Build 4."""
import argparse
import hashlib
import json
import plistlib
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

from apple_signing import (
    ManualSigning,
    decode_profile,
    public_config,
    validate_profile,
    verify_ipa,
    verify_signed_app,
)

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_SHA = "68a15a69aea24e93c0f9eb0e245052195f1bead2e820538d754c79066789e464"
EXECUTABLE_SHA = "42c5f03c4a64298fde31521516279cb4937cac32207f60ff969bf369cf616907"
ASSETS_SHA = "ac6cf17a0a818d6cd95f73ae5c8c7ccfc39c7992f4939579e0eaa0503d0cc468"
NATIVE_COMMIT = "d2a49d168aa22aa1d0bd050f146edb6582d9b961"
PROFILE_SHA = "79736d0477d53d25656c48c9ed3a8b596b776c4a183bb912c4e87b50860178bb"
IDENTITY = "77D03D37EDC8D46CED7343E60BD56E0CDF31F432"
TEAM = "4J27D8LXNK"
BUNDLE = "com.ahmedalsalahy.gameremote"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command):
    return subprocess.run(command, check=True, capture_output=True, timeout=120)


def privacy_resources(app):
    """Verify the native artifact already contains the reviewed privacy resources."""
    sources = {"PrivacyInfo.xcprivacy": ROOT / "ios/App/PrivacyInfo.xcprivacy"}
    for label, recipe, manifest in (
        ("nanopb_Privacy", "NanopbPrivacy.cmake", "third-party/nanopb/spm_resources/PrivacyInfo.xcprivacy"),
        ("curl_Privacy", "CurlPrivacy.cmake", "ios/Dependencies/curl/PrivacyInfo.xcprivacy"),
    ):
        text = (ROOT / "ios/cmake" / recipe).read_text()
        matches = re.findall(r'file\(WRITE "\$\{bundle\}/Info\.plist" \[=\[(.*?)\]=\]\)', text, re.DOTALL)
        if len(matches) != 1:
            raise ValueError("Expected the reviewed literal resource-bundle plist")
        info = matches[0].encode()
        if plistlib.loads(info).get("CFBundlePackageType") != "BNDL":
            raise ValueError("Privacy resource must be a resource-only bundle")
        directory = app / (label + ".bundle")
        if directory.is_symlink() or not directory.is_dir() or \
                {path.name for path in directory.iterdir()} != {"Info.plist", "PrivacyInfo.xcprivacy"}:
            raise ValueError("Unexpected privacy resource bundle members")
        if (directory / "Info.plist").is_symlink() or (directory / "Info.plist").read_bytes() != info:
            raise ValueError("Native privacy bundle plist differs from reviewed source")
        sources[label + ".bundle/PrivacyInfo.xcprivacy"] = ROOT / manifest
    for relative, source in sources.items():
        plistlib.loads(source.read_bytes())
        target = app / relative
        if target.is_symlink() or target.read_bytes() != source.read_bytes():
            raise ValueError("Native privacy manifest differs from reviewed source")
    return {name: digest(app / name) for name in sources}


def package(args):
    config = public_config("store")
    required = {"DEVELOPMENT_TEAM": TEAM, "BUNDLE_IDENTIFIER": BUNDLE,
                "VERSION": "1.10.0", "BUILD_NUMBER": "4",
                "EXPORT_CLASSIFICATION": "defer-to-app-store-connect"}
    if any(config.values[key] != value for key, value in required.items()):
        raise ValueError("Only the approved GameRemote publisher Build 4 is supported")
    if not args.execute_signing:
        raise ValueError("Explicit --execute-signing is required")
    if digest(args.archive) != ARCHIVE_SHA or digest(args.profile) != PROFILE_SHA:
        raise ValueError("Verified input archive or approved profile does not match")
    if not args.output.is_absolute() or args.output.exists() or args.output.is_symlink():
        raise ValueError("A fresh absolute output directory is required")
    profile = decode_profile(args.profile)
    profile_uuid = validate_profile(profile, config, IDENTITY)
    signing = ManualSigning(IDENTITY, profile_uuid, args.keychain)
    signing.validate()
    args.output.mkdir(mode=0o700)
    payload = args.output / "Payload"
    payload.mkdir()
    # This exact immutable 16-member archive is from device run 37524826816.
    with tarfile.open(args.archive, "r:gz") as archive:
        archive.extractall(payload, filter="data")
    app = payload / "GameRemote.app"
    if digest(app / "GameRemote") != EXECUTABLE_SHA or digest(app / "Assets.car") != ASSETS_SHA:
        raise ValueError("Verified native code or assets changed")
    if (app / "Frameworks").exists() or (app / "PlugIns").exists():
        raise ValueError("This signing recipe does not support nested executable code")
    old_info = plistlib.loads((app / "Info.plist").read_bytes())
    info = dict(old_info)
    changed = {"CFBundleIdentifier": BUNDLE, "CFBundleShortVersionString": "1.10.0",
               "CFBundleVersion": "4", "GameRemotePrivacyPolicyURL": config.values["PRIVACY_URL"],
               "GameRemoteSupportURL": config.values["SUPPORT_URL"],
               "GameRemoteSourceURL": config.values["SOURCE_URL"]}
    info.update(changed)
    for key in ("ITSAppUsesNonExemptEncryption", "ITSEncryptionExportComplianceCode"):
        info.pop(key, None)
    (app / "Info.plist").write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
    config.verify_plist(app / "Info.plist")
    privacy = privacy_resources(app)
    shutil.copyfile(args.profile, app / "embedded.mobileprovision")
    profile_entitlements = profile["Entitlements"]
    app_identifier = TEAM + "." + BUNDLE
    allowed_groups = profile_entitlements.get("keychain-access-groups", [])
    if app_identifier not in allowed_groups and TEAM + ".*" not in allowed_groups:
        raise ValueError("Profile does not allow the app's default keychain group")
    entitlements = {"application-identifier": app_identifier,
                    "com.apple.developer.team-identifier": TEAM,
                    "get-task-allow": False, "keychain-access-groups": [app_identifier]}
    if profile_entitlements.get("beta-reports-active") is True:
        entitlements["beta-reports-active"] = True
    entitlement_file = args.output / "distribution-entitlements.plist"
    entitlement_file.write_bytes(plistlib.dumps(entitlements))
    if digest(app / "GameRemote") != EXECUTABLE_SHA or digest(app / "Assets.car") != ASSETS_SHA:
        raise ValueError("Packaging unexpectedly changed code or assets before signing")
    run(["/usr/bin/codesign", "--force", "--sign", IDENTITY, "--keychain", str(args.keychain),
         "--timestamp=none", "--generate-entitlement-der", "--entitlements", str(entitlement_file), str(app)])
    verify_signed_app(app, config, signing)
    for name, expected in privacy.items():
        if digest(app / name) != expected:
            raise ValueError("Signing changed a privacy manifest")
    ipa = args.output / "GameRemote-1.10.0-build4.ipa"
    with zipfile.ZipFile(ipa, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(payload.rglob("*")):
            if path.is_symlink():
                raise ValueError("Unexpected symlink in signed app")
            if path.is_file():
                archive.write(path, path.relative_to(args.output).as_posix())
    verify_ipa(ipa, config, signing)
    if digest(args.archive) != ARCHIVE_SHA or digest(args.profile) != PROFILE_SHA:
        raise ValueError("Original release input changed")
    report = {"status": "LOCALLY_SIGNED_IPA_VERIFIED", "ipa": ipa.name, "ipa_sha256": digest(ipa),
              "base_archive_sha256": ARCHIVE_SHA, "base_executable_sha256": EXECUTABLE_SHA,
              "signed_executable_sha256": digest(app / "GameRemote"), "assets_sha256": digest(app / "Assets.car"),
              "native_source_commit": NATIVE_COMMIT, "native_build_run_id": 37524826816,
              "metadata_source_commit": NATIVE_COMMIT,
              "packaging_recipe_sha256": digest(Path(__file__)),
              "packaging_commit": run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.decode().strip(),
              "public_configuration": config.values, "signing_certificate_sha1": IDENTITY,
              "profile_sha256": PROFILE_SHA, "changed_info_keys": sorted(changed),
              "privacy_manifests": privacy, "embedded_swift_runtime": [],
              "key_exported": False, "new_native_build": True, "uploaded": False,
              "submission_ready": False, "export_declaration_pending": True,
              "limits": ["Apple processing and physical-device playback remain unverified."]}
    (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.output / "SHA256SUMS").write_text(digest(ipa) + "  " + ipa.name + "\n")
    return ipa


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "profile", "keychain", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--execute-signing", action="store_true")
    args = parser.parse_args()
    try:
        print("Verified signed candidate: " + str(package(args)))
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError, plistlib.InvalidFileException) as error:
        print("Packaging failed: " + type(error).__name__ + "; no successful release claim.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
