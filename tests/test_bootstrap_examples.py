"""Exercise the runnable Bootstrap documentation examples."""

import argparse
import asyncio
import logging
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


@pytest.mark.asyncio
async def test_documented_server_stops_when_its_task_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wait_started = asyncio.Event()
    stopped_with: list[float | None] = []

    class FakeServer:
        def add_insecure_port(self, target: str) -> int:
            assert target == "127.0.0.1:0"
            return 1

        async def start(self) -> None:
            return None

        async def wait_for_termination(self) -> bool:
            wait_started.set()
            await asyncio.Future()
            return False

        async def stop(self, grace: float | None) -> None:
            stopped_with.append(grace)

    fake_server = FakeServer()
    monkeypatch.setattr(server, "create_server", lambda endpoint: fake_server)
    arguments = argparse.Namespace(
        target="127.0.0.1:0",
        provider_instance_id=str(_PROVIDER_INSTANCE_ID),
        endpoint_generation=4,
    )

    task = asyncio.create_task(server._run(arguments))
    await wait_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert stopped_with == [None]


def test_documented_server_treats_keyboard_interrupt_as_clean_exit(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(server, "_arguments", object)

    def interrupt(coroutine: object) -> None:
        coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(server.asyncio, "run", interrupt)

    server.main()

    assert "Provider stopped" in caplog.text
