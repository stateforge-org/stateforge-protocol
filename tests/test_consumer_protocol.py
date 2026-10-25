"""Tests for exact Protocol wheel identity verification."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.ci import verify_consumer_protocol


class _Distribution:
    """Supply installed distribution metadata to the verifier."""

    version = "0.1.0"

    def __init__(self, direct_url: str | None) -> None:
        self._direct_url = direct_url

    def read_text(self, filename: str) -> str | None:
        assert filename == "direct_url.json"
        return self._direct_url


def _document(wheel: Path, digest: str) -> dict[str, object]:
    return {
        "archive_info": {"hashes": {"sha256": digest}},
        "url": wheel.resolve().as_uri(),
    }


def test_accepts_matching_local_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()

    result = verify_consumer_protocol.verify_direct_url(
        _document(wheel, digest), wheel
    )

    assert result["wheel"] == str(wheel.resolve())
    assert result["wheelSha256"] == digest


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"url": None}, "missing"),
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
        verify_consumer_protocol.verify_direct_url(document, wheel)


def test_rejects_mismatched_wheel_hash(tmp_path: Path) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")

    with pytest.raises(ValueError, match="hash"):
        verify_consumer_protocol.verify_direct_url(
            _document(wheel, "0" * 64), wheel
        )


def test_accepts_pep_610_single_archive_hash(tmp_path: Path) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    document = {
        "archive_info": {"hash": f"sha256={digest}"},
        "url": wheel.resolve().as_uri(),
    }

    result = verify_consumer_protocol.verify_direct_url(document, wheel)

    assert result["wheelSha256"] == digest


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"archive_info": "invalid"},
        {"archive_info": {"hash": "md5=unsupported"}},
    ],
)
def test_rejects_missing_sha256_metadata(
    tmp_path: Path,
    document: dict[str, Any],
) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")
    document["url"] = wheel.resolve().as_uri()

    with pytest.raises(ValueError, match="hash"):
        verify_consumer_protocol.verify_direct_url(document, wheel)


def test_verify_reads_installed_distribution_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    direct_url = json.dumps(_document(wheel, digest))
    monkeypatch.setattr(
        verify_consumer_protocol.importlib.metadata,
        "distribution",
        lambda name: _Distribution(direct_url),
    )

    result = verify_consumer_protocol.verify(wheel)

    assert result["distribution"] == "stateforge-protocol"
    assert result["version"] == "0.1.0"


@pytest.mark.parametrize("filename", ["missing.whl", "protocol.tar.gz"])
def test_verify_requires_an_existing_wheel(
    tmp_path: Path,
    filename: str,
) -> None:
    artifact = tmp_path / filename
    if artifact.suffix != ".whl":
        artifact.write_bytes(b"not-a-wheel")

    with pytest.raises(ValueError, match="wheel"):
        verify_consumer_protocol.verify(artifact)


@pytest.mark.parametrize("direct_url", [None, "[]"])
def test_verify_rejects_missing_or_invalid_direct_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    direct_url: str | None,
) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")
    monkeypatch.setattr(
        verify_consumer_protocol.importlib.metadata,
        "distribution",
        lambda name: _Distribution(direct_url),
    )

    with pytest.raises(ValueError, match=r"direct_url|metadata"):
        verify_consumer_protocol.verify(wheel)


def test_verify_translates_missing_distribution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"exact-wheel")

    def missing(name: str) -> None:
        raise verify_consumer_protocol.importlib.metadata.PackageNotFoundError(
            name
        )

    monkeypatch.setattr(
        verify_consumer_protocol.importlib.metadata,
        "distribution",
        missing,
    )

    with pytest.raises(ValueError, match="distribution"):
        verify_consumer_protocol.verify(wheel)


def test_cli_writes_machine_readable_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = tmp_path / "stateforge_protocol-0.1.0-py3-none-any.whl"
    output = tmp_path / "evidence" / "protocol.json"
    monkeypatch.setattr(
        verify_consumer_protocol,
        "verify",
        lambda artifact: {
            "distribution": "stateforge-protocol",
            "version": "0.1.0",
            "wheel": str(artifact),
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_consumer_protocol.py",
            "--wheel",
            str(wheel),
            "--output",
            str(output),
        ],
    )

    assert verify_consumer_protocol.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["version"] == (
        "0.1.0"
    )
    assert json.loads(capsys.readouterr().out)["distribution"] == (
        "stateforge-protocol"
    )


def test_cli_reports_verification_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        verify_consumer_protocol,
        "verify",
        lambda artifact: (_ for _ in ()).throw(ValueError("wrong wheel")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_consumer_protocol.py",
            "--wheel",
            str(tmp_path / "missing.whl"),
            "--output",
            str(tmp_path / "output.json"),
        ],
    )

    with pytest.raises(SystemExit, match="wrong wheel"):
        verify_consumer_protocol.main()
