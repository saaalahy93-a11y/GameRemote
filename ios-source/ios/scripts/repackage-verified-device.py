#!/usr/bin/env python3
"""Package the unchanged verified Build 2 device code as publisher Build 3."""
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

from apple_signing import ManualSigning, decode_profile, public_config, validate_profile, verify_ipa, verify_signed_app

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_SHA = "7a122500a92eceb6c8a4fdf27e6db115957424a05233d2246d8960fdf0fe1148"
EXECUTABLE_SHA = "4890e80bed94e09e8ddacfdb03a5270b58b72985ed1003da260e3b555fa95daa"
ASSETS_SHA = "0b48206ca937a036491603b7470093a4f2c86cbc7355c6123f6de3f382aab908"
PROFILE_SHA = "79736d0477d53d25656c48c9ed3a8b596b776c4a183bb912c4e87b50860178bb"
IDENTITY = "77D03D37EDC8D46CED7343E60BD56E0CDF31F432"
TEAM = "4J27D8LXNK"
BUNDLE = "com.ahmedalsalahy.gameremote"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command):
    return subprocess.run(command, check=True, capture_output=True, timeout=120)


def privacy_resources(app):
    sources = {"PrivacyInfo.xcprivacy": ROOT / "ios/App/PrivacyInfo.xcprivacy"}
    for label, recipe, manifest in (
        ("nanopb_Privacy", "NanopbPrivacy.cmake", "third-party/nanopb/spm_resources/PrivacyInfo.xcprivacy"),
        ("curl_Privacy", "CurlPrivacy.cmake", "ios/Dependencies/curl/PrivacyInfo.xcprivacy"),
    ):
        text = (ROOT / "ios/cmake" / recipe).read_text()
        matches = re.findall(r'file\(WRITE "\$\{bundle\}/Info\.plist" \[=\[(.*?)\]=\]\)', text, re.S)
        if len(matches) != 1:
            raise ValueError("Expected the reviewed literal resource-bundle plist")
        info = matches[0].encode()
        if plistlib.loads(info).get("CFBundlePackageType") != "BNDL":
            raise ValueError("Privacy resource must be a resource-only bundle")
        directory = app / (label + ".bundle")
        directory.mkdir()
        (directory / "Info.plist").write_bytes(info)
        sources[label + ".bundle/PrivacyInfo.xcprivacy"] = ROOT / manifest
    for relative, source in sources.items():
        plistlib.loads(source.read_bytes())
        shutil.copyfile(source, app / relative)
    return {name: digest(app / name) for name in sources}


def package(args):
    config = public_config("store")
    required = {"DEVELOPMENT_TEAM": TEAM, "BUNDLE_IDENTIFIER": BUNDLE,
                "VERSION": "1.10.0", "BUILD_NUMBER": "3",
                "EXPORT_CLASSIFICATION": "defer-to-app-store-connect"}
    if any(config.values[key] != value for key, value in required.items()):
        raise ValueError("Only the approved GameRemote publisher Build 3 is supported")
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
    # This exact immutable 10-member archive was already downloaded and verified.
    with tarfile.open(args.archive, "r:gz") as archive:
        archive.extractall(payload, filter="data")
    app = payload / "GameRemote.app"
    if digest(app / "GameRemote") != EXECUTABLE_SHA or digest(app / "Assets.car") != ASSETS_SHA:
        raise ValueError("Previously verified native code or assets changed")
    if (app / "Frameworks").exists() or (app / "PlugIns").exists():
        raise ValueError("This reuse recipe does not support nested executable code")
    old_info = plistlib.loads((app / "Info.plist").read_bytes())
    info = dict(old_info)
    changed = {"CFBundleIdentifier": BUNDLE, "CFBundleShortVersionString": "1.10.0",
               "CFBundleVersion": "3", "GameRemotePrivacyPolicyURL": config.values["PRIVACY_URL"],
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
    ipa = args.output / "GameRemote-1.10.0-build3.ipa"
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
              "native_source_commit": "7e9e397e07f677282beb1af76448d587f79f300e",
              "metadata_source_commit": "432b5e8f72e42c0b47f6568f8a9560e4d0b678e9",
              "public_configuration": config.values, "signing_certificate_sha1": IDENTITY,
              "profile_sha256": PROFILE_SHA, "changed_info_keys": sorted(changed),
              "privacy_manifests": privacy, "embedded_swift_runtime": [],
              "key_exported": False, "new_native_build": False, "uploaded": False,
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
