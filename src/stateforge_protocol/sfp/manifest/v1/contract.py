"""Expose normative Provider Manifest v1 resource limits."""

from typing import Final

# Serialized protobuf limits enforced at the RPC boundary.
MAX_REQUEST_BYTES: Final = 8 * 1024
MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024

# Canonicalization and embedded JSON limits enforced outside JSON Schema.
MAX_CANONICAL_REVISION_PREIMAGE_BYTES: Final = 1 * 1024 * 1024
MAX_EMBEDDED_JSON_DEPTH: Final = 64

# Declaration-count limits mirrored by the packaged validation schema.
MAX_OPERATIONS: Final = 1_024
MAX_TRIGGERS: Final = 1_024
MAX_RUNTIME_REQUIREMENTS: Final = 1_024
MAX_PLATFORMS: Final = 256
MAX_PROFILE_CLAIMS_PER_OPERATION: Final = 64
