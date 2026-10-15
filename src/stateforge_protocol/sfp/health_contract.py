"""Expose StateForge's contract for the standard gRPC Health service."""

from typing import Final

from stateforge_protocol.sfp.bootstrap.v1 import contract as bootstrap_contract

STANDARD_HEALTH_SERVICE: Final = "grpc.health.v1.Health"
OVERALL_SERVICE_NAME: Final = ""
PROVIDER_HEALTH_SERVICE: Final = OVERALL_SERVICE_NAME

# Serialized standard Health messages enforced at the RPC boundary.
MAX_REQUEST_BYTES: Final = 4 * 1024
MAX_RESPONSE_BYTES: Final = 64

BOOTSTRAP_SERVICE: Final = bootstrap_contract.SERVICE_NAME
MANIFEST_SERVICE: Final = "stateforge.sfp.manifest.v1.ManifestService"
CAPABILITY_ASSESSMENT_SERVICE: Final = (
    "stateforge.sfp.capability_assessment.v1.CapabilityAssessmentService"
)
OPERATION_ADMISSION_SERVICE: Final = (
    "stateforge.sfp.operation_admission.v1.OperationAdmissionService"
)
OPERATION_LIFECYCLE_SERVICE: Final = (
    "stateforge.sfp.operation_lifecycle.v1.OperationLifecycleService"
)
TRIGGER_PUBLICATION_SERVICE: Final = (
    "stateforge.sfp.trigger_publication.v1.TriggerPublicationService"
)

SFP_SERVICE_NAMES: Final[tuple[str, ...]] = (
    BOOTSTRAP_SERVICE,
    MANIFEST_SERVICE,
    CAPABILITY_ASSESSMENT_SERVICE,
    OPERATION_ADMISSION_SERVICE,
    OPERATION_LIFECYCLE_SERVICE,
    TRIGGER_PUBLICATION_SERVICE,
)

# The Agent observes process-wide Provider health through the standard empty
# service key. Named SFP service keys remain useful for diagnostics, but they
# are not the authoritative input to Provider operational eligibility.
AUTHORITATIVE_WATCH_SERVICE: Final = PROVIDER_HEALTH_SERVICE

HEALTH_STATUS_NAMES: Final[tuple[str, ...]] = (
    "UNKNOWN",
    "SERVING",
    "NOT_SERVING",
    "SERVICE_UNKNOWN",
)

MAX_DIAGNOSTIC_CODE_POINTS: Final = 1_024
