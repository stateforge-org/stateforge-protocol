"""Tests for the independent SFP consumer ownership audit."""

import json
from pathlib import Path

import pytest
from scripts.ci import audit_consumer


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

    assert audit_consumer.audit(source) == []


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

    messages = {finding.message for finding in audit_consumer.audit(source)}
    assert messages == {
        "consumer imports private Protocol validation",
        "consumer redeclares Protocol-owned SERVICE_NAME",
        "consumer copies a Protocol-owned service identity",
        "bootstrap uses generated bindings without its contract",
        "bootstrap uses generated bindings without public validation",
    }


@pytest.mark.parametrize(
    "statement",
    [
        (
            "from stateforge_protocol.sfp.bootstrap.v1.bootstrap_pb2 "
            "import HandshakeRequest"
        ),
        "import stateforge_protocol.sfp.bootstrap.v1.bootstrap_pb2 as wire",
    ],
)
def test_generated_binding_import_forms_require_public_apis(
    tmp_path: Path,
    statement: str,
) -> None:
    source = tmp_path / "consumer"
    _write(source / "client.py", statement)

    messages = {finding.message for finding in audit_consumer.audit(source)}

    assert messages == {
        "bootstrap uses generated bindings without its contract",
        "bootstrap uses generated bindings without public validation",
    }


def test_rejects_direct_private_validation_import(tmp_path: Path) -> None:
    source = tmp_path / "consumer"
    _write(
        source / "client.py",
        "import stateforge_protocol.sfp._validation as helpers",
    )

    findings = audit_consumer.audit(source)

    assert [finding.message for finding in findings] == [
        "consumer imports private Protocol validation"
    ]


def test_rejects_a_missing_source_tree(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source directory"):
        audit_consumer.audit(tmp_path / "missing")


def test_cli_writes_success_and_failure_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "consumer"
    output = tmp_path / "evidence" / "ownership.json"
    _write(
        source / "client.py",
        "from stateforge_protocol.sfp.bootstrap.v1 import contract",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "audit_consumer.py",
            "--source",
            str(source),
            "--output",
            str(output),
        ],
    )

    assert audit_consumer.main() == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "findings": [],
        "pythonFileCount": 1,
        "source": str(source),
    }

    _write(source / "client.py", "MAX_REQUEST_BYTES = 1")
    assert audit_consumer.main() == 1
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["findings"][0]["message"] == (
        "consumer redeclares Protocol-owned MAX_REQUEST_BYTES"
    )
