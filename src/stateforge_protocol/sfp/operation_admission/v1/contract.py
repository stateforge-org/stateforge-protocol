"""Expose the normative SFP Operation Admission v1 wire contract."""

from dataclasses import dataclass
from typing import Final

from stateforge_protocol.sfp.operation_admission.v1 import (
    operation_admission_pb2,
)

SERVICE_NAME: Final = operation_admission_pb2.DESCRIPTOR.services_by_name[
    "OperationAdmissionService"
].full_name

# Serialized protobuf limits enforced at the RPC boundary.
MAX_REQUEST_BYTES: Final = 8 * 1024 * 1024
MAX_RESPONSE_BYTES: Final = 1 * 1024 * 1024
MAX_ERROR_DETAIL_BYTES: Final = 4 * 1024

# Invocation JSON limits enforced before dynamic manifest-schema validation.
MAX_PAYLOAD_JSON_DEPTH: Final = 64
MAX_EXECUTION_CONTEXT_JSON_DEPTH: Final = 64
MAX_JSON_CONTAINER_ENTRIES: Final = 256

# Contract-context limits mirrored by the packaged validation schema.


@dataclass(frozen=True, slots=True)
class AdmissionErrorContract:
    """Bind one structured rejection reason to its transport semantics."""

    grpc_status: str
    retryable: bool


def _reason(name: str) -> int:
    return operation_admission_pb2.AdmissionErrorReason.Value(name)


ADMISSION_ERROR_CONTRACTS: Final = {
    _reason("ADMISSION_ERROR_REASON_INVALID_OPERATION_REQUEST"): (
        AdmissionErrorContract("INVALID_ARGUMENT", False)
    ),
    _reason("ADMISSION_ERROR_REASON_OPERATION_NOT_DECLARED"): (
        AdmissionErrorContract("UNIMPLEMENTED", False)
    ),
    _reason("ADMISSION_ERROR_REASON_OPERATION_INCOMPATIBLE"): (
        AdmissionErrorContract("FAILED_PRECONDITION", False)
    ),
    _reason("ADMISSION_ERROR_REASON_OPERATION_PRECONDITION_FAILED"): (
        AdmissionErrorContract("FAILED_PRECONDITION", True)
    ),
    _reason("ADMISSION_ERROR_REASON_PROVIDER_CAPACITY_EXHAUSTED"): (
        AdmissionErrorContract("RESOURCE_EXHAUSTED", True)
    ),
    _reason("ADMISSION_ERROR_REASON_PROVIDER_UNAVAILABLE"): (
        AdmissionErrorContract("UNAVAILABLE", True)
    ),
    _reason("ADMISSION_ERROR_REASON_IDEMPOTENCY_CONFLICT"): (
        AdmissionErrorContract("ALREADY_EXISTS", False)
    ),
    _reason("ADMISSION_ERROR_REASON_OPERATION_DEADLINE_EXPIRED"): (
        AdmissionErrorContract("DEADLINE_EXCEEDED", False)
    ),
    _reason("ADMISSION_ERROR_REASON_OPERATION_RECORD_UNAVAILABLE"): (
        AdmissionErrorContract("FAILED_PRECONDITION", False)
    ),
    _reason("ADMISSION_ERROR_REASON_OPERATION_RECORD_EXPIRED"): (
        AdmissionErrorContract("FAILED_PRECONDITION", False)
    ),
}
