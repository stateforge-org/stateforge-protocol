"""Verify the installed StateForge Protocol wheel outside its checkout."""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import sys
from importlib import metadata
from pathlib import Path

_DISTRIBUTION = "stateforge-protocol"


def _is_within(path: Path, parent: Path) -> bool:
    """Return whether ``path`` is contained below ``parent``."""
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def verify(expected_version: str, workspace: Path | None) -> dict[str, object]:
    """Verify package metadata, imports, schemas, fixtures, and isolation."""
    distribution = metadata.distribution(_DISTRIBUTION)
    if distribution.version != expected_version:
        msg = (
            f"Expected {_DISTRIBUTION} {expected_version}, "
            f"found {distribution.version}"
        )
        raise ValueError(msg)
    package_root = Path(
        distribution.locate_file("stateforge_protocol")
    ).resolve()
    if not package_root.is_dir():
        raise ValueError(
            f"Installed package directory is missing: {package_root}"
        )
    if workspace is not None and _is_within(package_root, workspace.resolve()):
        raise ValueError("Package imported from the repository checkout")
    if not (package_root / "py.typed").is_file():
        raise ValueError("Installed package does not contain py.typed")

    module_names = sorted(
        module.name
        for module in pkgutil.walk_packages(
            [str(package_root)], prefix="stateforge_protocol."
        )
        if module.name.endswith(("_pb2", "_pb2_grpc"))
    )
    if not module_names:
        raise ValueError("Installed package contains no generated modules")
    for module_name in module_names:
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__ or "").resolve()
        if not _is_within(module_path, package_root):
            raise ValueError(
                f"Module did not load from the installed wheel: {module_name}"
            )

    schemas = sorted(package_root.rglob("*.schema.json"))
    if not schemas:
        raise ValueError("Installed package contains no validation schemas")
    for schema in schemas:
        json.loads(schema.read_text(encoding="utf-8"))

    fixture_root = package_root / "fixtures"
    fixture_files = sorted(fixture_root.rglob("*.json"))
    if not fixture_files:
        raise ValueError("Installed package contains no conformance fixtures")
    for fixture in fixture_files:
        json.loads(fixture.read_text(encoding="utf-8"))

    return {
        "distribution": _DISTRIBUTION,
        "version": distribution.version,
        "package_root": str(package_root),
        "generated_module_count": len(module_names),
        "schema_count": len(schemas),
        "fixture_count": len(fixture_files),
    }


def main() -> int:
    """Run installed-package verification from command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--workspace", type=Path)
    arguments = parser.parse_args()
    try:
        result = verify(arguments.expected_version, arguments.workspace)
    except (ImportError, OSError, ValueError, json.JSONDecodeError) as error:
        sys.stderr.write(f"Installed-package verification failed: {error}\n")
        return 1
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
