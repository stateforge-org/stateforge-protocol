"""Exercise the runnable Bootstrap documentation examples."""

from uuid import UUID

import pytest
from examples.bootstrap import client, server

from stateforge_protocol.sfp.bootstrap.v1 import validation

_PROVIDER_INSTANCE_ID = UUID("7f7db7d8-68b4-4f71-9769-065b5c4f941c")
_PROVIDER_RUNTIME_ID = UUID("68d818de-3671-471d-a0ba-044cf60e2c8e")
_AGENT_RUNTIME_ID = UUID("d81855f6-79ac-4b49-9f1a-c9f0985e7c58")
_SFP_V1 = validation.ProtocolVersion(major=1, minor=0)
_UUID4_VERSION = 4


def _endpoint() -> server.EndpointState:
    return server.EndpointState(
        provider_instance_id=_PROVIDER_INSTANCE_ID,
        endpoint_generation=4,
        provider_runtime_id=_PROVIDER_RUNTIME_ID,
        supported_versions=frozenset({_SFP_V1}),
    )


@pytest.mark.asyncio
async def test_documented_client_and_server_complete_handshake() -> None:
    endpoint = _endpoint()
    grpc_server = server.create_server(endpoint)
    port = grpc_server.add_insecure_port("127.0.0.1:0")
    await grpc_server.start()
    try:
        descriptor = client.EndpointDescriptor(
            target=f"127.0.0.1:{port}",
            provider_instance_id=_PROVIDER_INSTANCE_ID,
            endpoint_generation=4,
        )
        async with client.create_channel(descriptor.target) as channel:
            result = await client.perform_handshake(
                channel,
                descriptor,
                agent_runtime_id=_AGENT_RUNTIME_ID,
                agent_software_version="0.1.0",
                supported_versions=(_SFP_V1,),
                timeout_seconds=1.0,
            )
    finally:
        await grpc_server.stop(grace=None)

    assert result.selected_version == _SFP_V1
    assert result.provider_runtime_id == _PROVIDER_RUNTIME_ID
    assert UUID(result.session_id).version == _UUID4_VERSION


@pytest.mark.asyncio
async def test_documented_client_reports_incompatible_version() -> None:
    endpoint = _endpoint()
    grpc_server = server.create_server(endpoint)
    port = grpc_server.add_insecure_port("127.0.0.1:0")
    await grpc_server.start()
    try:
        descriptor = client.EndpointDescriptor(
            target=f"127.0.0.1:{port}",
            provider_instance_id=_PROVIDER_INSTANCE_ID,
            endpoint_generation=4,
        )
        async with client.create_channel(descriptor.target) as channel:
            with pytest.raises(client.NoCommonVersionError):
                await client.perform_handshake(
                    channel,
                    descriptor,
                    agent_runtime_id=_AGENT_RUNTIME_ID,
                    agent_software_version="0.1.0",
                    supported_versions=(
                        validation.ProtocolVersion(major=2, minor=0),
                    ),
                    timeout_seconds=1.0,
                )
    finally:
        await grpc_server.stop(grace=None)
