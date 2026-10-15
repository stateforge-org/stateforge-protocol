"""Expose transport limits for the shared Provider gRPC endpoint."""

from dataclasses import dataclass
from typing import Final

from stateforge_protocol.sfp import health_contract
from stateforge_protocol.sfp.bootstrap.v1 import contract as bootstrap
from stateforge_protocol.sfp.capability_assessment.v1 import (
    contract as capability_assessment,
)
from stateforge_protocol.sfp.manifest.v1 import contract as manifest
from stateforge_protocol.sfp.operation_admission.v1 import (
    contract as operation_admission,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    contract as operation_lifecycle,
)
from stateforge_protocol.sfp.trigger_publication.v1 import (
    contract as trigger_publication,
)


@dataclass(frozen=True, slots=True)
class ProcedureTransportLimits:
    """Describe one service's message limits on the shared endpoint."""

    service_name: str
    max_request_bytes: int
    max_response_bytes: int


PROCEDURE_LIMITS: Final[tuple[ProcedureTransportLimits, ...]] = (
    ProcedureTransportLimits(
        service_name=bootstrap.SERVICE_NAME,
        max_request_bytes=bootstrap.MAX_REQUEST_BYTES,
        max_response_bytes=bootstrap.MAX_RESPONSE_BYTES,
    ),
    ProcedureTransportLimits(
        service_name=health_contract.STANDARD_HEALTH_SERVICE,
        max_request_bytes=health_contract.MAX_REQUEST_BYTES,
        max_response_bytes=health_contract.MAX_RESPONSE_BYTES,
    ),
    ProcedureTransportLimits(
        service_name=manifest.SERVICE_NAME,
        max_request_bytes=manifest.MAX_REQUEST_BYTES,
        max_response_bytes=manifest.MAX_RESPONSE_BYTES,
    ),
    ProcedureTransportLimits(
        service_name=capability_assessment.SERVICE_NAME,
        max_request_bytes=capability_assessment.MAX_REQUEST_BYTES,
        max_response_bytes=capability_assessment.MAX_RESPONSE_BYTES,
    ),
    ProcedureTransportLimits(
        service_name=operation_admission.SERVICE_NAME,
        max_request_bytes=operation_admission.MAX_REQUEST_BYTES,
        max_response_bytes=operation_admission.MAX_RESPONSE_BYTES,
    ),
    ProcedureTransportLimits(
        service_name=operation_lifecycle.SERVICE_NAME,
        max_request_bytes=operation_lifecycle.MAX_REQUEST_BYTES,
        max_response_bytes=operation_lifecycle.MAX_RESPONSE_BYTES,
    ),
    ProcedureTransportLimits(
        service_name=trigger_publication.SERVICE_NAME,
        max_request_bytes=trigger_publication.MAX_REQUEST_BYTES,
        max_response_bytes=trigger_publication.MAX_RESPONSE_BYTES,
    ),
)

# Provider-oriented names make the transport direction explicit. Agent send
# uses the Provider receive ceiling; Agent receive uses the Provider send
# ceiling.
MAX_PROVIDER_RECEIVE_BYTES: Final = max(
    procedure.max_request_bytes for procedure in PROCEDURE_LIMITS
)
MAX_PROVIDER_SEND_BYTES: Final = max(
    procedure.max_response_bytes for procedure in PROCEDURE_LIMITS
)
