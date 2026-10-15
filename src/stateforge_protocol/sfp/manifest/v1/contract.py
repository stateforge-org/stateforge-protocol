"""Expose the normative SFP Provider Manifest v1 wire contract."""

from typing import Final

from stateforge_protocol.sfp.manifest.v1 import manifest_pb2

SERVICE_NAME: Final = manifest_pb2.DESCRIPTOR.services_by_name[
    "ManifestService"
].full_name

# Serialized protobuf limits enforced at the RPC boundary.
MAX_REQUEST_BYTES: Final = 8 * 1024
MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024

# Canonicalization and embedded JSON limits enforced outside JSON Schema.
MAX_CANONICAL_REVISION_PREIMAGE_BYTES: Final = 1 * 1024 * 1024
MAX_EMBEDDED_JSON_DEPTH: Final = 64
MAX_JSON_NODES: Final = 100_000
MAX_SCHEMA_NODES: Final = 25_000

# Declaration-count limits mirrored by the packaged validation schema.
MAX_OPERATIONS: Final = 1_024
MAX_TRIGGERS: Final = 1_024
MAX_RUNTIME_REQUIREMENTS: Final = 1_024
MAX_PLATFORMS: Final = 256
MAX_PROFILE_CLAIMS_PER_OPERATION: Final = 64
