"""Prove unsafe release requests stop before profile access or signing."""
import importlib.util
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
                "BUNDLE_IDENTIFIER": MODULE.BUNDLE, "VERSION": "1.10.0", "BUILD_NUMBER": "3",
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
            "BUNDLE_IDENTIFIER": MODULE.BUNDLE, "VERSION": "1.10.0", "BUILD_NUMBER": "3",
            "EXPORT_CLASSIFICATION": "defer-to-app-store-connect"})
        with patch.object(MODULE, "public_config", return_value=config), \
                patch.object(MODULE, "digest") as digest, patch.object(MODULE, "run") as sign:
            with self.assertRaisesRegex(ValueError, "Explicit --execute-signing"):
                MODULE.package(SimpleNamespace(execute_signing=False))
            digest.assert_not_called()
            sign.assert_not_called()


if __name__ == "__main__":
    unittest.main()
