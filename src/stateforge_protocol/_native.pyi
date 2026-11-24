"""Typed interface to the native Protocol implementation."""

from stateforge_protocol.sfp.bootstrap.v1.bootstrap_pb2 import ProtocolVersion

def validate_protocol_version(version: ProtocolVersion) -> None: ...
