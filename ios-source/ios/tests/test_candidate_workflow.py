#!/usr/bin/env python3
"""Exercise the actual selector and source-diff command without booting a simulator."""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SimulatorSelectionTests(unittest.TestCase):
    def select(self, wanted, available=("iphone", "ipad")):
        script = (ROOT / "ios/scripts/simulator-smoke.sh").read_text()
        match = re.search(r"^SMOKE_IOS_VERSION=.*?<<'PY'.*?\n(.*?)^PY$", script, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match, "Actual simulator selector was not found")
        prefix = "com.apple.CoreSimulator.SimDeviceType."
        models = {
            "iphone": ("iPhone 17 Pro", prefix + "iPhone-17-Pro"),
            "ipad": ("iPad Pro 13-inch (M5)", prefix + "iPad-Pro-13-inch-M5-8GB"),
            "ipad_11": ("iPad Pro 11-inch (M5)", prefix + "iPad-Pro-11-inch-M5-8GB"),
            "ipad_air": ("iPad Air 13-inch (M3)", prefix + "iPad-Air-13-inch-M3"),
            "ipad_renamed": ("iPad Pro 13-inch (M5)", prefix + "iPad-Pro-11-inch-M5-8GB"),
            "ipad_no_type": ("iPad Pro 13-inch (M5)", ""),
        }
        devices = {"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-26-2": [
            {"name": models[kind][0], "deviceTypeIdentifier": models[kind][1],
             "udid": kind, "isAvailable": True, "state": "Shutdown"}
            for kind in available
        ]}}
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "devices.json"
            fixture.write_text(json.dumps(devices))
            env = dict(os.environ, SMOKE_DEVICE_KIND=wanted, SMOKE_IOS_VERSION="26.2")
            return subprocess.run([sys.executable, "-c", match.group(1), str(fixture)],
                                  env=env, capture_output=True, text=True, check=False)

    def test_default_requires_both_families(self):
        result = self.select("")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row.split("\t")[0] for row in result.stdout.splitlines()], ["iphone", "ipad"])
        self.assertNotEqual(self.select("", ("iphone",)).returncode, 0)

    def test_single_family_does_not_require_the_other(self):
        for kind in ("iphone", "ipad"):
            with self.subTest(kind=kind):
                result = self.select(kind, (kind,))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([row.split("\t")[0] for row in result.stdout.splitlines()], [kind])

    def test_missing_or_invalid_selection_fails(self):
        self.assertNotEqual(self.select("ipad", ("iphone",)).returncode, 0)
        self.assertNotEqual(self.select("invalid").returncode, 0)
        self.assertNotEqual(self.select("iphone", ()).returncode, 0)

    def test_ipad_requires_authentic_13_inch_capture_device(self):
        self.assertNotEqual(self.select("ipad", ("ipad_11",)).returncode, 0)
        result = self.select("ipad", ("ipad_11", "ipad_air", "ipad"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("iPad Pro 13-inch (M5)", result.stdout)
        self.assertNotIn("11-inch", result.stdout)

    def test_13_inch_air_is_valid_when_no_pro_is_available(self):
        result = self.select("ipad", ("ipad_air",))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("iPad Air 13-inch (M3)", result.stdout)

    def test_display_name_cannot_forge_13_inch_hardware(self):
        for model in ("ipad_renamed", "ipad_no_type"):
            with self.subTest(model=model):
                self.assertNotEqual(self.select("ipad", (model,)).returncode, 0)


class ProductionSourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "-q")
        self.write("ios/App/Example.swift", "original app\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), "-c", "core.hooksPath=/dev/null",
                               "-c", "commit.gpgsign=false", "-c", "user.name=Fixture",
                               "-c", "user.email=fixture@example.invalid", *args],
                              capture_output=True, text=True, check=True)

    def write(self, path, text):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text)

    def guard(self):
        workflow = (ROOT / ".github/workflows/ios-candidate-checks.yml").read_text()
        lines = iter(workflow.splitlines())
        first = next((line for line in lines if line.strip().startswith("git diff --exit-code ")), None)
        self.assertIsNotNone(first, "Actual source-diff command was not found")
        command = [first]
        while command[-1].rstrip().endswith("\\"):
            command[-1] = command[-1].rstrip()[:-1]
            command.append(next(lines))
        args = shlex.split(" ".join(command))
        self.assertIn("$SOURCE_COMMIT", args)
        args = [self.base if arg == "$SOURCE_COMMIT" else arg for arg in args]
        return subprocess.run([args[0], "-C", str(self.root), *args[1:]],
                              capture_output=True, text=True, check=False)

    def test_verification_and_release_record_changes_are_allowed(self):
        for path in (".github/workflows/ios-candidate-checks.yml", "ios/scripts/simulator-smoke.sh",
                     "ios/scripts/simulator-ui.sh", "ios/tests/example.py", "ios/VALIDATION.md",
                     "docs/release/ios.md"):
            self.write(path, "verification-only change\n")
        self.git("add", ".")
        self.git("commit", "-qm", "verification fixtures")
        result = self.guard()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_production_changes_are_rejected(self):
        for path in ("ios/App/Example.swift", "ios/App/Assets.xcassets/icon.png",
                     "ios/Bridge/GameRemoteBridge.c", "ios/CMakeLists.txt", "CMakeLists.txt",
                     "ios/scripts/build.sh", "lib/src/session.c", "third-party/new-source.c"):
            with self.subTest(path=path):
                self.write(path, "changed production input\n")
                self.git("add", ".")
                self.git("commit", "-qm", "changed production fixture")
                self.assertEqual(self.guard().returncode, 1)
                # Only this disposable fixture repository is reset between cases.
                self.git("reset", "--hard", self.base)

    def test_dependency_gitlinks_are_rejected(self):
        self.git("update-index", "--add", "--cacheinfo", f"160000,{self.base},third-party/curl")
        self.git("commit", "-qm", "changed dependency fixture")
        self.assertEqual(self.guard().returncode, 1)


