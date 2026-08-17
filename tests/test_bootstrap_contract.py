"""Tests for the generated SFP bootstrap wire contract."""

from stateforge_protocol.sfp.bootstrap.v1 import bootstrap_pb2


def test_handshake_request_round_trip() -> None:
    request = bootstrap_pb2.HandshakeRequest(
        agent_runtime=bootstrap_pb2.AgentRuntime(
            runtime_id="d81855f6-79ac-4b49-9f1a-c9f0985e7c58",
            software_version="0.1.0",
        ),
        expected_provider_instance_id=("7f7db7d8-68b4-4f71-9769-065b5c4f941c"),
        expected_endpoint_generation=4,
        supported_sfp_versions=[
            bootstrap_pb2.ProtocolVersion(major=1, minor=0)
        ],
    )

    decoded = bootstrap_pb2.HandshakeRequest.FromString(
        request.SerializeToString()
    )

    assert decoded == request


def test_bootstrap_service_contains_handshake_method() -> None:
    service = bootstrap_pb2.DESCRIPTOR.services_by_name["BootstrapService"]

    assert tuple(service.methods_by_name) == ("Handshake",)
