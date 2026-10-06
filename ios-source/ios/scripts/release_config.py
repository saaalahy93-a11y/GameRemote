#!/usr/bin/env python3
"""Validate public iOS build metadata without Xcode, accounts, or network access."""

import argparse
import ipaddress
import os
import plistlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

FIELDS = (
    "BUNDLE_IDENTIFIER", "DEVELOPMENT_TEAM", "VERSION", "BUILD_NUMBER",
    "PRIVACY_URL", "SUPPORT_URL", "SOURCE_URL", "EXPORT_CLASSIFICATION",
)
DEVELOPMENT_DEFAULTS = {
    "BUNDLE_IDENTIFIER": "org.example.RemotePlayPrototype.iOS",
    "VERSION": "1.10.0",
    "BUILD_NUMBER": "2",
}
PLACEHOLDERS = {"example", "placeholder", "changeme", "yourdomain", "yourcompany", "tbd"}
URL_PLIST_KEYS = {
    "PRIVACY_URL": "GameRemotePrivacyPolicyURL",
    "SUPPORT_URL": "GameRemoteSupportURL",
    "SOURCE_URL": "GameRemoteSourceURL",
}


def is_public_https_url(value: str) -> bool:
    """Check URL syntax and known local/placeholder hosts, not ownership or uptime."""
    if not value or not value.isascii() or re.search(r"[\s<>\"'\\;$]", value):
        return False
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        return False
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        if url.scheme != "https" or url.username is not None or url.password is not None:
            return False
        if url.port is not None and not 1 <= url.port <= 65535:
            return False
        labels = host.lower().split(".")
        if len(labels) < 2 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
            return False
        if labels[-1] in {"local", "localhost", "test", "invalid", "example", "internal", "lan", "home"}:
            return False
        if PLACEHOLDERS.intersection(re.split(r"[.\-]", host.lower())):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return not labels[-1].isdigit()
    except ValueError:
        return False


@dataclass(frozen=True)
class ReleaseConfig:
    values: dict[str, str]
    store: bool = False

    @classmethod
    def from_environment(cls, store: bool = False, environment=None):
        environment = os.environ if environment is None else environment
        defaults = {} if store else DEVELOPMENT_DEFAULTS
        return cls({field: environment.get("GR_IOS_" + field, defaults.get(field, "")) for field in FIELDS}, store)

    def validate(self) -> None:
        errors = []
        for field in FIELDS:
            if self.store and not self.values[field]:
                errors.append("GR_IOS_" + field + " is required for a store archive")
        bundle = self.values["BUNDLE_IDENTIFIER"]
        label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
        if not re.fullmatch(label + r"(?:\." + label + r"){2,}", bundle) or len(bundle) > 255:
            errors.append("BUNDLE_IDENTIFIER must be a reverse-DNS app identifier")
        elif self.store and (PLACEHOLDERS.intersection(re.split(r"[.\-]", bundle.lower())) or "prototype" in bundle.lower()):
            errors.append("BUNDLE_IDENTIFIER must be publisher-owned; development placeholders are rejected")
        team = self.values["DEVELOPMENT_TEAM"]
        if team and (not re.fullmatch(r"[A-Z0-9]{10}", team) or len(set(team)) == 1 or team in {"ABCDEFGHIJ", "0123456789", "1234567890", "YOURTEAMID"}):
            errors.append("DEVELOPMENT_TEAM must be the 10-character Apple team identifier")
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", self.values["VERSION"]):
            errors.append("VERSION must contain three dot-separated non-negative integers")
        # Apple's release form: one to three numeric parts, first > 0, with 4/2/2 digit limits.
        if not re.fullmatch(r"[1-9][0-9]{0,3}(?:\.(?:0|[1-9][0-9]?)){0,2}", self.values["BUILD_NUMBER"]):
            errors.append("BUILD_NUMBER must have one to three numeric parts with 4/2/2 digit limits and a positive first part")
        for field in URL_PLIST_KEYS:
            value = self.values[field]
            if value and not is_public_https_url(value):
                errors.append(field + " must be an absolute public HTTPS URL without credentials or placeholders")
        classification = self.values["EXPORT_CLASSIFICATION"]
        if classification and classification not in {"exempt", "non-exempt"}:
            errors.append("EXPORT_CLASSIFICATION must be the owner's final 'exempt' or 'non-exempt' determination")
        if errors:
            raise ValueError("\n".join(errors))

    def cmake_arguments(self) -> list[str]:
        return ["-DCHIAKI_IOS_STORE_RELEASE=" + ("ON" if self.store else "OFF")] + [
            "-DCHIAKI_IOS_" + field + "=" + self.values[field] for field in FIELDS
        ]

    def verify_plist(self, path: Path) -> None:
        with path.open("rb") as stream:
            info = plistlib.load(stream)
        expected = {
            "CFBundleIdentifier": self.values["BUNDLE_IDENTIFIER"],
            "CFBundleShortVersionString": self.values["VERSION"],
            "CFBundleVersion": self.values["BUILD_NUMBER"],
            **{key: self.values[field] for field, key in URL_PLIST_KEYS.items()},
        }
        for key, value in expected.items():
            if info.get(key) != value:
                raise ValueError("Archive Info.plist does not match configured " + key)
        classification = self.values["EXPORT_CLASSIFICATION"]
        if classification and info.get("ITSAppUsesNonExemptEncryption") is not (classification == "non-exempt"):
            raise ValueError("Archive export classification does not match the final owner input")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", action="store_true")
    parser.add_argument("--from-environment", action="store_true")
    for field in FIELDS:
        parser.add_argument("--" + field.lower().replace("_", "-"))
    args = parser.parse_args()
    config = ReleaseConfig.from_environment(args.store, os.environ if args.from_environment else {})
    values = dict(config.values)
    for field in FIELDS:
        value = getattr(args, field.lower())
        if value is not None:
            values[field] = value
    try:
        ReleaseConfig(values, args.store).validate()
    except ValueError as error:
        print("FAIL iOS release configuration:\n" + str(error), file=sys.stderr)
        return 2
    print("PASS iOS " + ("store" if args.store else "development") + " metadata syntax; ownership, URL availability, export assessment and signing are not verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
