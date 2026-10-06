#!/usr/bin/env python3
"""Exercise CMake gates and compile host fixtures without Android binaries."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "cmake/OboeStatic.cmake"
ARCHIVE_URL = "https://codeload.github.com/google/oboe/tar.gz/refs/tags/1.10.0"


class OboeStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmake = os.environ.get("CHIAKI_TEST_CMAKE") or shutil.which("cmake")
        if not cls.cmake:
            raise RuntimeError("CMake is required; set CHIAKI_TEST_CMAKE to its executable")

    def configure(self, library_kind="", runtime="c++_static", tamper=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fixture-oboe"
            source.mkdir()
            (source / "fixture.cpp").write_text(
                "#include <shared_mutex>\n"
                "std::shared_mutex fixture_mutex;\n"
                "int fixture(void) { return 1; }\n")
            (root / "consumer.cpp").write_text(
                "#include <shared_mutex>\n"
                "extern int fixture(void);\n"
                "std::shared_mutex consumer_mutex;\n"
                "int main() { return fixture() == 1 ? 0 : 1; }\n")
            (source / "LICENSE").write_text("Fixture licence content\n")
            (source / "CMakeLists.txt").write_text(
                f"add_library(oboe {library_kind} fixture.cpp)\n"
                # Reproduce Oboe 1.10.0's raw flag under a C++14 parent.
                'target_compile_options(oboe PRIVATE -std=c++17)\n')
            module = MODULE
            override = f'set(FETCHCONTENT_SOURCE_DIR_CHIAKI_OBOE "{source.as_posix()}")\n'
            if tamper:
                # Keep the production expected digest and change only the input.
                # CMake must reject it before attempting extraction/configuration.
                archive = root / "tampered.tar.gz"
                archive.write_bytes(b"tampered archive")
                module = root / "OboeStatic.cmake"
                module.write_text(MODULE.read_text().replace(ARCHIVE_URL, archive.as_uri()))
                override = ""
            (root / "CMakeLists.txt").write_text(
                'cmake_minimum_required(VERSION 3.22.1)\n'
                'project(OboeContract LANGUAGES CXX)\n'
                'set(CMAKE_CXX_STANDARD 14)\n'
                'set(ANDROID TRUE)\n'
                f'set(ANDROID_STL "{runtime}")\n'
                'set(BUILD_SHARED_LIBS ON)\n'
                + override
                + f'include("{module.as_posix()}")\n'
                'get_target_property(kind oboe TYPE)\n'
                'get_target_property(pic oboe POSITION_INDEPENDENT_CODE)\n'
                'if(NOT kind STREQUAL "STATIC_LIBRARY" OR NOT pic)\n'
                '  message(FATAL_ERROR "Static/PIC contract failed")\n'
                'endif()\n'
                'if(NOT BUILD_SHARED_LIBS)\n'
                '  message(FATAL_ERROR "Oboe changed parent build policy")\n'
                'endif()\n'
                'if(NOT CMAKE_CXX_STANDARD EQUAL 14)\n'
                '  message(FATAL_ERROR "Oboe changed parent C++ standard")\n'
                'endif()\n'
                'get_target_property(standard oboe CXX_STANDARD)\n'
                'get_target_property(required oboe CXX_STANDARD_REQUIRED)\n'
                'if(NOT standard EQUAL 17 OR NOT required)\n'
                '  message(FATAL_ERROR "Oboe C++17 contract failed")\n'
                'endif()\n'
                'add_executable(consumer consumer.cpp)\n'
                'target_link_libraries(consumer PRIVATE oboe)\n')
            build = root / "build"
            result = subprocess.run([self.cmake, "-S", str(root), "-B", str(build)],
                                    capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                result = subprocess.run([self.cmake, "--build", str(build)],
                                        capture_output=True, text=True, timeout=60)
            notices = build / "release-notices"
            license_text = (notices / "oboe-1.10.0-LICENSE.txt").read_text() if notices.exists() else None
            return result, license_text

    def test_builds_static_cpp17_and_consumer_under_cpp14_parent(self):
        result, license_text = self.configure()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(license_text, "Fixture licence content\n")

    def test_rejects_source_that_produces_a_shared_library(self):
        result, _ = self.configure(library_kind="SHARED")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Oboe must be static", result.stdout + result.stderr)

    def test_rejects_shared_cpp_runtime(self):
        result, _ = self.configure(runtime="c++_shared")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires Android with c++_static", result.stdout + result.stderr)

    def test_rejects_changed_source_archive_digest(self):
        result, _ = self.configure(tamper=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match expected value", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
