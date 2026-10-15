"""Tests for the generated and handwritten SFP Bootstrap v1 contract."""

import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from google.protobuf.message import Message

from stateforge_protocol.sfp import primitives
from stateforge_protocol.sfp.bootstrap.v1 import (
    bootstrap_pb2,
    contract,
    validation,
)

_ROOT = Path(__file__).resolve().parents[1]
_SESSION_SCHEMA_FAMILIES = {
    "capability_assessment",
    "manifest",
    "operation_admission",
    "operation_lifecycle",
    "trigger_publication",
}
_AGENT_RUNTIME_ID = "d81855f6-79ac-4b49-9f1a-c9f0985e7c58"
_PROVIDER_INSTANCE_ID = "7f7db7d8-68b4-4f71-9769-065b5c4f941c"
_PROVIDER_RUNTIME_ID = "68d818de-3671-471d-a0ba-044cf60e2c8e"


def _valid_request() -> bootstrap_pb2.HandshakeRequest:
    return bootstrap_pb2.HandshakeRequest(
        agent_runtime=bootstrap_pb2.AgentRuntime(
            runtime_id=_AGENT_RUNTIME_ID,
            software_version="0.1.0",
        ),
        expected_provider_instance_id=_PROVIDER_INSTANCE_ID,
        expected_endpoint_generation=4,
        supported_sfp_versions=[
            bootstrap_pb2.ProtocolVersion(major=1, minor=0)
        ],
    )


def _valid_response() -> bootstrap_pb2.HandshakeResponse:
    return bootstrap_pb2.HandshakeResponse(
        provider_instance_id=_PROVIDER_INSTANCE_ID,
        endpoint_generation=4,
        selected_sfp_version=bootstrap_pb2.ProtocolVersion(major=1, minor=0),
        provider_runtime_id=_PROVIDER_RUNTIME_ID,
        session_id="session-A",
    )


def _fit_string_field(
    message: Message,
    setter: Callable[[str], None],
    target_size: int,
) -> None:
    """Set one string field until the message has the requested size."""
    length = target_size
    for _ in range(8):
        setter("x" * length)
        difference = target_size - message.ByteSize()
        if difference == 0:
            return
        length += difference
    raise AssertionError(f"Could not construct a {target_size}-byte message")


def test_handshake_request_round_trip() -> None:
    request = _valid_request()

    decoded = bootstrap_pb2.HandshakeRequest.FromString(
        request.SerializeToString()
    )

    assert decoded == request


def test_validates_complete_handshake_semantics() -> None:
    request = validation.validate_handshake_request(_valid_request())
    response = validation.validate_handshake_response(_valid_response())

    assert request.agent_runtime_id == UUID(_AGENT_RUNTIME_ID)
    assert request.expected_provider_instance_id == UUID(_PROVIDER_INSTANCE_ID)
    assert request.supported_sfp_versions == (
        validation.ProtocolVersion(major=1, minor=0),
    )
    assert response.provider_runtime_id == UUID(_PROVIDER_RUNTIME_ID)
    assert response.session_id == "session-A"


@pytest.mark.parametrize(
    "change",
    [
        "missing-runtime",
        "invalid-runtime-id",
        "missing-software-version",
        "invalid-provider-id",
        "invalid-generation",
        "missing-versions",
        "duplicate-versions",
        "invalid-version",
    ],
)
def test_rejects_invalid_handshake_request_semantics(change: str) -> None:
    request = _valid_request()
    if change == "missing-runtime":
        request.ClearField("agent_runtime")
    elif change == "invalid-runtime-id":
        request.agent_runtime.runtime_id = "not-a-uuid"
    elif change == "missing-software-version":
        request.agent_runtime.software_version = ""
    elif change == "invalid-provider-id":
        request.expected_provider_instance_id = _PROVIDER_INSTANCE_ID.upper()
    elif change == "invalid-generation":
        request.expected_endpoint_generation = 0
    elif change == "missing-versions":
        request.ClearField("supported_sfp_versions")
    elif change == "duplicate-versions":
        request.supported_sfp_versions.add(major=1, minor=0)
    else:
        request.supported_sfp_versions[0].major = 0

    with pytest.raises(validation.BootstrapValidationError):
        validation.validate_handshake_request(request)


