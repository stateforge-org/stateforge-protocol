"""Run a minimal asynchronous SFP Bootstrap client."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

import grpc

from stateforge_protocol.sfp import shared_endpoint
from stateforge_protocol.sfp.bootstrap.v1 import (
    bootstrap_pb2,
    bootstrap_pb2_grpc,
    contract,
    validation,
)

_LOGGER = logging.getLogger(__name__)


class HandshakeError(RuntimeError):
    """Report a handshake that cannot produce a trusted SFP session."""


class NoCommonVersionError(HandshakeError):
    """Report that the Agent and Provider share no SFP wire version."""


@dataclass(frozen=True, slots=True)
class EndpointDescriptor:
    """Represent the already-validated endpoint discovery result."""

    target: str
    provider_instance_id: UUID
    endpoint_generation: int


@dataclass(frozen=True, slots=True)
class HandshakeResult:
    """Return the identity and session fences accepted by the Agent."""

    selected_version: validation.ProtocolVersion
    provider_runtime_id: UUID
    session_id: str


def create_channel(target: str) -> grpc.aio.Channel:
    """Create the shared Provider channel with Protocol-owned ceilings."""
    return grpc.aio.insecure_channel(
        target,
        options=(
            (
                "grpc.max_send_message_length",
                shared_endpoint.MAX_PROVIDER_RECEIVE_BYTES,
            ),
            (
                "grpc.max_receive_message_length",
                shared_endpoint.MAX_PROVIDER_SEND_BYTES,
            ),
        ),
    )


async def perform_handshake(
    channel: grpc.aio.Channel,
    descriptor: EndpointDescriptor,
    *,
    agent_runtime_id: UUID,
    agent_software_version: str,
    supported_versions: tuple[validation.ProtocolVersion, ...],
    timeout_seconds: float,
) -> HandshakeResult:
    """Negotiate one SFP session and validate all Agent-owned fences."""
    request = bootstrap_pb2.HandshakeRequest(
        agent_runtime=bootstrap_pb2.AgentRuntime(
            runtime_id=str(agent_runtime_id),
            software_version=agent_software_version,
        ),
        expected_provider_instance_id=str(descriptor.provider_instance_id),
        expected_endpoint_generation=descriptor.endpoint_generation,
        supported_sfp_versions=[
            bootstrap_pb2.ProtocolVersion(
                major=version.major,
                minor=version.minor,
            )
            for version in supported_versions
        ],
    )
    if request.ByteSize() > contract.MAX_REQUEST_BYTES:
        raise HandshakeError("Bootstrap request exceeds its wire limit")
    try:
        validation.validate_handshake_request(request)
    except validation.BootstrapValidationError as error:
        raise HandshakeError(f"Invalid Bootstrap request: {error}") from error

    stub = bootstrap_pb2_grpc.BootstrapServiceStub(channel)
    try:
        response = await stub.Handshake(
            request,
            timeout=timeout_seconds,
        )
    except grpc.aio.AioRpcError as error:
        if error.code() is grpc.StatusCode.UNIMPLEMENTED:
            raise NoCommonVersionError(
                "Agent and Provider share no SFP wire version"
            ) from error
        raise

    if response.ByteSize() > contract.MAX_RESPONSE_BYTES:
        raise HandshakeError("Bootstrap response exceeds its wire limit")
    try:
        validated = validation.validate_handshake_response(response)
    except validation.BootstrapValidationError as error:
        raise HandshakeError(f"Invalid Bootstrap response: {error}") from error

    if validated.provider_instance_id != descriptor.provider_instance_id:
        raise HandshakeError("Provider instance does not match discovery")
    if validated.endpoint_generation != descriptor.endpoint_generation:
        raise HandshakeError("Endpoint generation does not match discovery")
    if validated.selected_sfp_version not in supported_versions:
        raise HandshakeError("Provider selected a version not offered")

    return HandshakeResult(
        selected_version=validated.selected_sfp_version,
        provider_runtime_id=validated.provider_runtime_id,
        session_id=validated.session_id,
    )


async def _run(arguments: argparse.Namespace) -> None:
    descriptor = EndpointDescriptor(
        target=arguments.target,
        provider_instance_id=UUID(arguments.provider_instance_id),
        endpoint_generation=arguments.endpoint_generation,
    )
    async with create_channel(descriptor.target) as channel:
        result = await perform_handshake(
            channel,
            descriptor,
            agent_runtime_id=uuid4(),
            agent_software_version="bootstrap-example",
            supported_versions=(validation.ProtocolVersion(major=1, minor=0),),
            timeout_seconds=5.0,
        )
    _LOGGER.info(
        "Session established: SFP %d.%d, Provider runtime %s, session %s",
        result.selected_version.major,
        result.selected_version.minor,
        result.provider_runtime_id,
        result.session_id,
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target", help="gRPC target, such as unix:/tmp/sfp.sock"
    )
    parser.add_argument("provider_instance_id", help="discovered UUIDv4")
    parser.add_argument("endpoint_generation", type=int)
    return parser.parse_args()


def main() -> None:
    """Run the Bootstrap client example."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(_run(_arguments()))


if __name__ == "__main__":
    main()
