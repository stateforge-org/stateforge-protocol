"""Check generated contract freshness without modifying the working tree."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_GENERATED_SUFFIXES = (
    "_pb2.py",
    "_pb2.pyi",
    "_pb2_grpc.py",
    "_pb2_grpc.pyi",
)


def _generated_files(root: Path) -> dict[Path, bytes]:
    """Return generated files below ``root`` keyed by relative path."""
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and path.name.endswith(_GENERATED_SUFFIXES)
    }


def _report_mismatches(
    left: dict[Path, bytes],
    right: dict[Path, bytes],
    message: str,
) -> bool:
    """Report differing paths and return whether any mismatch was found."""
    mismatches = sorted(
        path
        for path in left.keys() | right.keys()
        if left.get(path) != right.get(path)
    )
    for path in mismatches:
        sys.stderr.write(f"{message}: src/{path}\n")
    return bool(mismatches)


def main() -> int:
    """Check deterministic generation and committed-file freshness."""
    buf = shutil.which("buf")
    if buf is None:
        sys.stderr.write("Install Buf and add it to PATH before checking.\n")
        return 1

    environment = os.environ.copy()
    scripts_directory = sysconfig.get_path("scripts")
    environment["PATH"] = os.pathsep.join(
        (scripts_directory, environment.get("PATH", ""))
    )

    with (
        tempfile.TemporaryDirectory(prefix="stateforge-contracts-a-") as tmp_a,
        tempfile.TemporaryDirectory(prefix="stateforge-contracts-b-") as tmp_b,
    ):
        for output in (tmp_a, tmp_b):
            subprocess.run(  # noqa: S603 - fixed command, resolved local tool
                [buf, "generate", "--output", output],
                cwd=_ROOT,
                env=environment,
                check=True,
            )

        expected_root = Path(tmp_a) / "src"
        repeated_root = Path(tmp_b) / "src"
        current_root = _ROOT / "src"
        expected = _generated_files(expected_root)
        repeated = _generated_files(repeated_root)
        current = _generated_files(current_root)
        if not expected:
            sys.stderr.write("Buf generated no contract modules.\n")
            return 1
        if _report_mismatches(
            expected,
            repeated,
            "Contract generation is not deterministic",
        ):
            return 1
        if _report_mismatches(
            expected,
            current,
            "Generated contract differs",
        ):
            return 1
    sys.stdout.write("Generated contracts are deterministic and current.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
