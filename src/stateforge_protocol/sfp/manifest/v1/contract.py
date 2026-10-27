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
MAX_PRESENTATION_POINTER_CODE_POINTS: Final = 2_048
MAX_PRESENTATION_SCOPE_CODE_POINTS: Final = 64

CORE_COMPONENT_NAMESPACE: Final = "stateforge.ui"

PROVIDER_OVERVIEW_SURFACE: Final = "stateforge.ui/surface.provider.overview@1"
OPERATION_REQUEST_SURFACE: Final = "stateforge.ui/surface.operation.request@1"
OPERATION_RUN_SURFACE: Final = "stateforge.ui/surface.operation.run@1"
OPERATION_RESULT_SURFACE: Final = "stateforge.ui/surface.operation.result@1"
TRIGGER_POLICY_SURFACE: Final = "stateforge.ui/surface.trigger.policy@1"
TRIGGER_EVENT_SURFACE: Final = "stateforge.ui/surface.trigger.event@1"
EVIDENCE_SURFACE: Final = "stateforge.ui/surface.evidence@1"

PROVIDER_SURFACES: Final = frozenset({PROVIDER_OVERVIEW_SURFACE})
OPERATION_SURFACES: Final = frozenset(
    {
        OPERATION_REQUEST_SURFACE,
        OPERATION_RUN_SURFACE,
        OPERATION_RESULT_SURFACE,
        EVIDENCE_SURFACE,
    }
)
TRIGGER_SURFACES: Final = frozenset(
    {
        TRIGGER_POLICY_SURFACE,
        TRIGGER_EVENT_SURFACE,
        EVIDENCE_SURFACE,
    }
)

PROVIDER_MANIFEST_BINDING: Final = "stateforge.binding/provider.manifest@1"
PROVIDER_RUNTIME_BINDING: Final = "stateforge.binding/provider.runtime@1"
OPERATION_REQUEST_SCHEMA_BINDING: Final = (
    "stateforge.binding/operation.request.schema@1"
)
# Presentation-safe projection only. The data-source owner must recursively
# omit every value whose applicable input schema marks it writeOnly. Secret
# form state is never exposed through a presentation binding.
OPERATION_REQUEST_PUBLIC_VALUE_BINDING: Final = (
    "stateforge.binding/operation.request.public_value@1"
)
OPERATION_RUN_BINDING: Final = "stateforge.binding/operation.run@1"
OPERATION_RESULT_SCHEMA_BINDING: Final = (
    "stateforge.binding/operation.result.schema@1"
)
OPERATION_RESULT_VALUE_BINDING: Final = (
    "stateforge.binding/operation.result.value@1"
)
OPERATION_EVIDENCE_BINDING: Final = "stateforge.binding/operation.evidence@1"
TRIGGER_PAYLOAD_SCHEMA_BINDING: Final = (
    "stateforge.binding/trigger.payload.schema@1"
)
TRIGGER_PAYLOAD_VALUE_BINDING: Final = (
    "stateforge.binding/trigger.payload.value@1"
)
AUDIT_BINDING: Final = "stateforge.binding/audit@1"
REPETITION_ITEM_BINDING: Final = "stateforge.binding/repetition.item@1"

SURFACE_BINDING_SOURCES: Final = {
    PROVIDER_OVERVIEW_SURFACE: frozenset(
        {PROVIDER_MANIFEST_BINDING, PROVIDER_RUNTIME_BINDING}
    ),
    OPERATION_REQUEST_SURFACE: frozenset(
        {
            PROVIDER_MANIFEST_BINDING,
            OPERATION_REQUEST_SCHEMA_BINDING,
            OPERATION_REQUEST_PUBLIC_VALUE_BINDING,
        }
    ),
    OPERATION_RUN_SURFACE: frozenset(
        {
            PROVIDER_MANIFEST_BINDING,
            OPERATION_REQUEST_PUBLIC_VALUE_BINDING,
            OPERATION_RUN_BINDING,
        }
    ),
    OPERATION_RESULT_SURFACE: frozenset(
        {
            PROVIDER_MANIFEST_BINDING,
            OPERATION_REQUEST_PUBLIC_VALUE_BINDING,
            OPERATION_RESULT_SCHEMA_BINDING,
            OPERATION_RESULT_VALUE_BINDING,
            OPERATION_EVIDENCE_BINDING,
        }
    ),
    TRIGGER_POLICY_SURFACE: frozenset(
        {PROVIDER_MANIFEST_BINDING, TRIGGER_PAYLOAD_SCHEMA_BINDING}
    ),
    TRIGGER_EVENT_SURFACE: frozenset(
        {
            PROVIDER_MANIFEST_BINDING,
            TRIGGER_PAYLOAD_SCHEMA_BINDING,
            TRIGGER_PAYLOAD_VALUE_BINDING,
        }
    ),
    EVIDENCE_SURFACE: frozenset(
        {
            PROVIDER_MANIFEST_BINDING,
            OPERATION_EVIDENCE_BINDING,
            TRIGGER_PAYLOAD_VALUE_BINDING,
            AUDIT_BINDING,
        }
    ),
}

CORE_COMPONENT_IDENTIFIERS: Final = frozenset(
    {
        "stateforge.ui/layout.stack@1",
        "stateforge.ui/layout.grid@1",
        "stateforge.ui/layout.section@1",
        "stateforge.ui/layout.tabs@1",
        "stateforge.ui/layout.steps@1",
        "stateforge.ui/input.form@1",
        "stateforge.ui/input.field@1",
        "stateforge.ui/input.object@1",
        "stateforge.ui/input.array@1",
        "stateforge.ui/input.key_value@1",
        "stateforge.ui/input.code@1",
        "stateforge.ui/content.text@1",
        "stateforge.ui/content.markdown@1",
        "stateforge.ui/data.key_value@1",
        "stateforge.ui/data.table@1",
        "stateforge.ui/data.tree@1",
        "stateforge.ui/data.code@1",
        "stateforge.ui/data.diff@1",
        "stateforge.ui/data.log@1",
        "stateforge.ui/status.badge@1",
        "stateforge.ui/status.progress@1",
        "stateforge.ui/status.timeline@1",
        "stateforge.ui/data.metric@1",
        "stateforge.ui/data.chart@1",
        "stateforge.ui/data.topology@1",
        "stateforge.ui/data.artifacts@1",
        "stateforge.ui/media.image@1",
        "stateforge.ui/action.operation_submit@1",
        "stateforge.ui/action.operation_cancel@1",
    }
)

ALLOWED_PRESENTATION_MEDIA_TYPES: Final = frozenset(
    {
        "image/png",
        "image/svg+xml",
    }
)
