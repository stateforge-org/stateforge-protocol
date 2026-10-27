"""Expose the normative SFP Provider Manifest v1 wire contract."""

from typing import Final

from stateforge_protocol.sfp import primitives
from stateforge_protocol.sfp.bootstrap.v1 import contract as bootstrap_contract
from stateforge_protocol.sfp.manifest.v1 import manifest_pb2

SERVICE_NAME: Final = manifest_pb2.DESCRIPTOR.services_by_name[
    "ManifestService"
].full_name

# Serialized protobuf limits enforced at the RPC boundary.
MAX_REQUEST_BYTES: Final = 8 * 1024
MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024

# Canonicalization and embedded JSON limits enforced outside JSON Schema.
MAX_CANONICAL_REVISION_PREIMAGE_BYTES: Final = 1 * 1024 * 1024
MAX_PRESENTATION_REVISION_PREIMAGE_BYTES: Final = 2 * 1024 * 1024
MAX_EMBEDDED_JSON_DEPTH: Final = 64
MAX_JSON_NODES: Final = 100_000
MAX_SCHEMA_NODES: Final = 25_000

# Request-envelope limits mirrored by the packaged validation schema.
MAX_SUPPORTED_SCHEMA_VERSIONS: Final = 32
MAX_SCHEMA_VERSION: Final = primitives.PROTOBUF_UINT32_MAX
MAX_SESSION_ID_CODE_POINTS: Final = (
    bootstrap_contract.MAX_SESSION_ID_CODE_POINTS
)

# Declaration-count limits mirrored by the packaged validation schema.
MAX_OPERATIONS: Final = 1_024
MAX_TRIGGERS: Final = 1_024
MAX_RUNTIME_REQUIREMENTS: Final = 1_024
MAX_PLATFORMS: Final = 256
MAX_PROFILE_CLAIMS_PER_OPERATION: Final = 64

# Optional presentation-overlay limits mirrored by the packaged schema.
PRESENTATION_SCHEMA_VERSION: Final = 1
MAX_PRESENTATION_OPERATIONS: Final = MAX_OPERATIONS
MAX_PRESENTATION_TRIGGERS: Final = MAX_TRIGGERS
MAX_CAPABILITY_GROUPS: Final = 64
MAX_FIELD_GROUPS_PER_SCHEMA: Final = 64
MAX_FIELDS_PER_GROUP: Final = 256
MAX_FIELD_ORDER_ENTRIES: Final = 1_024
MAX_FIELD_VIEWS_PER_SCHEMA: Final = 1_024
MAX_PRESENTATION_ASSETS: Final = 64
MAX_PRESENTATION_ASSET_BYTES: Final = 256 * 1024
MAX_PRESENTATION_ASSET_TOTAL_BYTES: Final = 1 * 1024 * 1024
MAX_PRESENTATION_ASSET_DIMENSION: Final = 8_192
MAX_PRESENTATION_LABEL_CODE_POINTS: Final = 255
MAX_PRESENTATION_SUMMARY_CODE_POINTS: Final = 512
MAX_PRESENTATION_DESCRIPTION_CODE_POINTS: Final = 4_096
MAX_PRESENTATION_POINTER_CODE_POINTS: Final = 2_048

ALLOWED_PRESENTATION_MEDIA_TYPES: Final = frozenset(
    {
        "image/png",
        "image/svg+xml",
    }
)
