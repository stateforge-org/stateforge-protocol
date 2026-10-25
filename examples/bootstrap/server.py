"""Run a minimal asynchronous SFP Bootstrap server."""

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


@dataclass(slots=True)
class EndpointState:
    """Own the live identity and session state of one Provider endpoint."""

    provider_instance_id: UUID
    endpoint_generation: int
    provider_runtime_id: UUID
    supported_versions: frozenset[validation.ProtocolVersion]
    stopping: bool = False

    def issue_session_id(self) -> str:
        """Create a fresh opaque ID using the Provider runtime strategy."""
        return str(uuid4())


class BootstrapService(bootstrap_pb2_grpc.BootstrapServiceServicer):
    """Implement Bootstrap using Protocol validation plus live state."""

    def __init__(self, endpoint: EndpointState) -> None:
        """Bind the service to one live endpoint state owner."""
        self._endpoint = endpoint

    async def Handshake(  # noqa: N802
        self,
        request: bootstrap_pb2.HandshakeRequest,
        context: grpc.aio.ServicerContext[
            bootstrap_pb2.HandshakeRequest,
            bootstrap_pb2.HandshakeResponse,
        ],
    ) -> bootstrap_pb2.HandshakeResponse:
        """Validate identity, negotiate a version, and issue a session."""
        if request.ByteSize() > contract.MAX_REQUEST_BYTES:
            await context.abort(
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                "Bootstrap request limit exceeded",
            )
        try:
            validated = validation.validate_handshake_request(request)
        except validation.BootstrapValidationError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))

        endpoint = self._endpoint
        if (
            validated.expected_provider_instance_id
            != endpoint.provider_instance_id
        ):
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                "Provider instance does not match this endpoint",
            )
        if (
            validated.expected_endpoint_generation
            != endpoint.endpoint_generation
        ):
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                "Endpoint generation does not match this endpoint",
            )

        mutual_versions = endpoint.supported_versions.intersection(
            validated.supported_sfp_versions
        )
        if not mutual_versions:
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                "No mutually supported SFP wire version",
            )
        if endpoint.stopping:
            await context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "Provider endpoint is stopping",
            )

        selected_version = max(mutual_versions)
        response = bootstrap_pb2.HandshakeResponse(
            provider_instance_id=str(endpoint.provider_instance_id),
            endpoint_generation=endpoint.endpoint_generation,
            selected_sfp_version=bootstrap_pb2.ProtocolVersion(
                major=selected_version.major,
                minor=selected_version.minor,
            ),
            provider_runtime_id=str(endpoint.provider_runtime_id),
            session_id=endpoint.issue_session_id(),
        )
        if response.ByteSize() > contract.MAX_RESPONSE_BYTES:
            await context.abort(
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                "Bootstrap response limit exceeded",
            )
        try:
            validation.validate_handshake_response(response)
        except validation.BootstrapValidationError:
            await context.abort(
                grpc.StatusCode.INTERNAL,
                "Provider produced an invalid Bootstrap response",
            )
        return response


def create_server(endpoint: EndpointState) -> grpc.aio.Server:
    """Create a bounded shared-endpoint server with Bootstrap installed."""
    server = grpc.aio.server(
        options=(
            (
                "grpc.max_receive_message_length",
                shared_endpoint.MAX_PROVIDER_RECEIVE_BYTES,
            ),
            (
                "grpc.max_send_message_length",
                shared_endpoint.MAX_PROVIDER_SEND_BYTES,
            ),
        )
    )
    bootstrap_pb2_grpc.add_BootstrapServiceServicer_to_server(
        BootstrapService(endpoint),
        server,
    )
    return server


async def _run(arguments: argparse.Namespace) -> None:
    endpoint = EndpointState(
        provider_instance_id=UUID(arguments.provider_instance_id),
        endpoint_generation=arguments.endpoint_generation,
        provider_runtime_id=uuid4(),
        supported_versions=frozenset(
            {validation.ProtocolVersion(major=1, minor=0)}
        ),
    )
    server = create_server(endpoint)
    server.add_insecure_port(arguments.target)
    await server.start()
    _LOGGER.info(
        "Serving Provider %s generation %d at %s",
        endpoint.provider_instance_id,
        endpoint.endpoint_generation,
        arguments.target,
    )
    await server.wait_for_termination()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target", help="listen target, such as unix:/tmp/sfp.sock"
    )
    parser.add_argument("provider_instance_id", help="canonical UUIDv4")
    parser.add_argument("endpoint_generation", type=int)
    return parser.parse_args()


def main() -> None:
    """Run the Bootstrap server example."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(_run(_arguments()))


if __name__ == "__main__":
    main()
