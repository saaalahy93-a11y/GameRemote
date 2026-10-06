#!/usr/bin/env python3
"""Exercise the OpenSSL producer's CMake configuration and archive safeguards.

Uses tiny host compilation fixtures without upstream archives. Android integration
and crypto compatibility still require the real release build and core tests.
"""
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "cmake/OpenSSLExternalProject.cmake"
VERSION = "3.5.9"
URL = f"https://github.com/openssl/openssl/releases/download/openssl-{VERSION}/openssl-{VERSION}.tar.gz"
SHA256 = "603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a"


class OpenSSLExternalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmake = os.environ.get("CHIAKI_TEST_CMAKE") or shutil.which("cmake")
        if not cls.cmake:
            raise RuntimeError("CMake is required; set CHIAKI_TEST_CMAKE to its executable")

    def configure(self, abi="arm64-v8a", jobs="2", archive_kind=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = MODULE
            if archive_kind:
                archive = root / "openssl-fixture.tar.gz"
                licence = b"Fixture upstream Apache licence\n"
                with tarfile.open(archive, "w:gz") as output:
                    entry = tarfile.TarInfo(f"openssl-{VERSION}/LICENSE.txt")
                    entry.size = len(licence)
                    output.addfile(entry, io.BytesIO(licence))
                module_text = MODULE.read_text().replace(
                    'https://github.com/openssl/openssl/releases/download/openssl-${CHIAKI_OPENSSL_VERSION}/openssl-${CHIAKI_OPENSSL_VERSION}.tar.gz',
                    archive.as_uri(),
                )
                if archive_kind == "valid":
                    module_text = module_text.replace(SHA256, hashlib.sha256(archive.read_bytes()).hexdigest())
                module = root / "OpenSSLExternalProject.cmake"
                module.write_text(module_text)
            (root / "CMakeLists.txt").write_text(
                'cmake_minimum_required(VERSION 3.22.1)\n'
                'project(OpenSSLContract NONE)\n'
                f'set(ANDROID_ABI "{abi}")\n'
                'set(ANDROID_NATIVE_API_LEVEL 24)\n'
                'set(ANDROID_NDK /fixture/ndk)\n'
                'set(CMAKE_C_COMPILER /fixture/ndk/bin/clang)\n'
                f'set(CHIAKI_DEPENDENCY_BUILD_JOBS "{jobs}" CACHE STRING "")\n'
                f'include("{module.as_posix()}")\n'
                'ExternalProject_Add_StepTargets(OpenSSL-ExternalProject release-notices)\n'
                'get_target_property(crypto_links OpenSSL::Crypto INTERFACE_LINK_LIBRARIES)\n'
                'get_target_property(ssl_links OpenSSL::SSL INTERFACE_LINK_LIBRARIES)\n'
                'file(WRITE "${CMAKE_BINARY_DIR}/contract.txt" '
                '"${OPENSSL_VERSION}\\n${OPENSSL_CRYPTO_LIBRARY}\\n${OPENSSL_SSL_LIBRARY}\\n${crypto_links}\\n${ssl_links}\\n")\n'
            )
            build = root / "build"
            result = subprocess.run([self.cmake, "-S", str(root), "-B", str(build)],
                                    capture_output=True, text=True, timeout=60)
            cfgcmd = build / f"openssl-{VERSION}-prefix/tmp/OpenSSL-ExternalProject-cfgcmd.txt"
            configure_command = cfgcmd.read_text() if cfgcmd.exists() else ""
            contract = (build / "contract.txt").read_text() if (build / "contract.txt").exists() else ""
            source_notice = build / "release-notices" / f"openssl-{VERSION}-SOURCE.txt"
            source_text = source_notice.read_text() if source_notice.exists() else ""
            build_commands = "\n".join(path.read_text() for path in build.rglob("build.make"))
            if archive_kind and result.returncode == 0:
                result = subprocess.run(
                    [self.cmake, "--build", str(build), "--target", "OpenSSL-ExternalProject-release-notices"],
                    capture_output=True, text=True, timeout=60,
                )
            licence_path = build / "release-notices" / f"openssl-{VERSION}-LICENSE.txt"
            licence_text = licence_path.read_text() if licence_path.exists() else None
            return result, configure_command, contract, source_text, build_commands, licence_text

    def test_android_abis_keep_static_pic_provider_and_library_contracts(self):
        for abi, target in (("arm64-v8a", "android-arm64"), ("x86_64", "android-x86_64")):
            with self.subTest(abi=abi):
                result, command, contract, source, commands, _ = self.configure(abi=abi)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for argument in (target, "--libdir=lib", "no-shared", "no-module", "no-dso", "enable-pic", "-D__ANDROID_API__=24"):
                    self.assertIn(argument, command)
                self.assertNotIn("no-deprecated", command)
                self.assertIn("ANDROID_NDK_ROOT=/fixture/ndk", command)
                self.assertIn("PATH=/fixture/ndk/bin:", command)
                self.assertIn("-j2", commands)
                self.assertTrue(contract.startswith(VERSION + "\n"), contract)
                self.assertIn("/lib/libcrypto.a", contract)
                self.assertIn("/lib/libssl.a", contract)
                self.assertIn("ssl;OpenSSL::Crypto", contract)
                self.assertIn(URL, source)
                self.assertIn(SHA256, source)
                self.assertIn("Apache-2.0", source)
                self.assertIn("2030-04-08", source)

    def test_rejects_unsupported_android_abi(self):
        result, *_ = self.configure(abi="unsupported")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Failed to match OPENSSL_OS_COMPILER", result.stdout + result.stderr)

    def test_upgrade_in_existing_build_tree_does_not_reuse_generated_headers(self):
        # Mimic 1.1.1's generated opensslconf.h becoming obsolete in 3.x: an old
        # binary-tree header must not shadow the new source-tree header.
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "A host C compiler is required")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / "build"
            module = root / "OpenSSLExternalProject.cmake"
            (root / "CMakeLists.txt").write_text(
                'cmake_minimum_required(VERSION 3.22.1)\n'
                'project(OpenSSLUpgrade NONE)\n'
                'set(ANDROID_ABI arm64-v8a)\n'
                'set(ANDROID_NATIVE_API_LEVEL 24)\n'
                'set(ANDROID_NDK /fixture/ndk)\n'
                'set(CMAKE_C_COMPILER /fixture/ndk/bin/clang)\n'
                f'include("{module.as_posix()}")\n'
                'ExternalProject_Get_Property(OpenSSL-ExternalProject SOURCE_DIR BINARY_DIR INSTALL_DIR)\n'
                'file(WRITE "${CMAKE_BINARY_DIR}/paths.txt" "${SOURCE_DIR}\\n${BINARY_DIR}\\n${INSTALL_DIR}\\n")\n'
            )
            release_paths = []
            for version, number in (("1.1.1w", 1), (VERSION, 3)):
                configure = (
                    f'#!{sys.executable}\n'
                    'from pathlib import Path\n'
                    'import shutil\n'
                    'source = Path(__file__).resolve().parent\n'
                    'Path("include/openssl").mkdir(parents=True, exist_ok=True)\n'
                    + ('shutil.copyfile(source / "include/openssl/opensslconf.h", "include/openssl/opensslconf.h")\n'
                       if number == 1 else '')
                    + f'compiler = {compiler!r}\n'
                    'Path("Makefile").write_text('
                    '"build_libs:\\n\\t\\\"" + compiler + "\\\" -Iinclude -I\\\"" + str(source / "include") + '
                    '"\\\" -c \\\"" + str(source / "fixture.c") + "\\\" -o fixture.o\\ninstall_dev:\\n\\t@:\\n")\n'
                )
                archive = root / f"openssl-{version}.tar.gz"
                files = {
                    "Configure": configure,
                    "LICENSE.txt": "Fixture licence\n",
                    "include/openssl/opensslconf.h": f"#define FIXTURE_VERSION {number}\n",
                    "fixture.c": f'#include <openssl/opensslconf.h>\n#if FIXTURE_VERSION != {number}\n#error stale generated header\n#endif\nint fixture(void) {{ return FIXTURE_VERSION; }}\n',
                }
                with tarfile.open(archive, "w:gz") as output:
                    for name, content in files.items():
                        entry = tarfile.TarInfo(f"openssl-{version}/{name}")
                        data = content.encode()
                        entry.size = len(data)
                        entry.mode = 0o755 if name == "Configure" else 0o644
                        output.addfile(entry, io.BytesIO(data))
                module.write_text(MODULE.read_text().replace(
                    'https://github.com/openssl/openssl/releases/download/openssl-${CHIAKI_OPENSSL_VERSION}/openssl-${CHIAKI_OPENSSL_VERSION}.tar.gz',
                    archive.as_uri(),
                ).replace(SHA256, hashlib.sha256(archive.read_bytes()).hexdigest())
                  .replace(f'set(CHIAKI_OPENSSL_VERSION "{VERSION}")', f'set(CHIAKI_OPENSSL_VERSION "{version}")')
                  # Exercise compilation even when stamp mtimes fall within one
                  # Make timestamp tick during this deliberately rapid upgrade.
                  .replace('ExternalProject_Add(OpenSSL-ExternalProject\n',
                           'ExternalProject_Add(OpenSSL-ExternalProject\nBUILD_ALWAYS TRUE\n'))
                for command in ([self.cmake, "-S", str(root), "-B", str(build)],
                                [self.cmake, "--build", str(build), "--target", "OpenSSL-ExternalProject"]):
                    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                paths = (build / "paths.txt").read_text().splitlines()
                self.assertTrue((Path(paths[1]) / "fixture.o").exists())
                release_paths.append(paths)
            for previous, current in zip(*release_paths):
                self.assertNotEqual(previous, current)
                self.assertTrue(Path(previous).exists(), "Old build outputs must remain intact")

    def test_rejects_invalid_dependency_job_limit(self):
        result, *_ = self.configure(jobs="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be a positive integer", result.stdout + result.stderr)

    def test_copies_licence_from_verified_archive_before_configuration(self):
        result, *_, licence = self.configure(archive_kind="valid")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(licence, "Fixture upstream Apache licence\n")

    def test_rejects_archive_with_wrong_release_checksum(self):
        result, *_, licence = self.configure(archive_kind="tampered")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match expected value", result.stdout + result.stderr)
        self.assertIsNone(licence)


if __name__ == "__main__":
    unittest.main()
