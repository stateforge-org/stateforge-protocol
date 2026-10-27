"""Expose the normative SFP Provider Manifest v1 wire contract."""

from dataclasses import dataclass
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
ALL_PRESENTATION_SURFACES: Final = (
    PROVIDER_SURFACES | OPERATION_SURFACES | TRIGGER_SURFACES
)
INPUT_PRESENTATION_SURFACES: Final = frozenset(
    {OPERATION_REQUEST_SURFACE, TRIGGER_POLICY_SURFACE}
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


@dataclass(frozen=True, slots=True)
class CoreComponentContract:
    """Define Protocol-owned structure for one portable core component."""

    permitted_surfaces: frozenset[str]
    minimum_children: int = 0
    maximum_children: int = 0
    required_bindings: frozenset[str] = frozenset()
    optional_bindings: frozenset[str] = frozenset()
    binding_source_rules: tuple[tuple[str, frozenset[str]], ...] = ()
    required_assets: frozenset[str] = frozenset()
    optional_assets: frozenset[str] = frozenset()


_LAYOUT_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    minimum_children=1,
    maximum_children=MAX_COMPONENT_CHILDREN,
)
_INPUT_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=INPUT_PRESENTATION_SURFACES,
    required_bindings=frozenset({"schema"}),
    optional_bindings=frozenset({"value"}),
    binding_source_rules=(
        (
            "schema",
            frozenset(
                {
                    OPERATION_REQUEST_SCHEMA_BINDING,
                    TRIGGER_PAYLOAD_SCHEMA_BINDING,
                }
            ),
        ),
        ("value", frozenset({OPERATION_REQUEST_PUBLIC_VALUE_BINDING})),
    ),
)
_INPUT_CONTAINER_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=INPUT_PRESENTATION_SURFACES,
    maximum_children=MAX_COMPONENT_CHILDREN,
    required_bindings=_INPUT_COMPONENT.required_bindings,
    optional_bindings=_INPUT_COMPONENT.optional_bindings,
    binding_source_rules=_INPUT_COMPONENT.binding_source_rules,
)
_SECRET_INPUT_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=INPUT_PRESENTATION_SURFACES,
    required_bindings=frozenset({"schema"}),
    binding_source_rules=(
        (
            "schema",
            frozenset(
                {
                    OPERATION_REQUEST_SCHEMA_BINDING,
                    TRIGGER_PAYLOAD_SCHEMA_BINDING,
                }
            ),
        ),
    ),
)
_STATIC_CONTENT_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    optional_bindings=frozenset({"value"}),
)
_BOUND_VALUE_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    required_bindings=frozenset({"value"}),
)
_TABLE_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    required_bindings=frozenset({"rows"}),
)
_DIFF_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    required_bindings=frozenset({"before", "after"}),
)
_LOG_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    required_bindings=frozenset({"entries"}),
)
_TIMELINE_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    required_bindings=frozenset({"events"}),
)
_CHART_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    required_bindings=frozenset({"series"}),
)
_TOPOLOGY_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    required_bindings=frozenset({"nodes", "edges"}),
)
_ARTIFACTS_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    required_bindings=frozenset({"items"}),
)
_IMAGE_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=ALL_PRESENTATION_SURFACES,
    required_assets=frozenset({"source"}),
)
_SUBMIT_ACTION_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=frozenset({OPERATION_REQUEST_SURFACE}),
)
_CANCEL_ACTION_COMPONENT: Final = CoreComponentContract(
    permitted_surfaces=frozenset({OPERATION_RUN_SURFACE}),
)

CORE_COMPONENT_CONTRACTS: Final = {
    "stateforge.ui/layout.stack@1": _LAYOUT_COMPONENT,
    "stateforge.ui/layout.grid@1": _LAYOUT_COMPONENT,
    "stateforge.ui/layout.section@1": _LAYOUT_COMPONENT,
    "stateforge.ui/layout.tabs@1": _LAYOUT_COMPONENT,
    "stateforge.ui/layout.steps@1": _LAYOUT_COMPONENT,
    "stateforge.ui/input.form@1": _INPUT_CONTAINER_COMPONENT,
    "stateforge.ui/input.field@1": _INPUT_COMPONENT,
    "stateforge.ui/input.object@1": _INPUT_CONTAINER_COMPONENT,
    "stateforge.ui/input.array@1": _INPUT_CONTAINER_COMPONENT,
    "stateforge.ui/input.key_value@1": _INPUT_COMPONENT,
    "stateforge.ui/input.code@1": _INPUT_COMPONENT,
    "stateforge.ui/input.secret@1": _SECRET_INPUT_COMPONENT,
    "stateforge.ui/content.text@1": _STATIC_CONTENT_COMPONENT,
    "stateforge.ui/content.markdown@1": _STATIC_CONTENT_COMPONENT,
    "stateforge.ui/data.key_value@1": _BOUND_VALUE_COMPONENT,
    "stateforge.ui/data.table@1": _TABLE_COMPONENT,
    "stateforge.ui/data.tree@1": _BOUND_VALUE_COMPONENT,
    "stateforge.ui/data.code@1": _BOUND_VALUE_COMPONENT,
    "stateforge.ui/data.diff@1": _DIFF_COMPONENT,
    "stateforge.ui/data.log@1": _LOG_COMPONENT,
    "stateforge.ui/status.badge@1": _BOUND_VALUE_COMPONENT,
    "stateforge.ui/status.progress@1": _BOUND_VALUE_COMPONENT,
    "stateforge.ui/status.timeline@1": _TIMELINE_COMPONENT,
    "stateforge.ui/data.metric@1": _BOUND_VALUE_COMPONENT,
    "stateforge.ui/data.chart@1": _CHART_COMPONENT,
    "stateforge.ui/data.topology@1": _TOPOLOGY_COMPONENT,
    "stateforge.ui/data.artifacts@1": _ARTIFACTS_COMPONENT,
    "stateforge.ui/media.image@1": _IMAGE_COMPONENT,
    "stateforge.ui/action.operation_submit@1": _SUBMIT_ACTION_COMPONENT,
    "stateforge.ui/action.operation_cancel@1": _CANCEL_ACTION_COMPONENT,
}

CORE_COMPONENT_IDENTIFIERS: Final = frozenset(CORE_COMPONENT_CONTRACTS)

ALLOWED_PRESENTATION_MEDIA_TYPES: Final = frozenset(
    {
        "image/png",
        "image/svg+xml",
    }
)
