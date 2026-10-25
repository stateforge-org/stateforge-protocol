"""Validate the complete SFP Operation Lifecycle v1 contract."""

from __future__ import annotations

from typing import Final

from stateforge_protocol.sfp import _validation
from stateforge_protocol.sfp.operation_admission.v1 import (
    validation as admission_validation,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    contract,
    operation_lifecycle_pb2,
)

__all__ = [
    "OperationLifecycleValidationError",
    "validate_cancel_exchange",
    "validate_cancel_operation_request",
    "validate_cancel_operation_response",
    "validate_lifecycle_error_detail",
    "validate_operation_snapshot",
    "validate_snapshot_transition",
    "validate_terminal_replay",
    "validate_watch_exchange",
    "validate_watch_operation_request",
    "validate_watch_operation_response",
]

_SCHEMA: Final = _validation.PackagedSchema(
    package="stateforge_protocol.sfp.operation_lifecycle.v1",
    resource="operation_lifecycle.schema.json",
    contract_name="Operation Lifecycle v1",
)
_TERMINAL_STATES: Final = {
    operation_lifecycle_pb2.OPERATION_STATE_SUCCEEDED,
    operation_lifecycle_pb2.OPERATION_STATE_FAILED,
    operation_lifecycle_pb2.OPERATION_STATE_CANCELLED,
}
_FIRST_NON_ACCEPTED_SEQUENCE: Final = 2
_FIRST_PROGRESS_SEQUENCE: Final = 3
_TRANSITIONS: Final = {
    operation_lifecycle_pb2.OPERATION_STATE_ACCEPTED: {
        operation_lifecycle_pb2.OPERATION_STATE_RUNNING,
        operation_lifecycle_pb2.OPERATION_STATE_CANCELLATION_REQUESTED,
        operation_lifecycle_pb2.OPERATION_STATE_FAILED,
    },
    operation_lifecycle_pb2.OPERATION_STATE_RUNNING: {
        operation_lifecycle_pb2.OPERATION_STATE_RUNNING,
        operation_lifecycle_pb2.OPERATION_STATE_CANCELLATION_REQUESTED,
        operation_lifecycle_pb2.OPERATION_STATE_SUCCEEDED,
        operation_lifecycle_pb2.OPERATION_STATE_FAILED,
    },
    operation_lifecycle_pb2.OPERATION_STATE_CANCELLATION_REQUESTED: {
        operation_lifecycle_pb2.OPERATION_STATE_CANCELLATION_REQUESTED,
        operation_lifecycle_pb2.OPERATION_STATE_SUCCEEDED,
        operation_lifecycle_pb2.OPERATION_STATE_FAILED,
        operation_lifecycle_pb2.OPERATION_STATE_CANCELLED,
    },
}


class OperationLifecycleValidationError(ValueError):
    """Report invalid lifecycle data without exposing business results."""


_VALIDATION: Final = _validation.ValidationContext(
    OperationLifecycleValidationError
)


def validate_watch_operation_request(
    request: operation_lifecycle_pb2.WatchOperationRequest,
) -> None:
    """Validate one request to observe an admitted operation."""
    request = _VALIDATION.require_instance(
        request,
        operation_lifecycle_pb2.WatchOperationRequest,
        "request: expected WatchOperationRequest",
    )
    _VALIDATION.require_serialized_size(
        request,
        maximum_bytes=contract.MAX_REQUEST_BYTES,
        path="request",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, request, "watchOperationRequest", "request"
    )


def validate_watch_operation_response(
    response: operation_lifecycle_pb2.WatchOperationResponse,
) -> None:
    """Validate one complete current-state Watch response."""
    response = _VALIDATION.require_instance(
        response,
        operation_lifecycle_pb2.WatchOperationResponse,
        "response: expected WatchOperationResponse",
    )
    _VALIDATION.require_serialized_size(
        response,
        maximum_bytes=contract.MAX_RESPONSE_BYTES,
        path="response",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, response, "watchOperationResponse", "response"
    )
    validate_operation_snapshot(response.snapshot)


def validate_cancel_operation_request(
    request: operation_lifecycle_pb2.CancelOperationRequest,
) -> None:
    """Validate one idempotent cooperative cancellation request."""
    request = _VALIDATION.require_instance(
        request,
        operation_lifecycle_pb2.CancelOperationRequest,
        "request: expected CancelOperationRequest",
    )
    _VALIDATION.require_serialized_size(
        request,
        maximum_bytes=contract.MAX_REQUEST_BYTES,
        path="request",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, request, "cancelOperationRequest", "request"
    )


