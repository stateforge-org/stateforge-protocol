"""Tests for the endpoint-discovery descriptor v1 contract."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import jsonschema
import pytest
import yaml
from tests.documentation import annotated_json_example

from stateforge_protocol.sfp.endpoint_discovery.v1 import contract

_ROOT = Path(__file__).resolve().parents[1]
_PROVIDER_INSTANCE_ID = UUID("7f7db7d8-68b4-4f71-9769-065b5c4f941c")
_SOCKET_PATH = (
    "/run/stateforge-agent/providers/"
    "7f7db7d8-68b4-4f71-9769-065b5c4f941c.4.sock"
)


def _descriptor() -> contract.EndpointDescriptor:
    return contract.EndpointDescriptor(
        provider_instance_id=_PROVIDER_INSTANCE_ID,
        endpoint_generation=4,
        socket_path=_SOCKET_PATH,
    )


def test_round_trips_the_canonical_descriptor() -> None:
    descriptor = _descriptor()
    content = descriptor.to_json_bytes()

    assert contract.parse_descriptor(content) == descriptor
    assert len(content) <= contract.MAX_DESCRIPTOR_BYTES
    assert contract.descriptor_filename(_PROVIDER_INSTANCE_ID) == (
        f"{_PROVIDER_INSTANCE_ID}.sfp.json"
    )
    assert contract.socket_filename(_PROVIDER_INSTANCE_ID, 4) == (
        f"{_PROVIDER_INSTANCE_ID}.4.sock"
    )
    assert (
        contract.provider_instance_id_from_descriptor_filename(
            f"{_PROVIDER_INSTANCE_ID}.sfp.json"
        )
        == _PROVIDER_INSTANCE_ID
    )


def test_canonical_document_matches_packaged_json_schema() -> None:
    schema_path = Path(contract.__file__).with_name(
        "endpoint_descriptor.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_descriptor().as_document(), schema)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", None),
        ("schema_version", "2"),
        ("provider_instance_id", 1),
        ("provider_instance_id", "not-a-uuid"),
        ("provider_instance_id", str(_PROVIDER_INSTANCE_ID).upper()),
        ("endpoint_generation", True),
        ("endpoint_generation", 0),
        ("endpoint_generation", contract.MAX_ENDPOINT_GENERATION + 1),
        ("transport", {"type": "tcp", "socket_path": _SOCKET_PATH}),
        ("transport", {"type": "unix", "socket_path": 1}),
        ("transport", {"type": "unix", "socket_path": "relative.sock"}),
    ],
)
def test_rejects_values_outside_descriptor_v1(
    field: str,
    value: object,
) -> None:
    document = _descriptor().as_document()
    document[field] = value

    with pytest.raises(contract.EndpointDescriptorContractError):
        contract.parse_descriptor(json.dumps(document).encode())


@pytest.mark.parametrize("change", ["missing", "unknown", "duplicate"])
def test_rejects_ambiguous_descriptor_shapes(change: str) -> None:
    document = _descriptor().as_document()
    if change == "missing":
        del document["transport"]
        content = json.dumps(document).encode()
    elif change == "unknown":
        document["unexpected"] = True
        content = json.dumps(document).encode()
    else:
        content = (
            b'{"schema_version":"1","schema_version":"1",'
            b'"provider_instance_id":"'
            + str(_PROVIDER_INSTANCE_ID).encode()
            + b'","endpoint_generation":4,"transport":{"type":"unix",'
            b'"socket_path":"' + _SOCKET_PATH.encode() + b'"}}'
        )

    with pytest.raises(contract.EndpointDescriptorContractError):
        contract.parse_descriptor(content)


def test_rejects_oversized_descriptor_before_parsing() -> None:
    with pytest.raises(
        contract.EndpointDescriptorContractError,
        match="exceeds",
    ):
        contract.parse_descriptor(b"x" * (contract.MAX_DESCRIPTOR_BYTES + 1))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2"),
        (
            "provider_instance_id",
            UUID("00000000-0000-1000-8000-000000000000"),
        ),
        ("endpoint_generation", 0),
        ("endpoint_generation", True),
        ("socket_path", ""),
        ("socket_path", "relative.sock"),
        ("socket_path", "/run/provider\x00.sock"),
    ],
)
def test_direct_descriptor_construction_enforces_the_contract(
    field: str,
    value: object,
) -> None:
    values: dict[str, Any] = {
        "provider_instance_id": _PROVIDER_INSTANCE_ID,
        "endpoint_generation": 4,
        "socket_path": _SOCKET_PATH,
        "schema_version": contract.SCHEMA_VERSION,
    }
    values[field] = value

    with pytest.raises(contract.EndpointDescriptorContractError):
        contract.EndpointDescriptor(**values)


def test_descriptor_serialization_enforces_the_byte_limit() -> None:
    descriptor = contract.EndpointDescriptor(
        provider_instance_id=_PROVIDER_INSTANCE_ID,
        endpoint_generation=4,
        socket_path="/" + ("x" * contract.MAX_DESCRIPTOR_BYTES),
    )

    with pytest.raises(
        contract.EndpointDescriptorContractError, match="exceeds"
    ):
        descriptor.to_json_bytes()


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not-json",
        b"[]",
        (
            b'{"schema_version":"1","provider_instance_id":"'
            + str(_PROVIDER_INSTANCE_ID).encode()
            + b'","endpoint_generation":4,"transport":[]}'
        ),
    ],
)
def test_rejects_unparseable_descriptor_documents(content: bytes) -> None:
    with pytest.raises(contract.EndpointDescriptorContractError):
        contract.parse_descriptor(content)


def test_descriptor_naming_rejects_invalid_identity_and_generation() -> None:
    invalid_id = UUID("00000000-0000-1000-8000-000000000000")

    with pytest.raises(contract.EndpointDescriptorContractError):
        contract.descriptor_filename(invalid_id)
    with pytest.raises(contract.EndpointDescriptorContractError):
        contract.socket_filename(_PROVIDER_INSTANCE_ID, 0)
    with pytest.raises(contract.EndpointDescriptorContractError):
        contract.provider_instance_id_from_descriptor_filename("provider.json")
    with pytest.raises(contract.EndpointDescriptorContractError):
        contract.provider_instance_id_from_descriptor_filename(
            f"{str(_PROVIDER_INSTANCE_ID).upper()}.sfp.json"
        )


def test_endpoint_discovery_walkthrough_covers_every_documented_scenario() -> (
    None
):
    declaration = yaml.safe_load(
        (
            _ROOT
            / "docs"
            / "v0.1.0"
            / "procedures"
            / "endpoint-discovery.yaml"
        ).read_text(encoding="utf-8")
    )
    expected_markers = {
        "success": "provisional channel",
        "invalid-descriptor": "EndpointDescriptorContractError",
        "unsafe-boundary": "Valid JSON is not sufficient",
        "replacement": "fresh Bootstrap session",
        "stale-generation": "never move backward",
    }

    assert set(declaration["scenarios"]) == set(expected_markers)
    for scenario_id, marker in expected_markers.items():
        serialized = json.dumps(declaration["scenarios"][scenario_id])
        assert marker in serialized


def test_endpoint_discovery_documentation_identifies_contract_sources() -> (
    None
):
    documentation = (
        _ROOT / "docs" / "v0.1.0" / "procedures" / "endpoint-discovery.md"
    ).read_text(encoding="utf-8")

    assert "endpoint_discovery/v1/contract.py" in documentation
    assert "endpoint_descriptor.schema.json" in documentation
    assert "has no separate `validation.py`" in documentation


def test_documented_endpoint_descriptor_matches_the_contract() -> None:
    documentation = (
        _ROOT / "docs" / "v0.1.0" / "procedures" / "endpoint-discovery.md"
    ).read_text(encoding="utf-8")
    example = annotated_json_example(
        documentation,
        title="Endpoint descriptor",
    )
    schema = json.loads(
        Path(contract.__file__)
        .with_name("endpoint_descriptor.schema.json")
        .read_text(encoding="utf-8")
    )

    jsonschema.validate(example, schema)
    assert contract.parse_descriptor(json.dumps(example).encode()) == (
        _descriptor()
    )
