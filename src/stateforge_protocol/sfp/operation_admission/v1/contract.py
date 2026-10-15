"""Expose the normative SFP Operation Admission v1 wire contract."""

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
MAX_REQUIRED_IMPLEMENTATION_ROLES: Final = 16
