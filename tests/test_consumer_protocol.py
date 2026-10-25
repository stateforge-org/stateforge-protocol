"""Tests for exact Protocol wheel identity verification."""

import hashlib
from pathlib import Path

import pytest
from scripts.ci.verify_consumer_protocol import verify_direct_url


def _document(wheel: Path, digest: str) -> dict[str, object]:
    return {
        "archive_info": {"hashes": {"sha256": digest}},
        "url": wheel.resolve().as_uri(),
    }


def test_accepts_matching_local_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()

    result = verify_direct_url(_document(wheel, digest), wheel)

    assert result["wheel"] == str(wheel.resolve())
    assert result["wheelSha256"] == digest


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"url": "https://example.test/protocol.whl"}, "file"),
        (
            {
                "archive_info": {"hashes": {"sha256": "0" * 64}},
                "url": "file:///different/protocol.whl",
            },
            "expected wheel",
        ),
    ],
)
def test_rejects_non_exact_installation(
    tmp_path: Path,
    document: dict[str, object],
    message: str,
) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")

    with pytest.raises(ValueError, match=message):
        verify_direct_url(document, wheel)


def test_rejects_mismatched_wheel_hash(tmp_path: Path) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")

    with pytest.raises(ValueError, match="hash"):
        verify_direct_url(_document(wheel, "0" * 64), wheel)
