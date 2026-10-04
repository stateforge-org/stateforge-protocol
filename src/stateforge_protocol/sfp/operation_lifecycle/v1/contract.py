"""Expose normative Operation Lifecycle v1 resource limits."""

from typing import Final

# Serialized protobuf limits enforced at the RPC boundary.
MAX_REQUEST_BYTES: Final = 8 * 1024
MAX_RESPONSE_BYTES: Final = 8 * 1024 * 1024
MAX_SNAPSHOT_BYTES: Final = 7 * 1024 * 1024
MAX_ERROR_DETAIL_BYTES: Final = 4 * 1024

# Result JSON limits shared with the admitted operation contract.
MAX_RESULT_JSON_DEPTH: Final = 64
MAX_RESULT_CONTAINER_ENTRIES: Final = 256
MAX_RESULT_PROPERTY_NAME_CODE_POINTS: Final = 128
MAX_RESULT_STRING_CODE_POINTS: Final = 65_536

# Diagnostic and observer limits defined by this procedure.
MAX_EXPLANATION_CODE_POINTS: Final = 1_024
MAX_PENDING_SNAPSHOTS_PER_OBSERVER: Final = 1
MAX_IN_FLIGHT_RESPONSES_PER_OBSERVER: Final = 1
MAX_OBSERVERS_PER_OPERATION: Final = 16
MAX_STALLED_DELIVERY_SECONDS: Final = 30
