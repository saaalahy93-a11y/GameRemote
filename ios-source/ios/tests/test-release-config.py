#!/usr/bin/env python3
"""Real metadata/preflight/CMake tests plus a mocked native archive command contract.

No test invokes Xcode, signing, a network request, or an Apple account.
"""

import importlib.util
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "ios/scripts"
sys.path.insert(0, str(SCRIPTS))
# These local scripts are not an installed package; resolve them after path setup.
from release_config import FIELDS, URL_PLIST_KEYS, ReleaseConfig  # noqa: E402
from apple_signing import ManualSigning, SECRET_NAMES  # noqa: E402

spec = importlib.util.spec_from_file_location("store_archive", SCRIPTS / "store-archive.py")
store_archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store_archive)

# Test fixtures only. They do not assert ownership of these identities or endpoints
# and are never defaults, production configuration, or a publishable release plan.
VALID = {
    "BUNDLE_IDENTIFIER": "com.validation.GameRemote",
    "DEVELOPMENT_TEAM": "A1B2C3D4E5",
    "VERSION": "2.3.4",
    "BUILD_NUMBER": "27.3.1",
    "PRIVACY_URL": "https://www.apple.com/legal/privacy/?lang=en&view=full",
    "SUPPORT_URL": "https://support.apple.com/",
    "SOURCE_URL": "https://github.com/",
    "EXPORT_CLASSIFICATION": "non-exempt",
}


class ReleaseConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="gameremote-release-tests-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.archive_root = self.path / "archive-source"
        curl = self.archive_root / "third-party/curl/CMakeLists.txt"
        curl.parent.mkdir(parents=True)
        curl.write_text("# Synthetic archive command fixture; never built.\n")
        self.signing = ManualSigning("A" * 40, "12345678-1234-4321-8765-123456789ABC", self.path / "fixture.keychain-db")
        self.environment = {key: value for key, value in os.environ.items() if not key.startswith("GR_IOS_")}
        self.environment["CHIAKI_HOST_PYTHON"] = sys.executable
        self.environment["CHIAKI_HOST_PROTOC"] = str(self.path / "fixture-protoc")
        self.environment["CMAKE_BUILD_PARALLEL_LEVEL"] = "2"
        self.environment["PYTHONDONTWRITEBYTECODE"] = "1"

    def configured_environment(self, values=VALID):
        return {**self.environment, **{"GR_IOS_" + key: value for key, value in values.items()}}

    def preflight(self, values):
        return subprocess.run(
            [str(SCRIPTS / "preflight.sh"), "--store-config"],
            env=self.configured_environment(values), capture_output=True, text=True, check=False,
        )

    def render(self, config):
        return subprocess.run(
            ["cmake", *config.cmake_arguments(), "-P", str(ROOT / "ios/cmake/ReleaseConfig.cmake")],
            cwd=self.path, env=self.environment, capture_output=True, text=True, check=False,
        )

    def test_development_defaults_render_without_owner_inputs(self):
        config = ReleaseConfig.from_environment(environment={})
        config.validate()
        result = self.render(config)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plist = self.path / "GameRemote-Info.plist"
        config.verify_plist(plist)
        info = plistlib.loads(plist.read_bytes())
        self.assertEqual(info["CFBundleIdentifier"], "org.example.RemotePlayPrototype.iOS")
        self.assertEqual(info["CFBundleShortVersionString"], "1.10.0")
        self.assertEqual(info["CFBundleVersion"], "2")
        self.assertNotIn("ITSAppUsesNonExemptEncryption", info)
        self.assertTrue(all(info[key] == "" for key in URL_PLIST_KEYS.values()))

    def test_real_bundle_packages_app_and_dependency_manifests_separately(self):
        fixture = self.path / "privacy-fixture"
        fixture.mkdir()
        (fixture / "dummy.c").write_text("int main(void) { return 0; }\n")
        app_manifest = ROOT / "ios/App/PrivacyInfo.xcprivacy"
        sdk_manifests = {
            "nanopb_Privacy.bundle": ROOT / "third-party/nanopb/spm_resources/PrivacyInfo.xcprivacy",
            "curl_Privacy.bundle": ROOT / "ios/Dependencies/curl/PrivacyInfo.xcprivacy",
        }
        integration = (ROOT / "ios/CMakeLists.txt").read_text()
        self.assertIn('include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/NanopbPrivacy.cmake")', integration)
        self.assertIn("gameremote_add_nanopb_privacy(GameRemoteIOS)", integration)
        self.assertIn('include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/CurlPrivacy.cmake")', integration)
        self.assertIn("gameremote_add_curl_privacy(GameRemoteIOS)", integration)
        (fixture / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.28)\nproject(PrivacyProbe C)\n"
            f'add_executable(PrivacyProbe MACOSX_BUNDLE dummy.c "{app_manifest}")\n'
            f'set_source_files_properties("{app_manifest}" PROPERTIES MACOSX_PACKAGE_LOCATION Resources)\n'
            f'include("{ROOT / "ios/cmake/NanopbPrivacy.cmake"}")\n'
            "gameremote_add_nanopb_privacy(PrivacyProbe)\n"
            f'include("{ROOT / "ios/cmake/CurlPrivacy.cmake"}")\n'
            "gameremote_add_curl_privacy(PrivacyProbe)\n"
        )
        build = fixture / "build"
        # Build only a tiny host C fixture; no iOS SDK, app, credentials or network.
        for command in (["cmake", "-S", str(fixture), "-B", str(build), "-G", "Unix Makefiles"],
                        ["cmake", "--build", str(build), "--parallel", "2"]):
            result = subprocess.run(command, env=self.environment, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        resources = build / "PrivacyProbe.app/Contents/Resources"
        for bundle_name, sdk_manifest in sdk_manifests.items():
            sdk_bundle = resources / bundle_name
            self.assertEqual((sdk_bundle / "PrivacyInfo.xcprivacy").read_bytes(), sdk_manifest.read_bytes())
            info = plistlib.loads((sdk_bundle / "Info.plist").read_bytes())
            self.assertEqual(info["CFBundlePackageType"], "BNDL")
            self.assertNotIn("CFBundleExecutable", info)
        self.assertEqual((resources / "PrivacyInfo.xcprivacy").read_bytes(), app_manifest.read_bytes())
        self.assertEqual(sorted(str(p.relative_to(resources)) for p in resources.rglob("*.xcprivacy")),
                         ["PrivacyInfo.xcprivacy", "curl_Privacy.bundle/PrivacyInfo.xcprivacy",
                          "nanopb_Privacy.bundle/PrivacyInfo.xcprivacy"])
        curl_privacy = plistlib.loads((resources / "curl_Privacy.bundle/PrivacyInfo.xcprivacy").read_bytes())
        self.assertEqual(curl_privacy, {
            "NSPrivacyTracking": False,
            "NSPrivacyTrackingDomains": [],
            "NSPrivacyCollectedDataTypes": [],
            "NSPrivacyAccessedAPITypes": [{
                "NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryFileTimestamp",
                "NSPrivacyAccessedAPITypeReasons": ["C617.1"],
            }],
        })

    def test_real_preflight_accepts_complete_syntax_without_xcode(self):
        result = self.preflight(VALID)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ownership, URL availability, export assessment and signing are not verified", result.stdout)

    def test_real_preflight_rejects_each_missing_owner_input(self):
        for field in FIELDS:
            with self.subTest(field=field):
                values = {key: value for key, value in VALID.items() if key != field}
                result = self.preflight(values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("GR_IOS_" + field + " is required", result.stderr)

    def test_cmake_renders_explicit_values_and_both_export_classifications(self):
        for classification in ("exempt", "non-exempt"):
            with self.subTest(classification=classification):
                config = ReleaseConfig({**VALID, "EXPORT_CLASSIFICATION": classification}, store=True)
                result = self.render(config)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                plist = self.path / "GameRemote-Info.plist"
                config.verify_plist(plist)
                text = plist.read_text()
                self.assertIn("&amp;view=full", text)
                self.assertNotIn("@CHIAKI_IOS_", text)
                self.assertNotIn("@GR_IOS_", text)

    def test_cmake_rejects_incomplete_release_before_creating_plist(self):
        config = ReleaseConfig.from_environment(store=True, environment={})
        result = self.render(config)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GR_IOS_PRIVACY_URL is required", result.stderr)
        self.assertFalse((self.path / "GameRemote-Info.plist").exists())

    def test_cmake_rejects_metadata_that_injects_validator_options(self):
        for field in URL_PLIST_KEYS:
            option = field.lower().replace("_", "-")
            value = "https://example.com/privacy;--" + option + "=https://www.apple.com/privacy"
            with self.subTest(field=field):
                result = self.render(ReleaseConfig({**VALID, field: value}, store=True))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(field + " must not contain a semicolon", result.stderr)
                self.assertFalse((self.path / "GameRemote-Info.plist").exists())

    def test_real_bundle_preserves_urls_through_both_cmake_substitutions(self):
        fixture = self.path / "bundle-fixture"
        fixture.mkdir()
        (fixture / "dummy.c").write_text("int main(void) { return 0; }\n")
        (fixture / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.28)\n"
            "project(PlistProbe LANGUAGES C)\n"
            f'include("{ROOT / "ios/cmake/ReleaseConfig.cmake"}")\n'
            "add_executable(PlistProbe MACOSX_BUNDLE dummy.c)\n"
            'set_target_properties(PlistProbe PROPERTIES MACOSX_BUNDLE_INFO_PLIST "${GR_IOS_INFO_PLIST}")\n'
        )
        urls = {field: "https://unpkg.com/@types/node@22.0.0/LICENSE?one=1&two=2" for field in URL_PLIST_KEYS}
        config = ReleaseConfig({**VALID, **urls}, store=True)
        build = fixture / "build"
        # Configure creates a real Apple bundle Info.plist without compiling,
        # signing or connecting to any URL. The host lane runs on macOS.
        result = subprocess.run(
            ["cmake", "-S", str(fixture), "-B", str(build), "-G", "Unix Makefiles", *config.cmake_arguments()],
            env=self.environment, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with (build / "PlistProbe.app/Contents/Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        for field, key in URL_PLIST_KEYS.items():
            self.assertEqual(info[key], urls[field])

    def test_invalid_identifiers_versions_and_final_classification(self):
        bad = {
            "BUNDLE_IDENTIFIER": ["org.example.RemotePlayPrototype.iOS", "com.example.GameRemote", "GameRemote", "com.company.*", "com.company.app name", "com.-company.app", "com.company.-"],
            "DEVELOPMENT_TEAM": ["none", "aaaaaaaaaa", "ABCDEFGHIJ", "AAAAAAAAAA", "1234567890"],
            "VERSION": ["1.0", "1.0.0-beta", "1.0.0.1", "01.0.0", "1.2.-1"],
            "BUILD_NUMBER": ["0", "10000", "1.100", "1.1.100", "1.0.0.0", "1beta", "01"],
            "EXPORT_CLASSIFICATION": ["unknown", "pending", "YES", "no", "https-only"],
        }
        for field, values in bad.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    ReleaseConfig({**VALID, field: value}, store=True).validate()

    def test_public_urls_reject_placeholder_local_and_unsafe_values(self):
        values = [
            "http://www.apple.com/privacy", "https://example.com/privacy", "https://privacy.example.org/",
            "https://yourdomain.com/", "https://localhost/", "https://console.local/",
            "https://policy.invalid/", "https://policy.test/", "https://192.168.1.1/privacy",
            "https://127.0.0.1/", "https://[::1]/", "https:///privacy", "privacy.html",
            "https://user:password@www.apple.com/", "https://www.apple.com/a b", "https://www.apple.com/\n",
            "https://www.apple.com:invalid/", "https://www.apple.com:99999/", "https://www.apple.com/%ZZ",
            "https://www.apple.com/$(CONFIGURATION)", "https://www.apple.com/<pending>",
        ]
        for field in URL_PLIST_KEYS:
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, field):
                    ReleaseConfig({**VALID, field: value}, store=True).validate()

    def test_nonempty_development_urls_are_also_validated(self):
        config = ReleaseConfig.from_environment(environment={"GR_IOS_PRIVACY_URL": "https://example.com/"})
        with self.assertRaisesRegex(ValueError, "PRIVACY_URL"):
            config.validate()

    def test_https_scheme_is_case_insensitive(self):
        ReleaseConfig({**VALID, "PRIVACY_URL": "HTTPS://www.apple.com/privacy"}, store=True).validate()

    def make_mock_archive(self, archive, wrong_version=False):
        app = archive / "Products/Applications/GameRemote.app"
        app.mkdir(parents=True)
        info = {
            "CFBundleIdentifier": VALID["BUNDLE_IDENTIFIER"],
            "CFBundleShortVersionString": "0.0.0" if wrong_version else VALID["VERSION"],
            "CFBundleVersion": VALID["BUILD_NUMBER"],
            **{key: VALID[field] for field, key in URL_PLIST_KEYS.items()},
            "ITSAppUsesNonExemptEncryption": True,
        }
        (app / "Info.plist").write_bytes(plistlib.dumps(info))
        for name in ("GameRemote", "Assets.car", "PrivacyInfo.xcprivacy", "AGPL-3.0-only-OpenSSL.txt", "ThirdPartyNotices.txt", "embedded.mobileprovision"):
            (app / name).write_bytes(b"fixture only")
        (app / "GameRemote").chmod(0o755)

    def archive_runner(self, commands, wrong_version=False, wrong_team=False):
        def run(command, **kwargs):
            commands.append(command)
            if command[0] == "xcodebuild":
                self.make_mock_archive(Path(command[command.index("-archivePath") + 1]), wrong_version=wrong_version)
            team = "Z9Y8X7W6V5" if wrong_team else VALID["DEVELOPMENT_TEAM"]
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="TeamIdentifier=" + team + "\n")
        return run

    def test_mocked_archive_keeps_probes_unsigned_and_explicitly_enables_archive_signing(self):
        commands = []
        with patch.dict(os.environ, self.configured_environment(), clear=True), patch.object(store_archive.subprocess, "run", side_effect=self.archive_runner(commands)):
            archive = store_archive.create_archive(self.path / "fresh", self.archive_root, self.signing)
        self.assertTrue(archive.is_dir())
        configure = next(command for command in commands if command[0] == "cmake")
        self.assertIn("-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO", configure)
        self.assertIn("-DCHIAKI_IOS_STORE_RELEASE=ON", configure)
        for field in FIELDS:
            self.assertIn("-DCHIAKI_IOS_" + field + "=" + VALID[field], configure)
        archive_command = next(command for command in commands if command[0] == "xcodebuild")
        self.assertIn("GR_IOS_ARCHIVE_SIGNING=YES", archive_command)
        for argument in self.signing.cmake_arguments():
            self.assertIn(argument, configure)
        for prefix in ("CODE_SIGN", "PROVISIONING_PROFILE", "OTHER_CODE_SIGN_FLAGS", "DEVELOPMENT_TEAM"):
            self.assertFalse(any(argument.startswith(prefix) for argument in archive_command))
        self.assertIn("generic/platform=iOS", archive_command)
        self.assertNotIn("CODE_SIGNING_ALLOWED=NO", archive_command)
        self.assertFalse(any("-exportArchive" in command or "-allowProvisioningUpdates" in command for command in commands))
        self.assertTrue(any(command[:3] == ["codesign", "--verify", "--strict"] for command in commands))

    def test_development_manual_archive_needs_no_store_urls_and_strips_secret_environment(self):
        values = {field: VALID[field] for field in ("BUNDLE_IDENTIFIER", "DEVELOPMENT_TEAM", "VERSION", "BUILD_NUMBER")}
        commands = []
        runner = self.archive_runner(commands)

        def run(command, **kwargs):
            self.assertFalse(set(kwargs["env"]) & set(SECRET_NAMES))
            result = runner(command, **kwargs)
            if command[0] == "xcodebuild":
                info_path = Path(command[command.index("-archivePath") + 1]) / "Products/Applications/GameRemote.app/Info.plist"
                info = plistlib.loads(info_path.read_bytes())
                for key in URL_PLIST_KEYS.values():
                    info[key] = ""
                info.pop("ITSAppUsesNonExemptEncryption")
                info_path.write_bytes(plistlib.dumps(info))
            return result

        environment = {**self.configured_environment(values), **{name: "synthetic secret" for name in SECRET_NAMES}}
        with patch.dict(os.environ, environment, clear=True), patch.object(store_archive.subprocess, "run", side_effect=run):
            store_archive.create_archive(self.path / "development", self.archive_root, self.signing, "development")
        configure = next(command for command in commands if command[0] == "cmake")
        self.assertIn("-DCHIAKI_IOS_STORE_RELEASE=OFF", configure)

    def test_archive_rejects_implicit_signing_and_unbounded_jobs_before_commands(self):
        environment = self.configured_environment()
        with patch.dict(os.environ, environment, clear=True), patch.object(store_archive.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "Explicit manual signing"):
                store_archive.create_archive(self.path / "fresh", self.archive_root)
            os.environ["CMAKE_BUILD_PARALLEL_LEVEL"] = "8"
            with self.assertRaisesRegex(ValueError, "parallelism"):
                store_archive.create_archive(self.path / "fresh", self.archive_root, self.signing)
            run.assert_not_called()

    def test_archive_rejects_missing_input_before_any_command_or_output(self):
        output = self.path / "fresh"
        with patch.dict(os.environ, self.environment, clear=True), patch.object(store_archive.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "GR_IOS_BUNDLE_IDENTIFIER is required"):
                store_archive.create_archive(output, self.archive_root, self.signing)
            run.assert_not_called()
        self.assertFalse(output.exists())

    def test_archive_refuses_reuse_and_relative_output_before_any_command(self):
        for output in (self.path, Path("relative-output")):
            with self.subTest(output=output), patch.dict(os.environ, self.configured_environment(), clear=True), patch.object(store_archive.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    store_archive.create_archive(output, self.archive_root, self.signing)
                run.assert_not_called()

    def test_archive_rejects_wrong_result_metadata_and_team(self):
        for failure in ("version", "team"):
            with (
                self.subTest(failure=failure),
                patch.dict(os.environ, self.configured_environment(), clear=True),
                patch.object(store_archive.subprocess, "run", side_effect=self.archive_runner([], wrong_version=failure == "version", wrong_team=failure == "team")),
                self.assertRaises(ValueError),
            ):
                store_archive.create_archive(self.path / failure, self.archive_root, self.signing)

    def test_archive_propagates_a_failed_build_without_attempting_signing(self):
        commands = []

        def fail_configure(command, **kwargs):
            commands.append(command)
            if command[0] == "cmake":
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with (
            patch.dict(os.environ, self.configured_environment(), clear=True),
            patch.object(store_archive.subprocess, "run", side_effect=fail_configure),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            store_archive.create_archive(self.path / "failed", self.archive_root, self.signing)
        self.assertFalse(any(command[0] in {"xcodebuild", "codesign"} for command in commands))

    def test_archive_rejects_signature_verification_failure(self):
        commands = []
        complete = self.archive_runner(commands)

        def fail_signature(command, **kwargs):
            if command[:2] == ["codesign", "--verify"]:
                commands.append(command)
                raise subprocess.CalledProcessError(1, command)
            return complete(command, **kwargs)

        with (
            patch.dict(os.environ, self.configured_environment(), clear=True),
            patch.object(store_archive.subprocess, "run", side_effect=fail_signature),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            store_archive.create_archive(self.path / "unsigned", self.archive_root, self.signing)
        self.assertFalse(any(command[:2] == ["codesign", "--display"] for command in commands))


if __name__ == "__main__":
    unittest.main(verbosity=2)
