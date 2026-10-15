"""Expose StateForge's contract for the standard gRPC Health service."""

from typing import Final

from grpc_health.v1 import health_pb2

from stateforge_protocol.sfp.bootstrap.v1 import contract as bootstrap_contract
from stateforge_protocol.sfp.capability_assessment.v1 import (
    contract as capability_assessment_contract,
)
from stateforge_protocol.sfp.manifest.v1 import contract as manifest_contract
from stateforge_protocol.sfp.operation_admission.v1 import (
    contract as operation_admission_contract,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    contract as operation_lifecycle_contract,
)
from stateforge_protocol.sfp.trigger_publication.v1 import (
    contract as trigger_publication_contract,
)

STANDARD_HEALTH_SERVICE: Final = health_pb2.DESCRIPTOR.services_by_name[
    "Health"
].full_name
OVERALL_SERVICE_NAME: Final = ""
PROVIDER_HEALTH_SERVICE: Final = OVERALL_SERVICE_NAME

# Serialized standard Health messages enforced at the RPC boundary.
MAX_REQUEST_BYTES: Final = 4 * 1024
MAX_RESPONSE_BYTES: Final = 64

BOOTSTRAP_SERVICE: Final = bootstrap_contract.SERVICE_NAME
MANIFEST_SERVICE: Final = manifest_contract.SERVICE_NAME
CAPABILITY_ASSESSMENT_SERVICE: Final = (
    capability_assessment_contract.SERVICE_NAME
)
OPERATION_ADMISSION_SERVICE: Final = operation_admission_contract.SERVICE_NAME
OPERATION_LIFECYCLE_SERVICE: Final = operation_lifecycle_contract.SERVICE_NAME
TRIGGER_PUBLICATION_SERVICE: Final = trigger_publication_contract.SERVICE_NAME

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
