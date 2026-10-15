"""Expose the normative SFP Bootstrap v1 wire contract."""

from typing import Final

SERVICE_NAME: Final = "stateforge.sfp.bootstrap.v1.BootstrapService"
HANDSHAKE_METHOD_NAME: Final = "Handshake"
HANDSHAKE_METHOD_PATH: Final = f"/{SERVICE_NAME}/{HANDSHAKE_METHOD_NAME}"

# Serialized protobuf limits enforced at the RPC boundary.
MAX_REQUEST_BYTES: Final = 64 * 1024
MAX_RESPONSE_BYTES: Final = 8 * 1024

# The negotiated session identifier is opaque Unicode protocol data.
MAX_SESSION_ID_CODE_POINTS: Final = 255
