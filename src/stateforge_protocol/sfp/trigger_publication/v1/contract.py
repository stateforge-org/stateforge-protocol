"""Expose normative Trigger Publication v1 resource limits."""

from typing import Final

from stateforge_protocol.sfp.bootstrap.v1 import contract as bootstrap_contract

# Serialized protobuf limits enforced at the RPC boundary.
MAX_REQUEST_BYTES: Final = 64 * 1024
MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024

# Canonical payload JSON limits enforced in addition to its declared schema.
MAX_CANONICAL_PAYLOAD_BYTES: Final = 1 * 1024 * 1024
MAX_PAYLOAD_JSON_DEPTH: Final = 64
MAX_PAYLOAD_CONTAINER_ENTRIES: Final = 256
MAX_PAYLOAD_PROPERTY_NAME_CODE_POINTS: Final = 128
MAX_PAYLOAD_STRING_CODE_POINTS: Final = 65_536

# Identifier, diagnostic, retry, and flow-control limits.
MAX_TRIGGER_IDENTIFIER_CODE_POINTS: Final = 255
MAX_SESSION_ID_CODE_POINTS: Final = (
    bootstrap_contract.MAX_SESSION_ID_CODE_POINTS
)
MAX_EXPLANATION_CODE_POINTS: Final = 1_024
MAX_RETRY_AFTER_SECONDS: Final = 24 * 60 * 60
MAX_IN_FLIGHT_PUBLICATIONS: Final = 1_024
