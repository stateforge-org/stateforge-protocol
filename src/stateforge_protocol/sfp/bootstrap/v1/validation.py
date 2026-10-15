"""Validate the complete SFP Bootstrap v1 semantic contract."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from stateforge_protocol.sfp import primitives
from stateforge_protocol.sfp.bootstrap.v1 import bootstrap_pb2, contract
from stateforge_protocol.sfp.endpoint_discovery.v1 import (
    contract as discovery_contract,
)


class BootstrapValidationError(ValueError):
    """Report Bootstrap data outside the versioned semantic contract."""


@dataclass(frozen=True, order=True, slots=True)
class ProtocolVersion:
    """One validated SFP wire version."""

    major: int
    minor: int

    def __post_init__(self) -> None:
        """Reject values outside the protobuf and SFP version contract."""
        if not primitives.is_uint32(self.major) or self.major == 0:
            raise BootstrapValidationError(
                "SFP major version must be a positive uint32"
            )
        if not primitives.is_uint32(self.minor):
            raise BootstrapValidationError(
                "SFP minor version must be a uint32"
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
    if not request.HasField("agent_runtime"):
        raise BootstrapValidationError("agent_runtime is required")
    try:
        agent_runtime_id = primitives.parse_canonical_uuid4(
            request.agent_runtime.runtime_id
        )
    except primitives.ProtocolScalarError as error:
        raise BootstrapValidationError(
            "agent_runtime.runtime_id must be a canonical UUIDv4"
        ) from error
    if not request.agent_runtime.software_version:
        raise BootstrapValidationError(
            "agent_runtime.software_version is required"
        )
    try:
        provider_instance_id = primitives.parse_canonical_uuid4(
            request.expected_provider_instance_id
        )
    except primitives.ProtocolScalarError as error:
        raise BootstrapValidationError(
            "expected_provider_instance_id must be a canonical UUIDv4"
        ) from error
    if not discovery_contract.is_allocated_endpoint_generation(
        request.expected_endpoint_generation
    ):
        raise BootstrapValidationError(
            "expected_endpoint_generation must be an allocated generation"
        )
    if not request.supported_sfp_versions:
        raise BootstrapValidationError(
            "supported_sfp_versions must contain at least one version"
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
    if len(set(versions)) != len(versions):
        raise BootstrapValidationError(
            "supported_sfp_versions must not contain duplicates"
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
    try:
        provider_instance_id = primitives.parse_canonical_uuid4(
            response.provider_instance_id
        )
    except primitives.ProtocolScalarError as error:
        raise BootstrapValidationError(
            "provider_instance_id must be a canonical UUIDv4"
        ) from error
    if not discovery_contract.is_allocated_endpoint_generation(
        response.endpoint_generation
    ):
        raise BootstrapValidationError(
            "endpoint_generation must be an allocated generation"
        )
    if not response.HasField("selected_sfp_version"):
        raise BootstrapValidationError("selected_sfp_version is required")
    selected_version = ProtocolVersion(
        major=response.selected_sfp_version.major,
        minor=response.selected_sfp_version.minor,
    )
    try:
        provider_runtime_id = primitives.parse_canonical_uuid4(
            response.provider_runtime_id
        )
    except primitives.ProtocolScalarError as error:
        raise BootstrapValidationError(
            "provider_runtime_id must be a canonical UUIDv4"
        ) from error
    session_id = response.session_id
    if not session_id or len(session_id) > contract.MAX_SESSION_ID_CODE_POINTS:
        raise BootstrapValidationError(
            "session_id must contain 1-"
            f"{contract.MAX_SESSION_ID_CODE_POINTS} Unicode code points"
        )
    return ValidatedHandshakeResponse(
        provider_instance_id=provider_instance_id,
        endpoint_generation=response.endpoint_generation,
        selected_sfp_version=selected_version,
        provider_runtime_id=provider_runtime_id,
        session_id=session_id,
    )
