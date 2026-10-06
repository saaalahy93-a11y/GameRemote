"""Exercise the real FetchContent integrity and licence-export paths offline."""
import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEPENDENCIES = (
    ("JsoncExternalProject.cmake", "JSONC", "", "COPYING", "json-c-0.17"),
    ("MiniupnpcExternalProject.cmake", "MINIUPNPC", "miniupnpc/", "LICENSE", "miniupnpc-2.2.8"),
)
LICENCE = "Fixture upstream licence\nAll fixture notices retained.\n"


class SourceArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmake = os.environ.get("CHIAKI_TEST_CMAKE") or shutil.which("cmake")
        if not cls.cmake:
            raise RuntimeError("CMake is required; set CHIAKI_TEST_CMAKE")

    def configure(self, dependency, *, corrupt=False, missing_licence=False):
        module_name, key, subdir, licence_name, notice_name = dependency
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "fixture.tar.gz"
            entries = {
                "CMakeLists.txt": (
                    "cmake_minimum_required(VERSION 3.22.1)\n"
                    "project(DependencyFixture LANGUAGES NONE)\n"
                )
            }
            if not missing_licence:
                entries[licence_name] = LICENCE
            with tarfile.open(archive, "w:gz") as tar:
                for name, text in entries.items():
                    data = text.encode()
                    member = tarfile.TarInfo(f"fixture/{subdir}{name}")
                    member.size = len(data)
                    tar.addfile(member, io.BytesIO(data))
            expected_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            module_text = (ROOT / "cmake" / module_name).read_text()
            # Adapt only the declared inputs. The production FetchContent and
            # export code, including URL_HASH, executes unchanged.
            for suffix, value in (("URL", archive.as_uri()), ("SHA256", expected_digest)):
                module_text, count = re.subn(
                    rf'set\(GAMEREMOTE_{key}_SOURCE_{suffix} "[^"\n]+"\)',
                    f'set(GAMEREMOTE_{key}_SOURCE_{suffix} "{value}")',
                    module_text,
                )
                self.assertEqual(count, 1, "Fixture must replace one declared source input")
            if corrupt:
                # Still a readable tarball; without URL_HASH this would configure
                # successfully. A parser failure cannot make this test pass.
                with tarfile.open(archive, "w:gz") as tar:
                    for name, text in entries.items():
                        data = (text + "\n").encode()
                        member = tarfile.TarInfo(f"fixture/{subdir}{name}")
                        member.size = len(data)
                        tar.addfile(member, io.BytesIO(data))
                self.assertNotEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), expected_digest)
            module = root / module_name
            module.write_text(module_text)
            (root / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.22.1)\n"
                "project(SourceContract LANGUAGES NONE)\n"
                f'include("{module.as_posix()}")\n'
            )
            build = root / "build"
            result = subprocess.run(
                [self.cmake, "-S", str(root), "-B", str(build)],
                capture_output=True, text=True, timeout=60, check=False,
            )
            notices = build / "release-notices"
            licence = notices / f"{notice_name}-LICENSE.txt"
            source = notices / f"{notice_name}-SOURCE.txt"
            return (
                result,
                licence.read_text() if licence.exists() else None,
                source.read_text() if source.exists() else None,
                expected_digest,
            )

    def test_verified_archive_configures_and_exports_exact_notice(self):
        for dependency in DEPENDENCIES:
            with self.subTest(dependency=dependency[0]):
                result, licence, source, digest = self.configure(dependency)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(licence, LICENCE)
                self.assertIn(f"Expected archive SHA256: {digest}\n", source)
                self.assertIn("Declared upstream source: file://", source)

    def test_changed_valid_archive_is_rejected_before_configuration(self):
        for dependency in DEPENDENCIES:
            with self.subTest(dependency=dependency[0]):
                result, licence, _, _ = self.configure(dependency, corrupt=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("does not match expected value", result.stdout + result.stderr)
                self.assertIsNone(licence)

    def test_missing_licence_fails_release_notice_assembly(self):
        for dependency in DEPENDENCIES:
            with self.subTest(dependency=dependency[0]):
                result, licence, _, _ = self.configure(dependency, missing_licence=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(dependency[3], result.stdout + result.stderr)
                self.assertIn("does not exist", result.stdout + result.stderr)
                self.assertIsNone(licence)


if __name__ == "__main__":
    unittest.main()
