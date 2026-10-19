"""Validate the complete SFP Bootstrap v1 semantic contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from stateforge_protocol.sfp import _validation, primitives
from stateforge_protocol.sfp.bootstrap.v1 import bootstrap_pb2, contract
from stateforge_protocol.sfp.endpoint_discovery.v1 import (
    contract as discovery_contract,
)

__all__ = [
    "BootstrapValidationError",
    "ProtocolVersion",
    "ValidatedHandshakeRequest",
    "ValidatedHandshakeResponse",
    "validate_handshake_request",
    "validate_handshake_response",
    "validate_protocol_version",
]


class BootstrapValidationError(ValueError):
    """Report Bootstrap data outside the versioned semantic contract."""


_VALIDATION: Final = _validation.ValidationContext(BootstrapValidationError)


@dataclass(frozen=True, order=True, slots=True)
class ProtocolVersion:
    """One validated SFP wire version."""

    major: int
    minor: int

    def __post_init__(self) -> None:
        """Reject values outside the protobuf and SFP version contract."""
        _VALIDATION.require_integer_range(
            self.major,
            minimum=1,
            maximum=primitives.PROTOBUF_UINT32_MAX,
            message="SFP major version must be a positive uint32",
        )
        _VALIDATION.require_integer_range(
            self.minor,
            minimum=0,
            maximum=primitives.PROTOBUF_UINT32_MAX,
            message="SFP minor version must be a uint32",
        )


@dataclass(frozen=True, slots=True)
class ValidatedHandshakeRequest:
    """Canonical semantic values extracted from a Handshake request."""

    agent_runtime_id: UUID
    agent_software_version: str
    expected_provider_instance_id: UUID
    expected_endpoint_generation: int
    supported_sfp_versions: tuple[ProtocolVersion, ...]


@dataclass(frozen=True, slots=True)
class ValidatedHandshakeResponse:
    """Canonical semantic values extracted from a Handshake response."""

    provider_instance_id: UUID
    endpoint_generation: int
    selected_sfp_version: ProtocolVersion
    provider_runtime_id: UUID
    session_id: str


def validate_protocol_version(major: int, minor: int) -> ProtocolVersion:
    """Validate and return one version without consumer-owned limits."""
    return ProtocolVersion(major=major, minor=minor)


def validate_handshake_request(
    request: bootstrap_pb2.HandshakeRequest,
) -> ValidatedHandshakeRequest:
    """Validate every context-independent Handshake request obligation."""
    request = _VALIDATION.require_instance(
        request,
        bootstrap_pb2.HandshakeRequest,
        "request must be a HandshakeRequest",
    )
    _VALIDATION.require(
        request.HasField("agent_runtime"),
        "agent_runtime is required",
    )
    agent_runtime_id = _VALIDATION.require_canonical_uuid4(
        request.agent_runtime.runtime_id,
        "agent_runtime.runtime_id must be a canonical UUIDv4",
    )
    _VALIDATION.require(
        bool(request.agent_runtime.software_version),
        "agent_runtime.software_version is required",
    )
    provider_instance_id = _VALIDATION.require_canonical_uuid4(
        request.expected_provider_instance_id,
        "expected_provider_instance_id must be a canonical UUIDv4",
    )
    _VALIDATION.require(
        discovery_contract.is_allocated_endpoint_generation(
            request.expected_endpoint_generation
        ),
        "expected_endpoint_generation must be an allocated generation",
    )
    _VALIDATION.require(
        bool(request.supported_sfp_versions),
        "supported_sfp_versions must contain at least one version",
    )
    try:
        versions = tuple(
            ProtocolVersion(major=value.major, minor=value.minor)
            for value in request.supported_sfp_versions
        )
    except BootstrapValidationError as error:
        raise BootstrapValidationError(
            "supported_sfp_versions contains an invalid wire version"
        ) from error
    _VALIDATION.require_unique(
        versions,
        "supported_sfp_versions must not contain duplicates",
    )
    return ValidatedHandshakeRequest(
        agent_runtime_id=agent_runtime_id,
        agent_software_version=request.agent_runtime.software_version,
        expected_provider_instance_id=provider_instance_id,
        expected_endpoint_generation=request.expected_endpoint_generation,
        supported_sfp_versions=versions,
    )


def validate_handshake_response(
    response: bootstrap_pb2.HandshakeResponse,
) -> ValidatedHandshakeResponse:
    """Validate every context-independent Handshake response obligation."""
    response = _VALIDATION.require_instance(
        response,
        bootstrap_pb2.HandshakeResponse,
        "response must be a HandshakeResponse",
    )
    provider_instance_id = _VALIDATION.require_canonical_uuid4(
        response.provider_instance_id,
        "provider_instance_id must be a canonical UUIDv4",
    )
    _VALIDATION.require(
        discovery_contract.is_allocated_endpoint_generation(
            response.endpoint_generation
        ),
        "endpoint_generation must be an allocated generation",
    )
    _VALIDATION.require(
        response.HasField("selected_sfp_version"),
        "selected_sfp_version is required",
    )
    selected_version = ProtocolVersion(
        major=response.selected_sfp_version.major,
        minor=response.selected_sfp_version.minor,
    )
    provider_runtime_id = _VALIDATION.require_canonical_uuid4(
        response.provider_runtime_id,
        "provider_runtime_id must be a canonical UUIDv4",
    )
    session_id = _VALIDATION.require_code_point_length(
        response.session_id,
        minimum=1,
        maximum=contract.MAX_SESSION_ID_CODE_POINTS,
        message=(
            "session_id must contain 1-"
            f"{contract.MAX_SESSION_ID_CODE_POINTS} Unicode code points"
        ),
    )
    return ValidatedHandshakeResponse(
        provider_instance_id=provider_instance_id,
        endpoint_generation=response.endpoint_generation,
        selected_sfp_version=selected_version,
        provider_runtime_id=provider_runtime_id,
        session_id=session_id,
    )
