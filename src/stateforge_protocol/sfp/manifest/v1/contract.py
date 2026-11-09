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

# Optional presentation-tree limits mirrored by the packaged schema.
PRESENTATION_SCHEMA_VERSION: Final = 1
MAX_PRESENTATION_OPERATIONS: Final = MAX_OPERATIONS
MAX_PRESENTATION_TRIGGERS: Final = MAX_TRIGGERS
MAX_PRESENTATION_SURFACES_PER_TARGET: Final = 8
MAX_PRESENTATION_COMPONENTS: Final = 4_096
MAX_PRESENTATION_COMPONENT_DEPTH: Final = 16
MAX_COMPONENT_CHILDREN: Final = 256
MAX_COMPONENT_BINDINGS: Final = 64
MAX_COMPONENT_ASSET_BINDINGS: Final = 32
MAX_COMPONENT_PROPERTIES_BYTES: Final = 64 * 1024
MAX_RENDERER_REQUIREMENTS: Final = 64
MAX_RENDERER_PERMISSIONS: Final = 32
MAX_REPETITION_ITEMS: Final = 1_024
MAX_PRESENTATION_ASSETS: Final = 64
MAX_PRESENTATION_ASSET_BYTES: Final = 256 * 1024
MAX_PRESENTATION_ASSET_TOTAL_BYTES: Final = 1 * 1024 * 1024
MAX_PRESENTATION_ASSET_DIMENSION: Final = 8_192
MAX_PRESENTATION_PNG_DECODED_BYTES: Final = 64 * 1024 * 1024
MAX_PRESENTATION_POINTER_CODE_POINTS: Final = 2_048
MAX_PRESENTATION_SCOPE_CODE_POINTS: Final = 64

STATEFORGE_NAMESPACE_ROOT: Final = "stateforge"

REPETITION_ITEM_BINDING: Final = "stateforge.binding/repetition.item@1"
RAW_OPERATION_REQUEST_BINDING: Final = (
    "stateforge.binding/operation.request.value@1"
)

ALLOWED_PRESENTATION_MEDIA_TYPES: Final = frozenset(
    {
        "image/png",
        "image/svg+xml",
    }
)
