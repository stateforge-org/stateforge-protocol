"""Check generated contract freshness without modifying the working tree."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_GENERATED_SUFFIXES = (
    "_pb2.py",
    "_pb2.pyi",
    "_pb2_grpc.py",
    "_pb2_grpc.pyi",
)


def main() -> int:
    """Generate in isolation and report missing, changed, or stale modules."""
    buf = shutil.which("buf")
    if buf is None:
        sys.stderr.write("Install Buf and add it to PATH before checking.\n")
        return 1

    with tempfile.TemporaryDirectory(prefix="stateforge-contracts-") as tmp:
        subprocess.run(  # noqa: S603 - fixed command, resolved local tool
            [buf, "generate", "--output", tmp], cwd=_ROOT, check=True
        )
        expected_root = Path(tmp) / "src"
        current_root = _ROOT / "src"
        expected = {
            path.relative_to(expected_root): path.read_bytes()
            for path in expected_root.rglob("*")
            if path.is_file() and path.name.endswith(_GENERATED_SUFFIXES)
        }
        current = {
            path.relative_to(current_root): path.read_bytes()
            for path in current_root.rglob("*")
            if path.is_file() and path.name.endswith(_GENERATED_SUFFIXES)
        }
        if not expected:
            sys.stderr.write("Buf generated no contract modules.\n")
            return 1
        mismatches = sorted(
            path
            for path in expected.keys() | current.keys()
            if expected.get(path) != current.get(path)
        )
        if mismatches:
            for path in mismatches:
                sys.stderr.write(f"Generated contract differs: src/{path}\n")
            return 1
    sys.stdout.write("Generated contracts are current.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
