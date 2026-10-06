#!/usr/bin/env python3
"""Signing contracts with synthetic files and mocked Apple tools; never uses credentials."""
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ios/scripts"))
# These local scripts are not an installed package; resolve them after path setup.
import apple_signing as signing  # noqa: E402
from release_config import URL_PLIST_KEYS  # noqa: E402

spec = importlib.util.spec_from_file_location("sign_and_export", ROOT / "ios/scripts/sign-and-export.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)

# These fixtures are not valid credentials and never reach Apple's tools or network.
CERTIFICATE = b"synthetic certificate, not a real DER certificate"
IDENTITY = hashlib.sha1(CERTIFICATE).hexdigest().upper()
UUID = "12345678-1234-4321-8765-123456789ABC"
PUBLIC = {
    "GR_IOS_BUNDLE_IDENTIFIER": "com.validation.GameRemote",
    "GR_IOS_DEVELOPMENT_TEAM": "A1B2C3D4E5",
    "GR_IOS_VERSION": "2.3.4",
    "GR_IOS_BUILD_NUMBER": "27.3.1",
}
STORE = {**PUBLIC, "GR_IOS_PRIVACY_URL": "https://www.apple.com/privacy/",
         "GR_IOS_SUPPORT_URL": "https://support.apple.com/", "GR_IOS_SOURCE_URL": "https://github.com/",
         "GR_IOS_EXPORT_CLASSIFICATION": "non-exempt"}
SECRETS = dict(zip(signing.SECRET_NAMES, (base64.b64encode(b"synthetic p12").decode(),
                                       'fixture "password" \\ value', base64.b64encode(b"synthetic profile").decode())))


def profile(config):
    value = {"UUID": UUID, "TeamIdentifier": [config.values["DEVELOPMENT_TEAM"]], "Platform": ["iOS"],
             "ExpirationDate": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
             "DeveloperCertificates": [CERTIFICATE], "Entitlements": {
                 "com.apple.developer.team-identifier": config.values["DEVELOPMENT_TEAM"],
                 "application-identifier": config.values["DEVELOPMENT_TEAM"] + "." + config.values["BUNDLE_IDENTIFIER"],
                 "get-task-allow": not config.store}}
    if not config.store:
        value["ProvisionedDevices"] = ["synthetic registered device"]
    return value


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gameremote-signing-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name).resolve()
        self.config = signing.public_config("development", PUBLIC)
        self.manual = signing.ManualSigning(IDENTITY, UUID, self.path / "signing.keychain-db")
        self.home = self.path / "home"
        self.home.mkdir()
        self.state = self.path / "state.json"
        self.installed = self.home / "Library/Developer/Xcode/UserData/Provisioning Profiles" / (UUID + ".mobileprovision")

    def app(self, config=None):
        config = config or self.config
        app = self.path / "source/Payload/GameRemote.app"
        app.mkdir(parents=True, exist_ok=True)
        info = {"CFBundleIdentifier": config.values["BUNDLE_IDENTIFIER"], "CFBundleVersion": config.values["BUILD_NUMBER"],
                "CFBundleShortVersionString": config.values["VERSION"], "CFBundleExecutable": "GameRemote",
                "CFBundleSupportedPlatforms": ["iPhoneOS"],
                **{key: config.values[field] for field, key in URL_PLIST_KEYS.items()}}
        if config.values["EXPORT_CLASSIFICATION"]:
            info["ITSAppUsesNonExemptEncryption"] = config.values["EXPORT_CLASSIFICATION"] == "non-exempt"
        (app / "Info.plist").write_bytes(plistlib.dumps(info))
        for name in ("GameRemote", "Assets.car", "PrivacyInfo.xcprivacy", "AGPL-3.0-only-OpenSSL.txt",
                     "ThirdPartyNotices.txt", "embedded.mobileprovision"):
            (app / name).write_bytes(b"synthetic app resource")
        (app / "GameRemote").chmod(0o755)
        return app

    def ipa(self, app):
        ipa = self.path / "fixture.ipa"
        with zipfile.ZipFile(ipa, "w") as archive:
            for path in app.iterdir():
                archive.write(path, "Payload/GameRemote.app/" + path.name)
        return ipa

    def native_app(self, config=None, overrides=None):
        config = config or self.config
        overrides = overrides or {}

        def run(command, **kwargs):
            stdout, stderr = "", ""
            if command[:3] == ["codesign", "--verify", "--deep"]:
                if overrides.get("signature_failure"):
                    raise RuntimeError("synthetic signature failure")
            elif command[:3] == ["codesign", "--display", "--verbose=4"]:
                stderr = "TeamIdentifier=" + overrides.get("team", config.values["DEVELOPMENT_TEAM"])
            elif command[:3] == ["codesign", "--display", "--entitlements"]:
                # Current codesign defaults to a human-readable DER description;
                # XML must be requested before the verifier can parse a plist.
                stdout = (plistlib.dumps(overrides.get("entitlements", profile(config)["Entitlements"])).decode()
                          if "--xml" in command else "[Dict]\n    [Key] application-identifier\n    [Value] [String] fixture\n")
            elif command[:3] == ["security", "cms", "-D"]:
                stdout = plistlib.dumps(overrides.get("profile", profile(config))).decode()
            elif command[:2] == ["lipo", "-archs"]:
                stdout = overrides.get("architecture", "arm64")
            elif command[:3] == ["xcrun", "vtool", "-show-build"]:
                stdout = "   platform " + overrides.get("platform", "IOS") + "\n"
            elif command[:3] == ["codesign", "--display", "--extract-certificates"]:
                Path(command[3] + "0").write_bytes(overrides.get("certificate", CERTIFICATE))
            else:
                self.fail("Unexpected native command: " + str(command))
            return subprocess.CompletedProcess(command, 0, stdout, stderr)
        return run

    def lifecycle_native(self, commands, fail=None):
        def run(command, **kwargs):
            commands.append(command)
            if command == ["security", "list-keychains", "-d", "user"]:
                stdout = '"/synthetic/original.keychain-db"\n'
            elif command[:3] == ["security", "cms", "-D"]:
                stdout = plistlib.dumps(profile(self.config)).decode()
            elif command == ["security", "-q", "-i"]:
                parsed = shlex.split(kwargs["input"])
                commands.append(parsed[:1])
                if parsed[0] == "create-keychain":
                    Path(parsed[-1]).touch()
                if parsed[0] == fail:
                    raise RuntimeError("synthetic import failure")
                stdout = ""
            elif command[:2] == ["security", "find-identity"]:
                stdout = IDENTITY
            elif command[:2] == ["security", "delete-keychain"]:
                if fail == "delete-keychain":
                    raise RuntimeError("synthetic keychain removal failure")
                Path(command[-1]).unlink()
                stdout = ""
            elif command[:5] == ["security", "list-keychains", "-d", "user", "-s"]:
                stdout = ""
            else:
                self.fail("Unexpected lifecycle command: " + str(command))
            return subprocess.CompletedProcess(command, 0, stdout, "")
        return run

    def test_development_requires_four_owner_values_but_no_store_urls(self):
        self.assertEqual(self.config.values["PRIVACY_URL"], "")
        for name in PUBLIC:
            with self.subTest(name=name), self.assertRaises(ValueError):
                signing.public_config("development", {key: value for key, value in PUBLIC.items() if key != name})

    def test_store_keeps_all_eight_required_values(self):
        signing.public_config("store", STORE)
        for name in STORE:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, name):
                signing.public_config("store", {key: value for key, value in STORE.items() if key != name})

    def test_manual_inputs_and_export_options_are_explicit_and_never_upload(self):
        for mode, environment, method in (("development", PUBLIC, "debugging"), ("store", STORE, "app-store-connect")):
            config = signing.public_config(mode, environment)
            options = self.manual.export_options(config)
            self.assertEqual(options["method"], method)
            self.assertEqual(options["destination"], "export")
            self.assertEqual(options["signingStyle"], "manual")
            self.assertEqual(options["signingCertificate"], IDENTITY)
            self.assertEqual(options["provisioningProfiles"], {config.values["BUNDLE_IDENTIFIER"]: UUID})
            self.assertFalse(options["manageAppVersionAndBuildNumber"])
            self.assertFalse(options["uploadSymbols"])
        for identity, profile_uuid, keychain in (("Apple Development", UUID, self.path), (IDENTITY, "bad-uuid", self.path),
                                                  (IDENTITY, UUID, Path("relative"))):
            with self.subTest(identity=identity, profile_uuid=profile_uuid), self.assertRaises(ValueError):
                signing.ManualSigning(identity, profile_uuid, keychain).validate()

    def test_profile_accepts_each_correct_distribution_mode(self):
        for mode, environment in (("development", PUBLIC), ("store", STORE)):
            config = signing.public_config(mode, environment)
            self.assertEqual(signing.validate_profile(profile(config), config, IDENTITY), UUID)

    def test_profile_rejects_mismatched_expired_or_wrong_distribution_inputs(self):
        for mode, environment in (("development", PUBLIC), ("store", STORE)):
            config = signing.public_config(mode, environment)
            cases = {"team": {"TeamIdentifier": ["Z9Y8X7W6V5"]}, "platform": {"Platform": ["macOS"]},
                     "expired": {"ExpirationDate": datetime(2000, 1, 1)}, "certificate": {"DeveloperCertificates": [b"wrong"]},
                     "enterprise": {"ProvisionsAllDevices": True}, "uuid": {"UUID": "../../escape"},
                     "entitlements": {"Entitlements": {}}, "bad_platform_type": {"Platform": None},
                     "bad_certificate_type": {"DeveloperCertificates": None}, "bad_uuid_type": {"UUID": 123},
                     "wrong_distribution": {"Entitlements": {**profile(config)["Entitlements"], "get-task-allow": config.store}},
                     "wildcard": {"Entitlements": {**profile(config)["Entitlements"], "application-identifier": "A1B2C3D4E5.*"}},
                     "devices": {"ProvisionedDevices": ["synthetic device"] if config.store else []}}
            for name, changes in cases.items():
                with self.subTest(mode=mode, name=name), self.assertRaises(ValueError):
                    signing.validate_profile({**profile(config), **changes}, config, IDENTITY)

    def test_security_password_uses_stdin_and_never_child_argv_or_environment(self):
        result = subprocess.CompletedProcess([], 0, "", "")
        with patch.dict(os.environ, SECRETS, clear=True), patch.object(signing.subprocess, "run", return_value=result) as run:
            signing.security_command(["import", "/synthetic.p12", "-P", SECRETS[signing.SECRET_NAMES[1]]])
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["security", "-q", "-i"])
        self.assertEqual(shlex.split(kwargs["input"])[-1], SECRETS[signing.SECRET_NAMES[1]])
        self.assertEqual(kwargs["env"], {})
        self.assertTrue(kwargs["capture_output"])
        self.assertNotIn("quit", kwargs["input"])

    def test_security_rejects_control_characters_and_oversize_stdin_before_running(self):
        with patch.object(signing, "native") as native:
            for value in ("new\ncommand", "carriage\rreturn", "nul\0byte", "tab\tinput", "x" * 4096):
                with self.subTest(value=value[:12]), self.assertRaises(ValueError):
                    signing.security_command(["import", "-P", value])
            native.assert_not_called()

    def test_native_error_withholds_raw_tool_response(self):
        with patch.object(signing.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "private fixture", "private fixture")):
            with self.assertRaisesRegex(RuntimeError, "output withheld") as error:
                signing.native(["security", "-q", "-i"])
        self.assertNotIn("private fixture", str(error.exception))

    def test_temporary_material_is_private_and_removed_on_success_or_body_failure(self):
        for fail in (False, True):
            commands = []
            with self.subTest(fail=fail), patch.object(Path, "home", return_value=self.home), patch.object(signing, "native", side_effect=self.lifecycle_native(commands)):
                try:
                    with signing.temporary_signing(self.config, IDENTITY, self.state, SECRETS) as manual:
                        directory = manual.keychain.parent
                        self.assertTrue(self.installed.is_file())
                        for path in (self.state, self.installed, directory / "certificate.p12", directory / "profile.mobileprovision"):
                            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                        if fail:
                            raise RuntimeError("synthetic export failure")
                except RuntimeError as error:
                    self.assertTrue(fail)
                    self.assertEqual(str(error), "synthetic export failure")
            self.assertFalse(self.installed.exists())
            self.assertFalse(self.state.exists())
            self.assertFalse(directory.exists())
            self.assertIn(["security", "list-keychains", "-d", "user", "-s", "/synthetic/original.keychain-db"], commands)

    def test_failed_import_cleans_up_without_yielding(self):
        commands = []
        with patch.object(Path, "home", return_value=self.home), patch.object(signing, "native", side_effect=self.lifecycle_native(commands, "import")):
            with self.assertRaisesRegex(RuntimeError, "synthetic import failure"):
                with signing.temporary_signing(self.config, IDENTITY, self.state, SECRETS):
                    self.fail("Failed import must not yield signing access")
        self.assertIn(["import"], commands)
        self.assertFalse(self.installed.exists())
        self.assertFalse(self.state.exists())
        self.assertFalse(list(self.path.glob("gameremote-signing-*")))

    def test_existing_profile_is_preserved_and_never_imports(self):
        self.installed.parent.mkdir(parents=True)
        self.installed.write_bytes(b"existing owner profile")
        commands = []
        with patch.object(Path, "home", return_value=self.home), patch.object(signing, "native", side_effect=self.lifecycle_native(commands)):
            with self.assertRaises(FileExistsError):
                with signing.temporary_signing(self.config, IDENTITY, self.state, SECRETS):
                    self.fail("Profile collision must fail")
        self.assertEqual(self.installed.read_bytes(), b"existing owner profile")
        self.assertNotIn(["import"], commands)
        self.assertFalse(self.state.exists())

    def test_cleanup_failure_retains_retry_state_but_removes_profile_and_p12(self):
        commands = []
        with patch.object(Path, "home", return_value=self.home), patch.object(signing, "native", side_effect=self.lifecycle_native(commands, "delete-keychain")):
            with self.assertRaisesRegex(RuntimeError, "cleanup state retained"):
                with signing.temporary_signing(self.config, IDENTITY, self.state, SECRETS) as manual:
                    directory = manual.keychain.parent
        self.assertTrue(self.state.exists())
        self.assertFalse(self.installed.exists())
        self.assertFalse((directory / "certificate.p12").exists())
        self.assertFalse((directory / "profile.mobileprovision").exists())
        # A later owner may install the same UUID before the independent retry.
        self.installed.write_bytes(b"replacement owner profile")
        commands = []
        with patch.object(Path, "home", return_value=self.home), patch.object(signing, "native", side_effect=self.lifecycle_native(commands)):
            signing.cleanup_signing(self.state)
        self.assertEqual(self.installed.read_bytes(), b"replacement owner profile")
        self.assertNotIn(["security", "list-keychains", "-d", "user", "-s", "/synthetic/original.keychain-db"], commands)
        self.assertFalse(self.state.exists())
        self.assertFalse(directory.exists())

    def test_cleanup_preserves_changed_profile_when_checkpoint_update_fails(self):
        with patch.object(Path, "home", return_value=self.home), patch.object(signing, "native", side_effect=self.lifecycle_native([])):
            with self.assertRaisesRegex(RuntimeError, "cleanup state retained"):
                with signing.temporary_signing(self.config, IDENTITY, self.state, SECRETS):
                    # Same inode, different bytes: ownership must include content.
                    self.installed.write_bytes(b"replacement owner profile")
                    with patch.object(signing, "save_state", side_effect=OSError("synthetic checkpoint failure")):
                        signing.cleanup_signing(self.state)
        # The context's final cleanup retries from the old on-disk checkpoint.
        self.assertEqual(self.installed.read_bytes(), b"replacement owner profile")
        self.assertFalse(self.state.exists())

    def test_missing_invalid_or_oversize_credentials_fail_before_native_commands(self):
        cases = [{}, {**SECRETS, signing.SECRET_NAMES[0]: "not base64"},
                 {**SECRETS, signing.SECRET_NAMES[2]: base64.b64encode(b"x" * (1024 * 1024 + 1)).decode()}]
        with patch.object(signing, "native") as native:
            for environment in cases:
                with self.assertRaises(ValueError):
                    with signing.temporary_signing(self.config, IDENTITY, self.state, environment):
                        self.fail("Invalid inputs must not yield")
            native.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_cleanup_rejects_outside_paths_before_native_or_delete(self):
        sentinel = self.path / "owner-file"
        sentinel.write_bytes(b"preserve")
        self.state.write_text(json.dumps({"directory": str(self.path), "search_list": []}))
        with patch.object(signing, "native") as native, self.assertRaises(ValueError):
            signing.cleanup_signing(self.state)
        native.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b"preserve")

    def test_atomic_state_update_failure_preserves_original_and_removes_new_profile(self):
        commands = []
        replace = os.replace
        attempts = []

        def fail_once(*args):
            attempts.append(args)
            if len(attempts) == 1:
                raise OSError("synthetic state replacement failure")
            return replace(*args)

        with (patch.object(Path, "home", return_value=self.home),
              patch.object(signing, "native", side_effect=self.lifecycle_native(commands)),
              patch.object(signing.os, "replace", side_effect=fail_once)):
            with self.assertRaisesRegex(OSError, "state replacement"):
                with signing.temporary_signing(self.config, IDENTITY, self.state, SECRETS):
                    self.fail("Failed state update must not yield")
        self.assertFalse(self.installed.exists())
        self.assertFalse(self.state.exists())
        self.assertFalse(self.state.with_name(self.state.name + ".update").exists())
        self.assertFalse(list(self.path.glob("gameremote-signing-*")))
        self.assertNotIn(["import"], commands)

    def test_cleanup_rejects_profile_uuid_traversal(self):
        directory = self.path / "gameremote-signing-fixture"
        directory.mkdir()
        self.state.write_text(json.dumps({"directory": str(directory), "search_list": [],
                                         "profile_uuid": "../../owner", "installed_profile": str(self.path / "owner")}))
        with patch.object(signing, "native") as native, self.assertRaisesRegex(ValueError, "UUID"):
            signing.cleanup_signing(self.state)
        native.assert_not_called()

    def test_profile_rejects_malformed_top_level_without_import(self):
        for value in ([], "invalid", {"Entitlements": []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                signing.validate_profile(value, self.config, IDENTITY)

    def test_real_ipa_roundtrip_validates_both_modes_with_mocked_apple_tools(self):
        for mode, environment in (("development", PUBLIC), ("store", STORE)):
            config = signing.public_config(mode, environment)
            with self.subTest(mode=mode), patch.object(signing, "native", side_effect=self.native_app(config)):
                signing.verify_ipa(self.ipa(self.app(config)), config, self.manual)

    def test_ipa_rejects_traversal_symlink_duplicate_and_extra_app(self):
        for name, mode in (("../escape", 0o100644), ("/absolute", 0o100644), ("Payload/link", 0o120777),
                           ("Payload/Other.app/Info.plist", 0o100644), ("Payload/GameRemote.app/./Info.plist", 0o100644)):
            ipa = self.ipa(self.app())
            with zipfile.ZipFile(ipa, "a") as archive:
                info = zipfile.ZipInfo(name)
                info.external_attr = mode << 16
                archive.writestr(info, b"synthetic")
            with self.subTest(name=name), patch.object(signing, "native") as native, self.assertRaises(ValueError):
                signing.verify_ipa(ipa, self.config, self.manual)
            native.assert_not_called()

    def test_ipa_rejects_case_unicode_and_implicit_parent_aliases_before_extraction(self):
        for aliases in (("Payload/GameRemote.app/Info.plist", "Payload/GameRemote.app/info.plist"),
                        ("Payload/GameRemote.app/Caf\u00e9/data", "Payload/GameRemote.app/Cafe\u0301/other"),
                        ("Payload/GameRemote.app/Assets/data", "payload/GameRemote.app/Assets/other")):
            ipa = self.path / "aliases.ipa"
            with zipfile.ZipFile(ipa, "w") as archive:
                for index, name in enumerate(aliases):
                    archive.writestr(name, plistlib.dumps({"CFBundleVersion": "1" if index == 0 else "27.3.1"}))
            with (self.subTest(aliases=aliases), patch.object(signing, "native") as native,
                  patch.object(zipfile.ZipFile, "extractall") as extract):
                with self.assertRaisesRegex(ValueError, "aliases"):
                    signing.verify_ipa(ipa, self.config, self.manual)
                native.assert_not_called()
                extract.assert_not_called()

    def test_missing_resource_and_wrong_metadata_reject_before_codesign(self):
        app = self.app()
        (app / "ThirdPartyNotices.txt").unlink()
        with patch.object(signing, "native") as native, self.assertRaisesRegex(ValueError, "resource"):
            signing.verify_signed_app(app, self.config, self.manual)
        native.assert_not_called()
        self.app()
        info = plistlib.loads((app / "Info.plist").read_bytes())
        info["CFBundleVersion"] = "1"
        (app / "Info.plist").write_bytes(plistlib.dumps(info))
        with patch.object(signing, "native") as native, self.assertRaises(ValueError):
            signing.verify_signed_app(app, self.config, self.manual)
        native.assert_not_called()

    def test_ipa_rejects_signature_team_entitlements_profile_architecture_and_certificate(self):
        ipa = self.ipa(self.app())
        wrong_profile = {**profile(self.config), "UUID": "87654321-1234-4321-8765-123456789ABC"}
        cases = [{"signature_failure": True}, {"team": "Z9Y8X7W6V5"},
                 {"entitlements": {**profile(self.config)["Entitlements"], "application-identifier": "wrong"}},
                 {"entitlements": {**profile(self.config)["Entitlements"], "com.apple.developer.team-identifier": "Z9Y8X7W6V5"}},
                 {"entitlements": {**profile(self.config)["Entitlements"], "get-task-allow": False}},
                 {"profile": wrong_profile}, {"architecture": "arm64 x86_64"}, {"platform": "IOSSIMULATOR"},
                 {"certificate": b"another certificate"}]
        for overrides in cases:
            with self.subTest(case=list(overrides)), patch.object(signing, "native", side_effect=self.native_app(overrides=overrides)):
                with self.assertRaises((ValueError, RuntimeError)):
                    signing.verify_ipa(ipa, self.config, self.manual)

    def test_default_entrypoint_validates_only_public_inputs(self):
        with (patch.dict(os.environ, PUBLIC, clear=True), patch.object(sys, "argv", ["sign-and-export.py"]),
              patch.object(exporter, "native") as native, patch.object(exporter, "temporary_signing") as temporary,
              patch("sys.stdout", new_callable=io.StringIO) as stdout):
            self.assertEqual(exporter.main(), 0)
        native.assert_not_called()
        temporary.assert_not_called()
        self.assertIn("no credentials read", stdout.getvalue())

    def test_default_entrypoint_reports_missing_public_fields_without_native_calls(self):
        with (patch.dict(os.environ, PUBLIC, clear=True), patch.object(sys, "argv", ["sign-and-export.py", "--mode", "store"]),
              patch.object(exporter, "native") as native, patch.object(exporter, "temporary_signing") as temporary,
              patch("sys.stderr", new_callable=io.StringIO) as stderr):
            self.assertEqual(exporter.main(), 2)
        native.assert_not_called()
        temporary.assert_not_called()
        self.assertIn("GR_IOS_PRIVACY_URL is required", stderr.getvalue())

    def test_pinned_toolchain_rejects_other_xcode_sdk_or_missing_manual_export_options(self):
        outputs = ["Xcode 26.3\nBuild version fixture", "26.2", "app-store-connect debugging provisioningProfiles signingCertificate"]
        for index, bad in ((0, "Xcode 26.2"), (0, ""), (1, "26.1"), (2, "old help")):
            trial = list(outputs)
            trial[index] = bad
            with patch.object(exporter, "native", side_effect=[subprocess.CompletedProcess([], 0, value, "") for value in trial]):
                with self.assertRaises(ValueError):
                    exporter.pinned_toolchain()
        with patch.object(exporter, "native", side_effect=[subprocess.CompletedProcess([], 0, value, "") for value in outputs]):
            exporter.pinned_toolchain()

    def test_export_releases_deliverables_only_after_validation_and_cleanup(self):
        for failure in (None, "verification", "cleanup", "export"):
            output = self.path / (failure or "success")
            events = []

            @contextmanager
            def temporary(*args):
                events.append("setup")
                try:
                    yield self.manual
                finally:
                    events.append("cleanup")
                    if failure == "cleanup":
                        raise RuntimeError("synthetic cleanup failure")

            def run_phase(command, log, **kwargs):
                self.assertEqual(set(kwargs["environment"]) & set(signing.SECRET_NAMES), set())
                if "--execute-signing" in command:
                    self.assertIn(str(ROOT / "ios/scripts/store-archive.py"), command)
                    self.assertEqual(kwargs["limit"], 1800)
                    output.mkdir()
                    return
                self.assertIn("-exportArchive", command)
                self.assertNotIn("-allowProvisioningUpdates", command)
                self.assertEqual(kwargs["limit"], 600)
                options = plistlib.loads((output / "ExportOptions.plist").read_bytes())
                self.assertEqual(options["destination"], "export")
                if failure == "export":
                    raise subprocess.CalledProcessError(1, command)
                destination = Path(command[command.index("-exportPath") + 1])
                destination.mkdir()
                (destination / "GameRemote.ipa").write_bytes(b"synthetic validated IPA")

            def verify(*args):
                events.append("verify")
                self.assertFalse((output / "deliverables").exists())
                if failure == "verification":
                    raise ValueError("synthetic validation failure")

            with (self.subTest(failure=failure), patch.dict(os.environ, {**PUBLIC, **SECRETS}, clear=True),
                  patch.object(exporter, "pinned_toolchain"), patch.object(exporter, "temporary_signing", temporary),
                  patch.object(exporter, "verify_signed_app"), patch.object(exporter, "bounded_phase", run_phase),
                  patch.object(exporter, "verify_ipa", verify),
                  patch.object(exporter, "native", return_value=subprocess.CompletedProcess([], 0, "fixturecommit", ""))):
                if failure:
                    with self.assertRaises((ValueError, RuntimeError, subprocess.CalledProcessError)):
                        exporter.sign_and_export(output, "development", IDENTITY, self.state)
                    self.assertFalse((output / "deliverables").exists())
                else:
                    ipa = exporter.sign_and_export(output, "development", IDENTITY, self.state)
                    self.assertEqual(events, ["setup", "verify", "cleanup"])
                    self.assertEqual({path.name for path in ipa.parent.iterdir()}, {"GameRemote.ipa", "verification.json"})
                    report = json.loads((ipa.parent / "verification.json").read_text())
                    self.assertFalse(report["uploaded_to_apple"])
                    self.assertEqual(report["sha256"], hashlib.sha256(ipa.read_bytes()).hexdigest())
                self.assertIn("cleanup", events)

    def test_real_cmake_properties_scope_signing_to_app_and_default_to_unsigned(self):
        cmake = shutil.which("cmake")
        self.assertIsNotNone(cmake, "CMake is required for the signing target-scope regression")
        source = self.path / "cmake-fixture"
        source.mkdir()
        (source / "dummy.c").write_text("int main(void) { return 0; }\n")
        integration = (ROOT / "ios/CMakeLists.txt").read_text()
        self.assertIn('include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/ManualSigning.cmake")', integration)
        self.assertIn("gameremote_configure_manual_signing(GameRemoteIOS)", integration)
        (source / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.28)\nproject(SigningScope C)\n"
            "set(CMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO)\n"
            "add_executable(GameRemoteIOS dummy.c)\nadd_library(GameRemoteBridge STATIC dummy.c)\n"
            "add_library(mbedcrypto STATIC dummy.c)\n"
            'set_target_properties(GameRemoteIOS PROPERTIES XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic")\n'
            f'include("{ROOT / "ios/cmake/ManualSigning.cmake"}")\n'
            "gameremote_configure_manual_signing(GameRemoteIOS)\n"
            'file(WRITE "${CMAKE_BINARY_DIR}/properties.txt" "global=${CMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED}\\n")\n'
            "foreach(target GameRemoteIOS GameRemoteBridge mbedcrypto)\n"
            "foreach(key CODE_SIGNING_ALLOWED CODE_SIGNING_REQUIRED CODE_SIGN_STYLE CODE_SIGN_IDENTITY PROVISIONING_PROFILE_SPECIFIER OTHER_CODE_SIGN_FLAGS GR_IOS_ARCHIVE_SIGNING)\n"
            "get_target_property(value ${target} XCODE_ATTRIBUTE_${key})\n"
            'file(APPEND "${CMAKE_BINARY_DIR}/properties.txt" "${target}.${key}=${value}\\n")\n'
            "endforeach()\nendforeach()\n"
        )
        for enabled in (False, True):
            build = source / ("manual" if enabled else "unsigned")
            args = self.manual.cmake_arguments() if enabled else ["-DCHIAKI_IOS_MANUAL_SIGNING=OFF"]
            result = subprocess.run([cmake, "-S", str(source), "-B", str(build), "-G", "Unix Makefiles", *args],
                                    capture_output=True, text=True, check=False, env={"PATH": os.defpath})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            properties = dict(line.split("=", 1) for line in (build / "properties.txt").read_text().splitlines())
            print("Generated CMake signing scope (manual=" + str(enabled) + "): " + json.dumps(properties, sort_keys=True), flush=True)
            self.assertEqual(properties["global"], "NO")
            for target in ("GameRemoteBridge", "mbedcrypto"):
                for key in ("CODE_SIGNING_ALLOWED", "CODE_SIGN_IDENTITY", "PROVISIONING_PROFILE_SPECIFIER", "GR_IOS_ARCHIVE_SIGNING"):
                    self.assertEqual(properties[target + "." + key], "value-NOTFOUND")
            if enabled:
                self.assertEqual(properties["GameRemoteIOS.CODE_SIGNING_ALLOWED"], "$(GR_IOS_ARCHIVE_SIGNING)")
                self.assertEqual(properties["GameRemoteIOS.CODE_SIGNING_REQUIRED"], "$(GR_IOS_ARCHIVE_SIGNING)")
                self.assertEqual(properties["GameRemoteIOS.GR_IOS_ARCHIVE_SIGNING"], "NO")
                self.assertEqual(properties["GameRemoteIOS.CODE_SIGN_STYLE"], "Manual")
                self.assertEqual(properties["GameRemoteIOS.PROVISIONING_PROFILE_SPECIFIER"], UUID)
                self.assertEqual(properties["GameRemoteIOS.CODE_SIGN_IDENTITY"], IDENTITY)
            else:
                self.assertEqual(properties["GameRemoteIOS.CODE_SIGN_STYLE"], "Automatic")
                self.assertEqual(properties["GameRemoteIOS.CODE_SIGNING_ALLOWED"], "value-NOTFOUND")

    def ignoring_child(self):
        child = self.path / "ignore-term.py"
        child.write_text("import os, signal, sys, time\nfrom pathlib import Path\n"
                         "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                         "Path(sys.argv[1]).write_text(str(os.getpid()))\n"
                         "while True: time.sleep(0.05)\n")
        return child, self.path / "child.pid"

    def rescue_fixture_child(self, pid_file):
        if pid_file.exists():
            try:
                os.killpg(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass

    def test_real_phase_deadline_reaps_term_ignoring_child(self):
        child, pid_file = self.ignoring_child()
        try:
            with self.assertRaises(subprocess.CalledProcessError) as error:
                exporter.bounded_phase([sys.executable, str(child), str(pid_file)], self.path / "phase.log",
                                       stall=10, limit=0.5, environment={"PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(error.exception.returncode, 124)
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid_file.read_text()), 0)
        finally:
            self.rescue_fixture_child(pid_file)

    def cancel_parent(self, *, group_interrupt):
        child, pid_file = self.ignoring_child()
        cleanup = self.path / "cleanup-complete"
        parent = self.path / "parent.py"
        parent.write_text(
            "import importlib.util, os, signal, sys\nfrom pathlib import Path\n"
            f"sys.path.insert(0, {str(ROOT / 'ios/scripts')!r})\n"
            f"spec = importlib.util.spec_from_file_location('phase', {str(ROOT / 'ios/scripts/sign-and-export.py')!r})\n"
            "module = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\n"
            "def stop(signum, frame): raise InterruptedError('synthetic cancellation')\n"
            "signal.signal(signal.SIGTERM, stop)\n"
            "signal.signal(signal.SIGINT, stop)\n"
            "try:\n"
            f" module.bounded_phase([sys.executable, {str(child)!r}, {str(pid_file)!r}], Path({str(self.path / 'parent-phase.log')!r}), stall=10, limit=20, environment={{'PYTHONDONTWRITEBYTECODE': '1'}})\n"
            "except InterruptedError: pass\n"
            "finally:\n"
            f" try: os.kill(int(Path({str(pid_file)!r}).read_text()), 0); status = 'child-alive'\n"
            " except ProcessLookupError: status = 'child-reaped'\n"
            f" Path({str(cleanup)!r}).write_text(status)\n"
        )
        process = subprocess.Popen([sys.executable, str(parent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env={"PYTHONDONTWRITEBYTECODE": "1"}, start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(pid_file.exists(), "Synthetic child did not start")
            if group_interrupt:
                os.killpg(process.pid, signal.SIGINT)
            else:
                process.terminate()
            self.assertEqual(process.wait(timeout=5), 0)
            self.assertEqual(cleanup.read_text(), "child-reaped")
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid_file.read_text()), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            self.rescue_fixture_child(pid_file)

    def test_parent_cancellation_reaps_phase_before_cleanup(self):
        self.cancel_parent(group_interrupt=False)

    def test_group_sigint_reaps_phase_before_cleanup(self):
        self.cancel_parent(group_interrupt=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
