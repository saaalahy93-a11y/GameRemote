"""Reproduce the offline Android notices from reviewed, hash-pinned texts."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CATALOG = Path("LICENSES/android/catalog.json")
ASSET = Path("assets/legal/android-notices.txt")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_notice(root: Path, notice: dict) -> str:
    relative = Path(notice["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Notice path must stay within the source checkout")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Notice symlink escapes the source checkout")
    data = path.read_bytes()
    if digest(data) != notice["sha256"]:
        raise ValueError(f"Notice changed: {relative}")
    return data.decode("utf-8")


def render(root: Path, catalog: dict) -> bytes:
    if catalog.get("schema_version") != 1:
        raise ValueError("Unsupported Android notices catalogue")
    for source_input in catalog.get("source_inputs", []):
        local_notice(root, source_input)
    parts = [catalog["introduction"].rstrip() + "\n"]
    identifiers = set()
    for component in catalog["components"]:
        identifier = component["id"]
        if identifier in identifiers:
            raise ValueError(f"Duplicate component: {identifier}")
        identifiers.add(identifier)
        parts.append("\n" + "=" * 64 + "\n" + component["title"] + "\n")
        for reference in component.get("source_references", []):
            parts.append("Source: " + reference + "\n")
        if component.get("description"):
            parts.append(component["description"] + "\n")
        for notice in component["notices"]:
            # Keep the exact text, including its original whitespace and
            # copyright notices; separators are added outside the text.
            parts.append("\n" + local_notice(root, notice) + "\n")
    seen_artifacts = set()
    for artifact in catalog["artifacts"]:
        key = (artifact["coordinate"], artifact["extension"])
        if key in seen_artifacts:
            raise ValueError(f"Duplicate artifact: {key}")
        seen_artifacts.add(key)
        if artifact["component_id"] not in identifiers:
            raise ValueError(f"Missing notices for {artifact['coordinate']}")
    if not seen_artifacts:
        raise ValueError("Android runtime artifact inventory is empty")
    return "".join(parts).encode("utf-8")


def verify_inventory(catalog: dict, inventory: dict) -> None:
    """Check the independently resolved graph, not a declared dependency list."""
    expected = {
        (a["coordinate"], a["extension"]): a["sha256"]
        for a in catalog["artifacts"]
    }
    actual = {}
    for artifact in inventory["artifacts"]:
        key = (artifact["coordinate"], artifact["extension"])
        if key in actual:
            raise ValueError(f"Duplicate resolved artifact: {key}")
        actual[key] = artifact["sha256"]
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        added = sorted(set(actual) - set(expected))
        changed = sorted(k for k in actual.keys() & expected.keys() if actual[k] != expected[k])
        raise ValueError(f"Android notice inventory is stale: missing={missing}, added={added}, changed={changed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="Verify without writing")
    parser.add_argument("--inventory", type=Path, help="Independently resolved dependency inventory JSON")
    args = parser.parse_args()
    catalog = json.loads((args.root / CATALOG).read_text(encoding="utf-8"))
    content = render(args.root, catalog)
    if args.inventory:
        verify_inventory(catalog, json.loads(args.inventory.read_text(encoding="utf-8")))
    if digest(content) != catalog["asset_sha256"]:
        raise ValueError("Generated notices differ from the reviewed catalogue digest")
    path = args.root / ASSET
    if args.check:
        if path.read_bytes() != content:
            raise ValueError("Packaged notice asset is stale; regenerate it")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print(f"Android notices verified: {len(catalog['artifacts'])} runtime artifacts, {len(catalog['components'])} sections, {len(content)} bytes")


if __name__ == "__main__":
    main()