def validate_cancel_operation_response(
    response: operation_lifecycle_pb2.CancelOperationResponse,
) -> None:
    """Validate one atomic cancellation decision and current snapshot."""
    response = _VALIDATION.require_instance(
        response,
        operation_lifecycle_pb2.CancelOperationResponse,
        "response: expected CancelOperationResponse",
    )
    _VALIDATION.require_serialized_size(
        response,
        maximum_bytes=contract.MAX_RESPONSE_BYTES,
        path="response",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, response, "cancelOperationResponse", "response"
    )
    validate_operation_snapshot(response.snapshot)


def validate_lifecycle_error_detail(
    detail: operation_lifecycle_pb2.OperationLifecycleErrorDetail,
) -> None:
    """Validate one structured lifecycle transport failure."""
    detail = _VALIDATION.require_instance(
        detail,
        operation_lifecycle_pb2.OperationLifecycleErrorDetail,
        "error: expected OperationLifecycleErrorDetail",
    )
    _VALIDATION.require_serialized_size(
        detail,
        maximum_bytes=contract.MAX_ERROR_DETAIL_BYTES,
        path="error",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, detail, "operationLifecycleErrorDetail", "error"
    )


def validate_operation_snapshot(
    snapshot: operation_lifecycle_pb2.OperationSnapshot,
) -> None:
    """Validate one self-contained immutable operation snapshot."""
    snapshot = _VALIDATION.require_instance(
        snapshot,
        operation_lifecycle_pb2.OperationSnapshot,
        "snapshot: expected OperationSnapshot",
    )
    _VALIDATION.require_serialized_size(
        snapshot,
        maximum_bytes=contract.MAX_SNAPSHOT_BYTES,
        path="snapshot",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, snapshot, "operationSnapshot", "snapshot"
    )
    try:
        admission_validation.validate_admission_record(
            snapshot.admission_record
        )
    except admission_validation.OperationAdmissionValidationError as error:
        raise OperationLifecycleValidationError(
            "snapshot: admission record is invalid"
        ) from error

    if snapshot.state == operation_lifecycle_pb2.OPERATION_STATE_ACCEPTED:
        _VALIDATION.require_equal(
            snapshot.updated_at,
            snapshot.admission_record.admitted_at,
            "snapshot: ACCEPTED time must equal admission time",
        )
    else:
        _VALIDATION.require(
            snapshot.sequence >= _FIRST_NON_ACCEPTED_SEQUENCE,
            "snapshot: committed state requires sequence 2 or later",
        )
    if snapshot.state in {
        operation_lifecycle_pb2.OPERATION_STATE_SUCCEEDED,
        operation_lifecycle_pb2.OPERATION_STATE_CANCELLED,
    }:
        _VALIDATION.require(
            snapshot.sequence >= _FIRST_PROGRESS_SEQUENCE,
            "snapshot: success or cancellation requires an intervening state",
        )

    if snapshot.HasField("progress"):
        _VALIDATION.require(
            _FIRST_PROGRESS_SEQUENCE
            <= snapshot.progress.sequence
            <= snapshot.sequence,
            "snapshot: progress sequence is outside the retained history",
        )
        if snapshot.progress.sequence == snapshot.sequence:
            _VALIDATION.require_equal(
                snapshot.progress.updated_at,
                snapshot.updated_at,
                "snapshot: current progress time must match snapshot time",
            )
        if snapshot.state in _TERMINAL_STATES:
            _VALIDATION.require(
                snapshot.progress.sequence < snapshot.sequence,
                "snapshot: terminal commit must follow retained progress",
            )

    if snapshot.state == operation_lifecycle_pb2.OPERATION_STATE_SUCCEEDED:
        _VALIDATION.require_bounded_protojson_container(
            snapshot.success.result,
            maximum_depth=contract.MAX_RESULT_JSON_DEPTH,
            maximum_entries=contract.MAX_RESULT_CONTAINER_ENTRIES,
            nesting_message="snapshot: result nesting limit exceeded",
            container_message="snapshot: result container limit exceeded",
        )


