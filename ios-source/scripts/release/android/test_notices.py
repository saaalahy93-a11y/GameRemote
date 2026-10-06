"""Notice changes and graph drift must not produce a release silently."""

import copy
import tempfile
import unittest
from pathlib import Path

from generate_notices import digest, local_notice, render, verify_inventory


class NoticeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.original = b"Copyright Example\r\nAll rights retained.\n"
        (self.root / "LICENSE.txt").write_bytes(self.original)
        self.notice = {"path": "LICENSE.txt", "sha256": digest(self.original)}
        self.artifact = {"coordinate": "example:library:1", "extension": "jar", "sha256": "a" * 64, "component_id": "example"}
        self.catalog = {
            "schema_version": 1, "introduction": "Notices", "artifacts": [self.artifact],
            "components": [{"id": "example", "title": "Example", "notices": [self.notice]}],
        }

    def test_exact_notice_bytes_and_runtime_graph(self):
        self.assertIn(self.original, render(self.root, self.catalog))
        verify_inventory(self.catalog, {"artifacts": [self.artifact]})

    def test_changed_notice_is_rejected(self):
        (self.root / "LICENSE.txt").write_bytes(self.original + b"altered")
        with self.assertRaisesRegex(ValueError, "Notice changed"):
            render(self.root, self.catalog)

    def test_missing_component_is_rejected(self):
        self.catalog["artifacts"][0]["component_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "Missing notices"):
            render(self.root, self.catalog)

    def test_changed_native_source_recipe_requires_review(self):
        recipe = b"pinned source archive and version\n"
        (self.root / "Native.cmake").write_bytes(recipe)
        self.catalog["source_inputs"] = [{"path": "Native.cmake", "sha256": digest(recipe)}]
        render(self.root, self.catalog)
        (self.root / "Native.cmake").write_bytes(b"different archive/version\n")
        with self.assertRaisesRegex(ValueError, "Notice changed: Native.cmake"):
            render(self.root, self.catalog)

    def test_duplicate_artifact_is_rejected(self):
        self.catalog["artifacts"].append(copy.deepcopy(self.artifact))
        with self.assertRaisesRegex(ValueError, "Duplicate artifact"):
            render(self.root, self.catalog)

    def test_changed_added_and_removed_dependency_are_rejected(self):
        changed = dict(self.artifact, sha256="b" * 64)
        added = dict(self.artifact, coordinate="example:new:2")
        for artifacts in ([changed], [self.artifact, added], []):
            with self.subTest(artifacts=artifacts), self.assertRaisesRegex(ValueError, "inventory is stale"):
                verify_inventory(self.catalog, {"artifacts": artifacts})

    def test_duplicate_resolved_dependency_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate resolved"):
            verify_inventory(self.catalog, {"artifacts": [self.artifact, self.artifact]})

    def test_absolute_and_traversal_paths_are_rejected(self):
        for path in ("../LICENSE.txt", str(self.root / "LICENSE.txt")):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "within the source"):
                local_notice(self.root, dict(self.notice, path=path))

    def test_symlink_outside_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            other = Path(external) / "notice.txt"
            other.write_bytes(self.original)
            (self.root / "escape.txt").symlink_to(other)
            with self.assertRaisesRegex(ValueError, "symlink escapes"):
                local_notice(self.root, dict(self.notice, path="escape.txt"))


if __name__ == "__main__":
    unittest.main()
