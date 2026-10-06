"""Prove unsafe release requests stop before profile access or signing."""
import hashlib
import importlib.util
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("repackage_verified_device", SCRIPTS / "repackage-verified-device.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SigningBoundaryTests(unittest.TestCase):
    def test_bad_archive_never_reads_profile_or_signs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "wrong.tar.gz"
            archive.write_bytes(b"not the approved native artifact")
            args = SimpleNamespace(archive=archive, profile=root / "must-not-read.profile",
                                   output=root / "must-not-create", execute_signing=True)
            config = SimpleNamespace(values={"DEVELOPMENT_TEAM": MODULE.TEAM,
                "BUNDLE_IDENTIFIER": MODULE.BUNDLE, "VERSION": "1.10.0", "BUILD_NUMBER": "4",
                "EXPORT_CLASSIFICATION": "defer-to-app-store-connect"})
            with patch.object(MODULE, "public_config", return_value=config), \
                    patch.object(MODULE, "decode_profile") as profile, patch.object(MODULE, "run") as sign:
                with self.assertRaisesRegex(ValueError, "Verified input archive"):
                    MODULE.package(args)
                profile.assert_not_called()
                sign.assert_not_called()
                self.assertFalse(args.output.exists())

    def test_missing_execute_flag_stops_before_file_access(self):
        config = SimpleNamespace(values={"DEVELOPMENT_TEAM": MODULE.TEAM,
            "BUNDLE_IDENTIFIER": MODULE.BUNDLE, "VERSION": "1.10.0", "BUILD_NUMBER": "4",
            "EXPORT_CLASSIFICATION": "defer-to-app-store-connect"})
        with patch.object(MODULE, "public_config", return_value=config), \
                patch.object(MODULE, "digest") as digest, patch.object(MODULE, "run") as sign:
            with self.assertRaisesRegex(ValueError, "Explicit --execute-signing"):
                MODULE.package(SimpleNamespace(execute_signing=False))
            digest.assert_not_called()
            sign.assert_not_called()


class ExistingPrivacyResourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "GameRemote.app"
        self.app.mkdir()
        manifest = plistlib.dumps({"NSPrivacyTracking": False})
        info = plistlib.dumps({"CFBundlePackageType": "BNDL"})
        for relative in ("ios/App/PrivacyInfo.xcprivacy",
                         "third-party/nanopb/spm_resources/PrivacyInfo.xcprivacy",
                         "ios/Dependencies/curl/PrivacyInfo.xcprivacy"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(manifest)
        (self.app / "PrivacyInfo.xcprivacy").write_bytes(manifest)
        (self.root / "ios/cmake").mkdir()
        for label, recipe in (("nanopb_Privacy", "NanopbPrivacy.cmake"), ("curl_Privacy", "CurlPrivacy.cmake")):
            (self.root / "ios/cmake" / recipe).write_text(
                'file(WRITE "${bundle}/Info.plist" [=[' + info.decode() + ']=])')
            bundle = self.app / (label + ".bundle")
            bundle.mkdir()
            (bundle / "Info.plist").write_bytes(info)
            (bundle / "PrivacyInfo.xcprivacy").write_bytes(manifest)
        self.root_patch = patch.object(MODULE, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_valid_native_resources_are_preserved(self):
        before = {p.relative_to(self.app): p.read_bytes() for p in self.app.rglob("*") if p.is_file()}
        result = MODULE.privacy_resources(self.app)
        self.assertEqual(len(result), 3)
        self.assertEqual(result["PrivacyInfo.xcprivacy"], hashlib.sha256(before[Path("PrivacyInfo.xcprivacy")]).hexdigest())
        self.assertEqual(before, {p.relative_to(self.app): p.read_bytes() for p in self.app.rglob("*") if p.is_file()})

    def test_extra_bundle_member_is_rejected(self):
        (self.app / "curl_Privacy.bundle/unexpected-code").write_bytes(b"unexpected")
        with self.assertRaisesRegex(ValueError, "Unexpected privacy resource bundle members"):
            MODULE.privacy_resources(self.app)

    def test_changed_bundle_plist_is_rejected(self):
        (self.app / "curl_Privacy.bundle/Info.plist").write_bytes(plistlib.dumps({"CFBundlePackageType": "APPL"}))
        with self.assertRaisesRegex(ValueError, "bundle plist differs"):
            MODULE.privacy_resources(self.app)

    def test_changed_manifest_is_rejected(self):
        (self.app / "PrivacyInfo.xcprivacy").write_bytes(plistlib.dumps({"NSPrivacyTracking": True}))
        with self.assertRaisesRegex(ValueError, "manifest differs"):
            MODULE.privacy_resources(self.app)

    def test_manifest_symlink_is_rejected(self):
        target = self.app / "PrivacyInfo.xcprivacy"
        target.unlink()
        target.symlink_to(self.root / "ios/App/PrivacyInfo.xcprivacy")
        with self.assertRaisesRegex(ValueError, "manifest differs"):
            MODULE.privacy_resources(self.app)


if __name__ == "__main__":
    unittest.main()
