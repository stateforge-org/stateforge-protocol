"""Expose normative Capability Assessment v1 resource limits."""

from typing import Final

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
