"""Expose the normative SFP Capability Assessment v1 wire contract."""

from typing import Final

from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2,
)

SERVICE_NAME: Final = capability_assessment_pb2.DESCRIPTOR.services_by_name[
    "CapabilityAssessmentService"
].full_name

# Serialized protobuf limits enforced at the RPC boundary.
MAX_REQUEST_BYTES: Final = 8 * 1024 * 1024
MAX_RESPONSE_BYTES: Final = 16 * 1024 * 1024

# Execution-context limits enforced before semantic assessment.
MAX_EXECUTION_CONTEXT_JSON_DEPTH: Final = 64
MAX_EXECUTION_CONTEXT_CONTAINER_ENTRIES: Final = 32

# Assessment-count limits mirrored by the packaged validation schema.
MAX_OPERATION_IDENTIFIERS: Final = 64
MAX_REQUIREMENT_FINDINGS_PER_OPERATION: Final = 64
MAX_REASONS_PER_OPERATION: Final = 16
MAX_CONSTRAINTS_PER_OPERATION: Final = 32

# Canonical reusable values from the open reason-code vocabulary.
REASON_CODE_ACCESS_DENIED: Final[str] = (
    "stateforge.capability_assessment.v1.access_denied"
)
REASON_CODE_PERMISSION_UNCERTAIN: Final[str] = (
    "stateforge.capability_assessment.v1.permission_uncertain"
)
REASON_CODE_UNSUPPORTED_VENDOR_STATE: Final[str] = (
    "stateforge.capability_assessment.v1.unsupported_vendor_state"
)
REASON_CODE_INSUFFICIENT_EVIDENCE: Final[str] = (
    "stateforge.capability_assessment.v1.insufficient_evidence"
)
REASON_CODE_REQUIREMENT_UNMET: Final[str] = (
    "stateforge.capability_assessment.v1.requirement_unmet"
)