def validate_watch_exchange(
    request: operation_lifecycle_pb2.WatchOperationRequest,
    response: operation_lifecycle_pb2.WatchOperationResponse,
) -> None:
    """Validate a Watch response against its active request and cursor."""
    validate_watch_operation_request(request)
    validate_watch_operation_response(response)
    _validate_request_response_correlation(request, response, "watch exchange")
    sequence = response.snapshot.sequence
    _VALIDATION.require(
        sequence >= request.after_sequence,
        "watch exchange: response sequence precedes the cursor",
    )
    expected_skipped = (
        request.after_sequence > 0 and sequence > request.after_sequence + 1
    )
    _VALIDATION.require_equal(
        response.updates_skipped,
        expected_skipped,
        "watch exchange: updates_skipped does not match the cursor gap",
    )


def validate_cancel_exchange(
    request: operation_lifecycle_pb2.CancelOperationRequest,
    response: operation_lifecycle_pb2.CancelOperationResponse,
) -> None:
    """Validate a cancellation response against its active request."""
    validate_cancel_operation_request(request)
    validate_cancel_operation_response(response)
    _validate_request_response_correlation(
        request, response, "cancel exchange"
    )


def validate_snapshot_transition(
    before: operation_lifecycle_pb2.OperationSnapshot,
    after: operation_lifecycle_pb2.OperationSnapshot,
) -> None:
    """Validate one adjacent committed transition without coalescing."""
    validate_operation_snapshot(before)
    validate_operation_snapshot(after)
    for previous, current, field in (
        (before.admission_record, after.admission_record, "admission record"),
        (
            before.operation_identifier,
            after.operation_identifier,
            "operation identifier",
        ),
        (
            before.manifest_revision,
            after.manifest_revision,
            "manifest revision",
        ),
    ):
        _VALIDATION.require_equal(
            current,
            previous,
            f"transition: immutable {field} changed",
        )
    _VALIDATION.require_equal(
        after.sequence,
        before.sequence + 1,
        "transition: adjacent sequence did not increase by one",
    )
    _VALIDATION.require(
        before.state not in _TERMINAL_STATES,
        "transition: terminal snapshots cannot change",
    )
    _VALIDATION.require(
        after.state in _TRANSITIONS.get(before.state, set()),
        "transition: operation state change is not allowed",
    )
    if after.state == before.state:
        _VALIDATION.require(
            after.HasField("progress")
            and after.progress != before.progress
            and after.progress.sequence == after.sequence,
            "transition: same-state commit must contain new progress",
        )
    else:
        _VALIDATION.require_equal(
            after.HasField("progress"),
            before.HasField("progress"),
            "transition: state change must retain progress presence",
        )
        if before.HasField("progress"):
            _VALIDATION.require_equal(
                after.progress,
                before.progress,
                "transition: state change must retain the latest progress",
            )


def validate_terminal_replay(
    retained: operation_lifecycle_pb2.OperationSnapshot,
    replayed: operation_lifecycle_pb2.OperationSnapshot,
) -> None:
    """Require a terminal replay to preserve every committed byte."""
    validate_operation_snapshot(retained)
    validate_operation_snapshot(replayed)
    _VALIDATION.require(
        retained.state in _TERMINAL_STATES,
        "replay: retained snapshot is not terminal",
    )
    _VALIDATION.require_equal(
        replayed,
        retained,
        "replay: terminal snapshot changed",
    )


def _validate_request_response_correlation(
    request: (
        operation_lifecycle_pb2.WatchOperationRequest
        | operation_lifecycle_pb2.CancelOperationRequest
    ),
    response: (
        operation_lifecycle_pb2.WatchOperationResponse
        | operation_lifecycle_pb2.CancelOperationResponse
    ),
    path: str,
) -> None:
    """Require current envelope and retained operation correlation."""
    binding = request.session_binding
    snapshot = response.snapshot
    for expected, actual, field in (
        (
            binding.expected_provider_instance_id,
            response.provider_instance_id,
            "Provider instance identity",
        ),
        (
            binding.expected_endpoint_generation,
            response.endpoint_generation,
            "endpoint generation",
        ),
        (binding.expected_session_id, response.session_id, "session identity"),
        (
            request.operation_id,
            snapshot.admission_record.operation_id,
            "operation identity",
        ),
        (
            request.expected_request_fingerprint,
            snapshot.admission_record.request_fingerprint,
            "request fingerprint",
        ),
    ):
        _VALIDATION.require_equal(
            actual, expected, f"{path}: {field} mismatch"
        )
