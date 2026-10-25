"""Tests for the independent SFP consumer ownership audit."""

from pathlib import Path

from scripts.ci.audit_consumer import audit


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_accepts_public_contract_and_validation_imports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "consumer"
    _write(
        source / "client.py",
        """
from stateforge_protocol.sfp.bootstrap.v1 import (
    bootstrap_pb2,
    contract,
    validation,
)

request = bootstrap_pb2.HandshakeRequest()
limit = contract.MAX_REQUEST_BYTES
validation.validate_handshake_request(request)
""",
    )

    assert audit(source) == []


def test_rejects_private_helpers_copied_contracts_and_missing_api(
    tmp_path: Path,
) -> None:
    source = tmp_path / "consumer"
    _write(
        source / "client.py",
        """
from stateforge_protocol.sfp import _validation
from stateforge_protocol.sfp.bootstrap.v1 import bootstrap_pb2

SERVICE_NAME = "stateforge.sfp.bootstrap.v1.BootstrapService"
request = bootstrap_pb2.HandshakeRequest()
""",
    )

    messages = {finding.message for finding in audit(source)}
    assert messages == {
        "consumer imports private Protocol validation",
        "consumer redeclares Protocol-owned SERVICE_NAME",
        "consumer copies a Protocol-owned service identity",
        "bootstrap uses generated bindings without its contract",
        "bootstrap uses generated bindings without public validation",
    }
