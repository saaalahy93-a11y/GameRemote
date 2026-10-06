#!/usr/bin/env python3
"""Explicitly sign and export a local IPA. Default validates public inputs only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import sys
import zipfile

from apple_signing import SECRET_NAMES, cleanup_signing, native, public_config, temporary_signing, verify_ipa, verify_signed_app

ROOT = Path(__file__).resolve().parents[2]


def bounded_phase(command, log, *, stall, limit, environment):
    """One bounded child group at a time; reap it before credential cleanup."""
    runner = [sys.executable, str(ROOT / "ios/scripts/run-bounded.py"),
              "--stall", str(stall), "--limit", str(limit), "--log", str(log), "--", *command]
    # Isolate the runner so a terminal's group SIGINT reaches this orchestrator
    # once; forwarding it must not interrupt the runner's own group cleanup.
    process = subprocess.Popen(runner, env=environment, start_new_session=True)
    try:
        result = process.wait()
    except BaseException:
        if process.poll() is None:
            process.terminate()
        # The runner owns and terminates its child's group before it exits. Do
        # not race it with another identical TERM/KILL deadline or early cleanup.
        process.wait()
        raise
    if result:
        raise subprocess.CalledProcessError(result, command)


def pinned_toolchain():
    if native(["xcodebuild", "-version"]).stdout.splitlines()[:1] != ["Xcode 26.3"]:
        raise ValueError("Signing requires the selected Xcode 26.3")
    if native(["xcrun", "--sdk", "iphoneos", "--show-sdk-version"]).stdout.strip() != "26.2":
        raise ValueError("Signing requires the iPhoneOS 26.2 SDK")
    help_text = native(["xcodebuild", "-help"])
    for value in ("app-store-connect", "debugging", "provisioningProfiles", "signingCertificate"):
        if value not in help_text.stdout + help_text.stderr:
            raise ValueError("Selected Xcode does not advertise the required manual export options")


def sign_and_export(output, mode, identity, state):
    config = public_config(mode)
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise ValueError("Export output must be a fresh absolute directory")
    print("Checking pinned Xcode and SDK.", flush=True)
    pinned_toolchain()
    print("Validating the profile and preparing temporary manual signing.", flush=True)
    with temporary_signing(config, identity, state) as signing:
        print("Creating and verifying the manual archive.", flush=True)
        environment = {key: value for key, value in os.environ.items() if key not in SECRET_NAMES}
        bounded_phase([sys.executable, str(ROOT / "ios/scripts/store-archive.py"), str(output),
                       "--mode", mode, "--identity", signing.identity, "--profile-uuid", signing.profile_uuid,
                       "--keychain", str(signing.keychain), "--execute-signing"],
                      output.with_name(output.name + "-archive.log"), stall=300, limit=1800, environment=environment)
        archive = output / "GameRemote.xcarchive"
        verify_signed_app(archive / "Products/Applications/GameRemote.app", config, signing)
        options = output / "ExportOptions.plist"
        options.write_bytes(plistlib.dumps(signing.export_options(config)))
        export = output / "export"
        print("Exporting the IPA locally.", flush=True)
        bounded_phase(["xcodebuild", "-exportArchive", "-archivePath", str(archive),
                       "-exportOptionsPlist", str(options), "-exportPath", str(export)],
                      output / "export.log", stall=180, limit=600, environment=environment)
        ipas = list(export.glob("*.ipa"))
        if len(ipas) != 1:
            raise ValueError("Export must produce exactly one IPA")
        print("Verifying the exported IPA.", flush=True)
        verify_ipa(ipas[0], config, signing)
        verified_ipa = ipas[0]
        print("Removing temporary signing material before retaining deliverables.", flush=True)
    # Publishable artifacts are assembled only after validation AND credential cleanup succeed.
    deliverables = output / "deliverables"
    deliverables.mkdir()
    ipa = deliverables / "GameRemote.ipa"
    shutil.copyfile(verified_ipa, ipa)
    report = {"mode": mode, "bundle_identifier": config.values["BUNDLE_IDENTIFIER"],
              "team": config.values["DEVELOPMENT_TEAM"], "version": config.values["VERSION"],
              "build": config.values["BUILD_NUMBER"], "sha256": hashlib.sha256(ipa.read_bytes()).hexdigest(),
              "xcode": "26.3", "sdk": "26.2", "source_commit": native(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip(),
              "verified": ["metadata", "signature", "signing-certificate", "profile", "entitlements", "arm64-ios", "resources"],
              "export_classification": config.values["EXPORT_CLASSIFICATION"],
              "export_declaration_pending": config.values["EXPORT_CLASSIFICATION"] not in {"exempt", "non-exempt"},
              "submission_ready": False,
              "uploaded_to_apple": False}
    (deliverables / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return ipa


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--mode", choices=("development", "store"), default="development")
    parser.add_argument("--identity", default=os.environ.get("GR_IOS_SIGNING_IDENTITY", ""))
    parser.add_argument("--state", type=Path)
    parser.add_argument("--execute-signing", action="store_true")
    parser.add_argument("--cleanup-state", type=Path)
    args = parser.parse_args()
    def interrupted(signum, _frame):
        raise InterruptedError("Signing interrupted")
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    try:
        if args.cleanup_state:
            cleanup_signing(args.cleanup_state)
            return 0
        try:
            public_config(args.mode)
        except ValueError as error:
            # These messages are field names/rules from the public-only validator.
            print("FAIL public signing configuration:\n" + str(error), file=sys.stderr)
            return 2
        if not args.execute_signing:
            print("Public signing configuration valid; no credentials read, signing, export or upload performed.")
            return 0
        if args.output is None or args.state is None:
            raise ValueError("Explicit signing requires output and --state paths")
        ipa = sign_and_export(args.output, args.mode, args.identity, args.state)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile):
        # Never include a credential-tool argv, input or raw response in a failure message.
        print("FAIL signing/export. No deliverable should be used; inspect the bounded non-credential build log and cleanup result.", file=sys.stderr)
        return 2
    print("Validated local IPA: " + str(ipa))
    print("No Apple upload or store validation was performed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
