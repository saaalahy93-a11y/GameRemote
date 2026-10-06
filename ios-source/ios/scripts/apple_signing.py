#!/usr/bin/env python3
"""Explicit manual signing and local IPA validation; no Apple account or upload APIs."""
import base64
import hashlib
import json
import os
import plistlib
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import unicodedata
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from release_config import ReleaseConfig

SECRET_NAMES = ("GR_IOS_CERTIFICATE_P12_BASE64", "GR_IOS_CERTIFICATE_PASSWORD", "GR_IOS_PROFILE_BASE64")


def public_config(mode, environment=None):
    environment = os.environ if environment is None else environment
    if mode not in {"development", "store"}:
        raise ValueError("Signing mode must be development or store")
    config = ReleaseConfig.from_environment(store=mode == "store", environment=environment)
    config.validate()
    for field in ("BUNDLE_IDENTIFIER", "DEVELOPMENT_TEAM", "VERSION", "BUILD_NUMBER"):
        if not environment.get("GR_IOS_" + field):
            raise ValueError("GR_IOS_" + field + " is required for signed device builds")
    return config


def native(command, *, input=None, environment=None):
    """Keep credential-tool output and argv out of errors and build logs."""
    environment = dict(os.environ if environment is None else environment)
    for name in SECRET_NAMES:
        environment.pop(name, None)
    try:
        result = subprocess.run(command, input=input, capture_output=True, text=True,
                                env=environment, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Native signing/verification command could not complete") from None
    if result.returncode:
        raise RuntimeError("Native signing/verification command failed (output withheld)")
    return result


def security_command(arguments):
    # Apple's security -i reads one command from stdin and returns its status at EOF.
    # Its parser is not a shell: each double-quoted argument is escaped independently.
    if any(any(ord(char) < 32 or ord(char) == 127 for char in item) for item in arguments):
        raise ValueError("Signing command inputs must not contain control characters")
    line = " ".join('"' + item.replace("\\", "\\\\").replace('"', '\\"') + '"' for item in arguments) + "\n"
    if len(line.encode()) >= 4096:
        raise ValueError("Signing command exceeds Apple's interactive input limit")
    return native(["security", "-q", "-i"], input=line)


@dataclass(frozen=True)
class ManualSigning:
    identity: str
    profile_uuid: str
    keychain: Path

    def validate(self):
        if not isinstance(self.identity, str) or not re.fullmatch(r"[A-Fa-f0-9]{40}", self.identity):
            raise ValueError("Signing identity must be an explicit 40-digit certificate SHA-1 fingerprint")
        try:
            if not isinstance(self.profile_uuid, str) or str(uuid.UUID(self.profile_uuid)).upper() != self.profile_uuid.upper():
                raise ValueError()
        except (ValueError, AttributeError):
            raise ValueError("Provisioning profile UUID is invalid") from None
        if not self.keychain.is_absolute() or any(c in str(self.keychain) for c in "\r\n\0"):
            raise ValueError("Signing keychain must have an absolute path")

    def cmake_arguments(self):
        self.validate()
        return ["-DCHIAKI_IOS_MANUAL_SIGNING=ON", "-DCHIAKI_IOS_SIGNING_IDENTITY=" + self.identity,
                "-DCHIAKI_IOS_SIGNING_PROFILE_UUID=" + self.profile_uuid,
                "-DCHIAKI_IOS_SIGNING_KEYCHAIN_FLAGS=--keychain " + shlex.quote(str(self.keychain))]

    def export_options(self, config):
        self.validate()
        return {"method": "app-store-connect" if config.store else "debugging",
                "destination": "export", "signingStyle": "manual",
                "teamID": config.values["DEVELOPMENT_TEAM"], "signingCertificate": self.identity,
                "provisioningProfiles": {config.values["BUNDLE_IDENTIFIER"]: self.profile_uuid},
                "manageAppVersionAndBuildNumber": False, "uploadSymbols": False,
                "thinning": "<none>"}


def validate_profile(profile, config, identity, now=None):
    if not isinstance(profile, dict) or not isinstance(profile.get("Entitlements"), dict):
        raise ValueError("Provisioning profile lacks its entitlement dictionary")
    team, bundle = config.values["DEVELOPMENT_TEAM"], config.values["BUNDLE_IDENTIFIER"]
    entitlements = profile.get("Entitlements", {})
    if profile.get("TeamIdentifier") != [team] or entitlements.get("com.apple.developer.team-identifier") != team:
        raise ValueError("Provisioning profile team does not match configured team")
    if entitlements.get("application-identifier") != team + "." + bundle:
        raise ValueError("Provisioning profile must match the exact app identifier (no wildcard)")
    expiry = profile.get("ExpirationDate")
    if not isinstance(expiry, datetime) or expiry.replace(tzinfo=timezone.utc) <= (now or datetime.now(timezone.utc)):
        raise ValueError("Provisioning profile is expired or lacks an expiry")
    if not isinstance(profile.get("Platform"), list) or "iOS" not in profile["Platform"]:
        raise ValueError("Provisioning profile is not for iOS")
    devices = profile.get("ProvisionedDevices")
    if profile.get("ProvisionsAllDevices") or (config.store and (devices is not None or entitlements.get("get-task-allow") is not False)):
        raise ValueError("Store export requires an App Store distribution profile")
    if not config.store and (not isinstance(devices, list) or not devices or entitlements.get("get-task-allow") is not True):
        raise ValueError("Development export requires a development profile with registered devices")
    certificates = profile.get("DeveloperCertificates", [])
    if not isinstance(certificates, list) or not any(isinstance(cert, bytes) and hashlib.sha1(cert).hexdigest().upper() == identity.upper() for cert in certificates):
        raise ValueError("Provisioning profile does not contain the selected signing certificate")
    profile_uuid = profile.get("UUID", "")
    ManualSigning(identity, profile_uuid, Path("/validation-only.keychain-db")).validate()
    return profile_uuid


def decode_profile(path):
    result = native(["security", "cms", "-D", "-i", str(path)])
    try:
        return plistlib.loads(result.stdout.encode())
    except (ValueError, plistlib.InvalidFileException):
        raise ValueError("Provisioning profile could not be decoded") from None


def private_write(path, content):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def save_state(path, state):
    pending = path.with_name(path.name + ".update")
    private_write(pending, json.dumps(state).encode())
    try:
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def cleanup_signing(state_path):
    if not state_path.is_absolute() or state_path.is_symlink():
        raise ValueError("Signing cleanup state must be an absolute regular path")
    if not state_path.exists():
        return
    state_path = state_path.parent.resolve() / state_path.name
    state = json.loads(state_path.read_text())
    directory = Path(state["directory"])
    # Cleanup is restricted to the helper's single temporary directory and UUID profile.
    if (directory.parent != state_path.parent or not directory.name.startswith("gameremote-signing-")
            or directory.is_symlink() or directory != directory.resolve()):
        raise ValueError("Refusing unexpected signing cleanup directory")
    keychain = directory / "signing.keychain-db"
    failures = []
    if state.get("installed_profile"):
        ManualSigning("0" * 40, state["profile_uuid"], keychain).validate()
        profile = Path(state["installed_profile"])
        expected = Path.home() / "Library/Developer/Xcode/UserData/Provisioning Profiles" / (state["profile_uuid"] + ".mobileprovision")
        if profile != expected:
            raise ValueError("Refusing unexpected profile cleanup path")
        try:
            if profile.exists() or profile.is_symlink():
                current = profile.lstat()
                # Retained cleanup state must never delete a later owner's replacement.
                owned = [current.st_dev, current.st_ino] == state["profile_owner"] and not profile.is_symlink()
                if owned and state.get("profile_sha256"):
                    owned = hashlib.sha256(profile.read_bytes()).hexdigest() == state["profile_sha256"]
                if owned:
                    profile.unlink()
            state["installed_profile"] = None
            save_state(state_path, state)
        except OSError:
            failures.append("profile removal")
    if keychain.exists():
        try:
            native(["security", "delete-keychain", str(keychain)])
        except RuntimeError:
            failures.append("temporary keychain removal")
    if not state.get("search_list_restored"):
        try:
            native(["security", "list-keychains", "-d", "user", "-s", *state["search_list"]])
            state["search_list_restored"] = True
            save_state(state_path, state)
        except (OSError, RuntimeError):
            failures.append("keychain search-list restoration")
    for name in ("certificate.p12", "profile.mobileprovision"):
        try:
            (directory / name).unlink(missing_ok=True)
        except OSError:
            failures.append("temporary credential removal")
    if failures:
        raise RuntimeError("Signing cleanup failed: " + ", ".join(failures) + "; cleanup state retained")
    shutil.rmtree(directory)
    state_path.unlink()


@contextmanager
def temporary_signing(config, identity, state_path, environment=None):
    environment = os.environ if environment is None else environment
    if not state_path.is_absolute() or state_path.exists() or state_path.is_symlink():
        raise ValueError("Signing cleanup state must be a fresh absolute path")
    ManualSigning(identity, "00000000-0000-0000-0000-000000000001", Path("/validation-only")).validate()
    if any(name not in environment or not environment[name] for name in SECRET_NAMES):
        raise ValueError("Explicit PKCS#12, password and provisioning-profile secrets are required")
    try:
        certificate = base64.b64decode(environment[SECRET_NAMES[0]], validate=True)
        profile_bytes = base64.b64decode(environment[SECRET_NAMES[2]], validate=True)
    except ValueError:
        raise ValueError("Signing credentials must use valid base64") from None
    if not certificate or not profile_bytes or max(len(certificate), len(profile_bytes)) > 1024 * 1024:
        raise ValueError("Signing credential files must be nonempty and at most 1 MiB")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    # Normalize the parent once so the independently callable cleanup can bind its scope.
    state_path = state_path.parent.resolve() / state_path.name
    search_list = shlex.split(native(["security", "list-keychains", "-d", "user"]).stdout)
    directory = Path(tempfile.mkdtemp(prefix="gameremote-signing-", dir=state_path.parent))
    state = {"directory": str(directory), "search_list": search_list, "installed_profile": None}
    try:
        private_write(state_path, json.dumps(state).encode())
    except BaseException:
        directory.rmdir()
        raise
    try:
        certificate_path, profile_path = directory / "certificate.p12", directory / "profile.mobileprovision"
        private_write(certificate_path, certificate)
        private_write(profile_path, profile_bytes)
        profile_uuid = validate_profile(decode_profile(profile_path), config, identity)
        installed = Path.home() / "Library/Developer/Xcode/UserData/Provisioning Profiles" / (profile_uuid + ".mobileprovision")
        installed.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite or delete an existing owner's profile.
        descriptor = os.open(installed, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                owned = os.fstat(stream.fileno())
                state.update(installed_profile=str(installed), profile_uuid=profile_uuid,
                             profile_owner=[owned.st_dev, owned.st_ino])
                save_state(state_path, state)
                stream.write(profile_bytes)
        except BaseException:
            installed.unlink(missing_ok=True)
            raise
        state["profile_sha256"] = hashlib.sha256(profile_bytes).hexdigest()
        save_state(state_path, state)
        keychain = directory / "signing.keychain-db"
        password = os.urandom(32).hex()
        security_command(["create-keychain", "-p", password, str(keychain)])
        security_command(["set-keychain-settings", "-lut", "3600", str(keychain)])
        security_command(["unlock-keychain", "-p", password, str(keychain)])
        security_command(["import", str(certificate_path), "-k", str(keychain), "-P", environment[SECRET_NAMES[1]],
                          "-T", "/usr/bin/codesign", "-T", "/usr/bin/security"])
        security_command(["set-key-partition-list", "-S", "apple-tool:,apple:,codesign:", "-k", password, str(keychain)])
        native(["security", "list-keychains", "-d", "user", "-s", str(keychain), *search_list])
        available = native(["security", "find-identity", "-v", "-p", "codesigning", str(keychain)]).stdout
        if not re.search(r"\b" + re.escape(identity.upper()) + r"\b", available.upper()):
            raise ValueError("Selected signing identity is not usable in the temporary keychain")
        yield ManualSigning(identity, profile_uuid, keychain)
    finally:
        cleanup_signing(state_path)


def verify_signed_app(app, config, signing):
    config.verify_plist(app / "Info.plist")
    info = plistlib.loads((app / "Info.plist").read_bytes())
    if info.get("CFBundleExecutable") != "GameRemote" or info.get("CFBundleSupportedPlatforms") != ["iPhoneOS"]:
        raise ValueError("Exported app is not the expected physical-device app")
    if not os.access(app / "GameRemote", os.X_OK):
        raise ValueError("Exported app executable is missing or not executable")
    for resource in ("Assets.car", "PrivacyInfo.xcprivacy", "AGPL-3.0-only-OpenSSL.txt", "ThirdPartyNotices.txt", "embedded.mobileprovision"):
        if not (app / resource).is_file() or not (app / resource).stat().st_size:
            raise ValueError("Exported app lacks a required resource")
    native(["codesign", "--verify", "--deep", "--strict", str(app)])
    details = native(["codesign", "--display", "--verbose=4", str(app)]).stderr.splitlines()
    if "TeamIdentifier=" + config.values["DEVELOPMENT_TEAM"] not in details:
        raise ValueError("Exported signature team does not match")
    entitlements = plistlib.loads(native(["codesign", "--display", "--entitlements", "-", "--xml", str(app)]).stdout.encode())
    if entitlements.get("com.apple.developer.team-identifier") != config.values["DEVELOPMENT_TEAM"]:
        raise ValueError("Exported signature team entitlement does not match")
    if entitlements.get("application-identifier") != config.values["DEVELOPMENT_TEAM"] + "." + config.values["BUNDLE_IDENTIFIER"]:
        raise ValueError("Exported signature app identifier does not match")
    if entitlements.get("get-task-allow", False) is not (not config.store):
        raise ValueError("Exported signature is for the wrong distribution mode")
    profile_uuid = validate_profile(decode_profile(app / "embedded.mobileprovision"), config, signing.identity)
    if profile_uuid != signing.profile_uuid:
        raise ValueError("Exported app contains an unexpected provisioning profile")
    if native(["lipo", "-archs", str(app / "GameRemote")]).stdout.strip() != "arm64":
        raise ValueError("Exported app must contain only the arm64 device architecture")
    platform = native(["xcrun", "vtool", "-show-build", str(app / "GameRemote")]).stdout
    if re.findall(r"(?m)^\s*platform\s+(\S+)\s*$", platform) != ["IOS"]:
        raise ValueError("Exported executable is not an iOS device Mach-O")
    with tempfile.TemporaryDirectory(prefix="gameremote-cert-check-") as directory:
        prefix = str(Path(directory) / "signer")
        native(["codesign", "--display", "--extract-certificates", prefix, str(app)])
        leaf = Path(prefix + "0")
        if not leaf.is_file() or hashlib.sha1(leaf.read_bytes()).hexdigest().upper() != signing.identity.upper():
            raise ValueError("Exported app was not signed by the selected certificate")


def verify_ipa(ipa, config, signing):
    with zipfile.ZipFile(ipa) as archive, tempfile.TemporaryDirectory(prefix="gameremote-ipa-check-") as directory:
        members = archive.infolist()
        if len(members) > 10000 or sum(item.file_size for item in members) > 512 * 1024 * 1024:
            raise ValueError("IPA exceeds the validation size budget")
        seen, spellings = set(), {}
        for item in members:
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename or str(path) in seen or str(path) == "." or stat.S_ISLNK(mode):
                raise ValueError("IPA contains unsafe or duplicate archive members")
            seen.add(str(path))
            # APFS/HFS+ can alias case and Unicode spellings, including implicit parents.
            for index in range(1, len(path.parts) + 1):
                spelling = "/".join(path.parts[:index])
                canonical = unicodedata.normalize("NFD", spelling).casefold()
                if canonical in spellings and spellings[canonical] != spelling:
                    raise ValueError("IPA contains filesystem name aliases")
                spellings[canonical] = spelling
        archive.extractall(directory)
        for item in members:
            path = Path(directory) / item.filename
            if path.is_file():
                path.chmod(0o600 | ((item.external_attr >> 16) & 0o111))
        apps = list((Path(directory) / "Payload").glob("*.app"))
        if len(apps) != 1 or apps[0].name != "GameRemote.app":
            raise ValueError("IPA must contain exactly Payload/GameRemote.app")
        verify_signed_app(apps[0], config, signing)
