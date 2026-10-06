#!/usr/bin/env python3
"""Plan or explicitly create a manually signed iOS archive; never upload."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from apple_signing import ManualSigning, SECRET_NAMES, public_config


def create_archive(output: Path, root: Path, signing=None, mode="store") -> Path:
    config = public_config(mode)
    config.validate()  # Must fail before Xcode, directory creation or signing.
    if not output.is_absolute():
        raise ValueError("Archive output must be an absolute path to a new directory")
    if output.exists() or output.is_symlink():
        raise ValueError("Archive output already exists; choose a fresh directory (nothing is overwritten)")
    if signing is None:
        raise ValueError("Explicit manual signing identity, profile UUID and keychain are required")
    signing.validate()
    jobs = os.environ.get("CMAKE_BUILD_PARALLEL_LEVEL", "2")
    if jobs not in {"1", "2"}:
        raise ValueError("Signed archive build parallelism must be 1 or 2")
    environment = {key: value for key, value in os.environ.items() if key not in SECRET_NAMES}
    subprocess.run([str(root / "ios/scripts/preflight.sh")], check=True, env=environment)
    if not (root / "third-party/curl/CMakeLists.txt").is_file():
        raise ValueError("Initialize pinned submodules first: git submodule update --init --recursive")
    host_python = os.environ.get("CHIAKI_HOST_PYTHON") or shutil.which("python3")
    host_protoc = os.environ.get("CHIAKI_HOST_PROTOC") or shutil.which("protoc")
    if not host_python or not host_protoc:
        raise ValueError("The preflight-selected host Python and protoc must be available")
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment["PATH"] = str(Path(host_python).parent) + os.pathsep + str(Path(host_protoc).parent) + os.pathsep + environment.get("PATH", "")
    output.mkdir(parents=True, exist_ok=False)
    build = output / "build"
    archive = output / "GameRemote.xcarchive"
    subprocess.run([
        "cmake", "-S", str(root / "ios"), "-B", str(build), "-G", "Xcode",
        "-DCMAKE_TOOLCHAIN_FILE=" + str(root / "ios/cmake/ios.cmake"),
        "-DCMAKE_OSX_SYSROOT=iphoneos", "-DCMAKE_OSX_ARCHITECTURES=arm64",
        "-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO",
        "-DPYTHON_EXECUTABLE=" + host_python, "-DPython_EXECUTABLE=" + host_python,
        "-DPROTOC=" + host_protoc, "-Dnanopb_PROTOC_PATH=" + host_protoc,
        "-DCMAKE_POLICY_VERSION_MINIMUM=3.5", "-DFETCHCONTENT_QUIET=OFF",
        *config.cmake_arguments(), *signing.cmake_arguments(),
    ], check=True, env=environment)
    # CMake applies manual signing only to GameRemoteIOS. Global Xcode overrides
    # would incorrectly force the app profile onto static-library dependencies.
    subprocess.run([
        "xcodebuild", "-project", str(build / "GameRemoteIOS.xcodeproj"),
        "-scheme", "GameRemoteIOS", "-configuration", "Release",
        "-sdk", "iphoneos", "-destination", "generic/platform=iOS",
        "-archivePath", str(archive), "-derivedDataPath", str(output / "DerivedData"),
        "-jobs", jobs, "archive", "GR_IOS_ARCHIVE_SIGNING=YES",
    ], check=True, env=environment)
    app = archive / "Products/Applications/GameRemote.app"
    config.verify_plist(app / "Info.plist")
    if not os.access(app / "GameRemote", os.X_OK):
        raise ValueError("Archived app executable is missing or not executable")
    for resource in ("Assets.car", "PrivacyInfo.xcprivacy", "AGPL-3.0-only-OpenSSL.txt", "ThirdPartyNotices.txt", "embedded.mobileprovision"):
        if not (app / resource).is_file() or (app / resource).stat().st_size == 0:
            raise ValueError("Archived app is missing " + resource)
    subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True, env=environment)
    identity = subprocess.run(["codesign", "--display", "--verbose=4", str(app)], check=True, capture_output=True, text=True, env=environment)
    if "TeamIdentifier=" + config.values["DEVELOPMENT_TEAM"] not in identity.stderr.splitlines():
        raise ValueError("Archived signature does not have the configured development team")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Absolute path to a new directory for this archive attempt")
    parser.add_argument("--mode", choices=("development", "store"), default="store")
    parser.add_argument("--identity", required=True)
    parser.add_argument("--profile-uuid", required=True)
    parser.add_argument("--keychain", type=Path, required=True)
    parser.add_argument("--execute-signing", action="store_true")
    args = parser.parse_args()
    try:
        public_config(args.mode)
        signing = ManualSigning(args.identity, args.profile_uuid, args.keychain)
        signing.validate()
        if not args.execute_signing:
            print("Manual archive configuration validated; no build or signing performed. Use --execute-signing explicitly.")
            return 0
        archive = create_archive(args.output, Path(__file__).resolve().parents[2], signing, args.mode)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("FAIL iOS store archive: " + str(error), file=sys.stderr)
        return 2
    print("Created and locally verified signed archive: " + str(archive))
    print("No export, upload, App Store validation or publication was performed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
