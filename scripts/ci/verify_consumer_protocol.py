"""Verify that a consumer kept the exact built Protocol wheel installed."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

_DISTRIBUTION = "stateforge-protocol"


def _sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _direct_url_hash(document: dict[str, Any]) -> str | None:
    """Read the standardized archive SHA-256 from direct_url metadata."""
    archive_info = document.get("archive_info")
    if not isinstance(archive_info, dict):
        return None
    hashes = archive_info.get("hashes")
    if isinstance(hashes, dict) and isinstance(hashes.get("sha256"), str):
        return hashes["sha256"]
    legacy_hash = archive_info.get("hash")
    if isinstance(legacy_hash, str) and legacy_hash.startswith("sha256="):
        return legacy_hash.removeprefix("sha256=")
    return None


def verify_direct_url(document: dict[str, Any], wheel: Path) -> dict[str, str]:
    """Match installed direct-url metadata to one exact local wheel."""
    url = document.get("url")
    if not isinstance(url, str):
        raise ValueError("Installed Protocol direct URL is missing")
    parsed = urlparse(url)
    if parsed.scheme != "file":
        raise ValueError("Installed Protocol did not originate from a file")
    installed_from = Path(unquote(parsed.path)).resolve()
    expected_wheel = wheel.resolve()
    if installed_from != expected_wheel:
        raise ValueError(
            "Installed Protocol does not match the expected wheel"
        )

    expected_sha256 = _sha256(expected_wheel)
    installed_sha256 = _direct_url_hash(document)
    if installed_sha256 != expected_sha256:
        raise ValueError("Installed Protocol wheel hash does not match")
    return {
        "wheel": str(expected_wheel),
        "wheelSha256": expected_sha256,
        "directUrl": url,
    }


def verify(wheel: Path) -> dict[str, str]:
    """Verify the installed distribution and return evidence."""
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError("Expected Protocol wheel does not exist")
    try:
        distribution = importlib.metadata.distribution(_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError as error:
        raise ValueError(
            "Installed Protocol distribution does not exist"
        ) from error
    raw_direct_url = distribution.read_text("direct_url.json")
    if raw_direct_url is None:
        raise ValueError("Installed Protocol has no direct_url.json evidence")
    document = json.loads(raw_direct_url)
    if not isinstance(document, dict):
        raise ValueError("Installed Protocol direct URL metadata is invalid")
    result = verify_direct_url(document, wheel)
    result.update(
        {
            "distribution": _DISTRIBUTION,
            "version": distribution.version,
        }
    )
    return result


def main() -> int:
    """Run exact-wheel verification and write machine-readable evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        result = verify(arguments.wheel)
    except (json.JSONDecodeError, OSError, ValueError) as error:
        raise SystemExit(
            f"Protocol wheel verification failed: {error}"
        ) from error
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main().
    raise SystemExit(main())