class ArtifactProvenanceTests(unittest.TestCase):
    def verify(self, producer_run, source, current_source, producer_source):
        workflow = (ROOT / ".github/workflows/ios-candidate-checks.yml").read_text()
        step = workflow.split("      - name: Verify simulator artifact provenance\n", 1)[1]
        step = step.split("      - name: ", 1)[0]
        command = textwrap.dedent(step.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            gh = Path(directory) / "gh"
            gh.write_text(textwrap.dedent('''\
                #!/bin/sh
                [ "$#" -eq 4 ] || exit 20
                [ "$1" = api ] && [ "$2" = "$FIXTURE_API_PATH" ] || exit 20
                [ "$3" = --jq ] && [ "$4" = .head_sha ] || exit 20
                [ -n "$FIXTURE_PRODUCER_SHA" ] || exit 19
                printf "%s\\n" "$FIXTURE_PRODUCER_SHA"
                '''))
            gh.chmod(0o755)
            env = dict(os.environ, PATH=f"{directory}:/usr/bin:/bin",
                       SIMULATOR_BUILD_RUN=producer_run, GITHUB_RUN_ID="17",
                       SOURCE_COMMIT=source, GITHUB_SHA=current_source,
                       GITHUB_REPOSITORY="fixture/repository",
                       FIXTURE_API_PATH=f"repos/fixture/repository/actions/runs/{producer_run}",
                       FIXTURE_PRODUCER_SHA=producer_source)
            return subprocess.run(["/bin/sh", "-ec", command], env=env,
                                  capture_output=True, text=True, check=False)

    def test_current_run_requires_the_tested_commit_without_api(self):
        self.assertEqual(self.verify("17", "merge-sha", "merge-sha", "").returncode, 0)
        self.assertNotEqual(self.verify("17", "head-sha", "merge-sha", "").returncode, 0)

    def test_other_run_requires_the_producer_head(self):
        self.assertEqual(self.verify("16", "producer", "new-checkout", "producer").returncode, 0)
        self.assertNotEqual(self.verify("16", "producer", "new-checkout", "wrong").returncode, 0)


if __name__ == "__main__":
    unittest.main()
