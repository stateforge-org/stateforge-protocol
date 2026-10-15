"""Tests for the endpoint-discovery descriptor v1 contract."""

import json
from pathlib import Path
from uuid import UUID

import jsonschema
import pytest

from stateforge_protocol.sfp.endpoint_discovery.v1 import contract

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
        ("schema_version", "2"),
        ("provider_instance_id", "not-a-uuid"),
        ("provider_instance_id", str(_PROVIDER_INSTANCE_ID).upper()),
        ("endpoint_generation", True),
        ("endpoint_generation", 0),
        ("endpoint_generation", contract.MAX_ENDPOINT_GENERATION + 1),
        ("transport", {"type": "tcp", "socket_path": _SOCKET_PATH}),
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