@pytest.mark.parametrize(
    "change",
    [
        "invalid-provider-id",
        "invalid-generation",
        "missing-version",
        "invalid-version",
        "invalid-runtime-id",
        "missing-session",
        "oversized-session",
    ],
)
def test_rejects_invalid_handshake_response_semantics(change: str) -> None:
    response = _valid_response()
    if change == "invalid-provider-id":
        response.provider_instance_id = "not-a-uuid"
    elif change == "invalid-generation":
        response.endpoint_generation = 0
    elif change == "missing-version":
        response.ClearField("selected_sfp_version")
    elif change == "invalid-version":
        response.selected_sfp_version.major = 0
    elif change == "invalid-runtime-id":
        response.provider_runtime_id = _PROVIDER_RUNTIME_ID.upper()
    elif change == "missing-session":
        response.session_id = ""
    else:
        response.session_id = "x" * (contract.MAX_SESSION_ID_CODE_POINTS + 1)

    with pytest.raises(validation.BootstrapValidationError):
        validation.validate_handshake_response(response)


@pytest.mark.parametrize(
    ("major", "minor"),
    [
        (0, 0),
        (True, 0),
        (1, True),
        (primitives.PROTOBUF_UINT32_MAX + 1, 0),
        (1, primitives.PROTOBUF_UINT32_MAX + 1),
    ],
)
def test_rejects_invalid_protocol_versions(
    major: object,
    minor: object,
) -> None:
    with pytest.raises(validation.BootstrapValidationError):
        validation.validate_protocol_version(major, minor)


def test_bootstrap_service_contains_handshake_method() -> None:
    service = bootstrap_pb2.DESCRIPTOR.services_by_name["BootstrapService"]

    assert tuple(service.methods_by_name) == ("Handshake",)
    assert service.full_name == contract.SERVICE_NAME


def test_bootstrap_limits_accept_exact_boundary_and_reject_larger_size() -> (
    None
):
    for target_size in (
        contract.MAX_REQUEST_BYTES,
        contract.MAX_REQUEST_BYTES + 1,
    ):
        request = bootstrap_pb2.HandshakeRequest(
            agent_runtime=bootstrap_pb2.AgentRuntime(runtime_id="agent"),
            expected_provider_instance_id="provider",
            expected_endpoint_generation=1,
            supported_sfp_versions=[
                bootstrap_pb2.ProtocolVersion(major=1, minor=0)
            ],
        )
        _fit_string_field(
            request,
            lambda value, current=request: setattr(
                current.agent_runtime, "software_version", value
            ),
            target_size,
        )
        assert request.ByteSize() == target_size
        assert (request.ByteSize() <= contract.MAX_REQUEST_BYTES) is (
            target_size == contract.MAX_REQUEST_BYTES
        )

    for target_size in (
        contract.MAX_RESPONSE_BYTES,
        contract.MAX_RESPONSE_BYTES + 1,
    ):
        response = bootstrap_pb2.HandshakeResponse(
            provider_instance_id="provider",
            endpoint_generation=1,
            selected_sfp_version=bootstrap_pb2.ProtocolVersion(
                major=1, minor=0
            ),
            session_id="session",
        )
        _fit_string_field(
            response,
            lambda value, current=response: setattr(
                current, "provider_runtime_id", value
            ),
            target_size,
        )
        assert response.ByteSize() == target_size
        assert (response.ByteSize() <= contract.MAX_RESPONSE_BYTES) is (
            target_size == contract.MAX_RESPONSE_BYTES
        )


def test_session_identifier_limit_is_shared_by_versioned_schemas() -> None:
    exact = "é" * contract.MAX_SESSION_ID_CODE_POINTS
    oversized = exact + "é"
    assert len(exact) == contract.MAX_SESSION_ID_CODE_POINTS
    assert len(oversized) == contract.MAX_SESSION_ID_CODE_POINTS + 1

    schema_families = set()
    for path in (_ROOT / "src" / "stateforge_protocol" / "sfp").glob(
        "*/v1/*.schema.json"
    ):
        document = json.loads(path.read_text(encoding="utf-8"))
        session_definition = document.get("$defs", {}).get("sessionId")
        if session_definition is None:
            continue
        schema_families.add(path.parents[1].name)
        assert session_definition["maxLength"] == (
            contract.MAX_SESSION_ID_CODE_POINTS
        )
    assert schema_families == _SESSION_SCHEMA_FAMILIES


def test_bootstrap_documentation_matches_exported_limits() -> None:
    documentation = (_ROOT / "docs" / "bootstrap.md").read_text(
        encoding="utf-8"
    )
    assert (
        f"| Serialized request | {contract.MAX_REQUEST_BYTES // 1024} KiB |"
        in documentation
    )
    assert (
        f"| Serialized response | {contract.MAX_RESPONSE_BYTES // 1024} KiB |"
        in documentation
    )
    assert (
        f"| Session ID | {contract.MAX_SESSION_ID_CODE_POINTS} Unicode code "
        "points |" in documentation
    )
