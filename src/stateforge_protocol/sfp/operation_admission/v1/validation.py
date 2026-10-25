"""Validate the complete SFP Operation Admission v1 contract."""

from __future__ import annotations

import hashlib
from typing import Final

from stateforge_protocol.sfp import _validation
from stateforge_protocol.sfp.operation_admission.v1 import (
    contract,
    operation_admission_pb2,
)

__all__ = [
    "OperationAdmissionValidationError",
    "canonical_invocation",
    "compute_request_fingerprint",
    "validate_admission_error_detail",
    "validate_admission_exchange",
    "validate_admission_record",
    "validate_start_operation_request",
    "validate_start_operation_response",
]

_SCHEMA: Final = _validation.PackagedSchema(
    package="stateforge_protocol.sfp.operation_admission.v1",
    resource="operation_admission.schema.json",
    contract_name="Operation Admission v1",
)


class OperationAdmissionValidationError(ValueError):
    """Report invalid admission data without exposing business payloads."""


_VALIDATION: Final = _validation.ValidationContext(
    OperationAdmissionValidationError
)


def validate_start_operation_request(
    request: operation_admission_pb2.StartOperationRequest,
) -> None:
    """Validate every context-independent admission request obligation."""
    request = _VALIDATION.require_instance(
        request,
        operation_admission_pb2.StartOperationRequest,
        "request: expected StartOperationRequest",
    )
    _VALIDATION.require_serialized_size(
        request,
        maximum_bytes=contract.MAX_REQUEST_BYTES,
        path="request",
    )
    _VALIDATION.require_bounded_protojson_container(
        request.invocation.payload,
        maximum_depth=contract.MAX_PAYLOAD_JSON_DEPTH,
        maximum_entries=contract.MAX_JSON_CONTAINER_ENTRIES,
        nesting_message="request: payload nesting limit exceeded",
        container_message="request: payload container limit exceeded",
    )
    _VALIDATION.require_bounded_protojson_container(
        request.invocation.execution_context,
        maximum_depth=contract.MAX_EXECUTION_CONTEXT_JSON_DEPTH,
        maximum_entries=contract.MAX_JSON_CONTAINER_ENTRIES,
        nesting_message="request: execution context nesting limit exceeded",
        container_message=(
            "request: execution context container limit exceeded"
        ),
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, request, "startOperationRequest", "request"
    )
    canonical_invocation(request.invocation)


def validate_start_operation_response(
    response: operation_admission_pb2.StartOperationResponse,
) -> None:
    """Validate every context-independent admission response obligation."""
    response = _VALIDATION.require_instance(
        response,
        operation_admission_pb2.StartOperationResponse,
        "response: expected StartOperationResponse",
    )
    _VALIDATION.require_serialized_size(
        response,
        maximum_bytes=contract.MAX_RESPONSE_BYTES,
        path="response",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, response, "startOperationResponse", "response"
    )
    validate_admission_record(response.record)
    _VALIDATION.require(
        response.record.admitted_endpoint_generation
        <= response.endpoint_generation,
        "response: admission generation is newer than the endpoint",
    )
    accepted_new = (
        response.disposition
        == operation_admission_pb2.ADMISSION_DISPOSITION_ACCEPTED_NEW
    )
    if accepted_new:
        _VALIDATION.require_equal(
            response.record.admitted_endpoint_generation,
            response.endpoint_generation,
            "response: new admission must use the current generation",
        )


def validate_admission_record(
    record: operation_admission_pb2.OperationAdmissionRecord,
) -> None:
    """Validate one immutable retained admission record."""
    record = _VALIDATION.require_instance(
        record,
        operation_admission_pb2.OperationAdmissionRecord,
        "record: expected OperationAdmissionRecord",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, record, "operationAdmissionRecord", "record"
    )
    _VALIDATION.require(
        record.record_expires_at.ToDatetime()
        > record.admitted_at.ToDatetime(),
        "record: expiry must be later than admission",
    )


def validate_admission_error_detail(
    detail: operation_admission_pb2.OperationAdmissionErrorDetail,
) -> None:
    """Validate one structured non-OK admission detail."""
    detail = _VALIDATION.require_instance(
        detail,
        operation_admission_pb2.OperationAdmissionErrorDetail,
        "error: expected OperationAdmissionErrorDetail",
    )
    _VALIDATION.require_serialized_size(
        detail,
        maximum_bytes=contract.MAX_ERROR_DETAIL_BYTES,
        path="error",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, detail, "operationAdmissionErrorDetail", "error"
    )


def validate_admission_exchange(
    request: operation_admission_pb2.StartOperationRequest,
    response: operation_admission_pb2.StartOperationResponse,
) -> None:
    """Validate a successful response against its immutable request."""
    validate_start_operation_request(request)
    validate_start_operation_response(response)
    if (
        request.admission_mode
        == operation_admission_pb2.ADMISSION_MODE_RESOLVE_ONLY
    ):
        _VALIDATION.require_equal(
            response.disposition,
            operation_admission_pb2.ADMISSION_DISPOSITION_RESOLVED_EXISTING,
            "exchange: resolve-only request cannot admit new work",
        )
    binding = request.session_binding
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
            request.invocation.contract.manifest_revision,
            response.manifest_revision,
            "manifest revision",
        ),
        (
            request.invocation.operation_id,
            response.record.operation_id,
            "operation identity",
        ),
        (
            compute_request_fingerprint(request.invocation),
            response.record.request_fingerprint,
            "request fingerprint",
        ),
    ):
        _VALIDATION.require_equal(
            actual, expected, f"exchange: {field} mismatch"
        )


def canonical_invocation(
    invocation: operation_admission_pb2.OperationInvocation,
) -> bytes:
    """Return canonical immutable invocation bytes for idempotency."""
    invocation = _VALIDATION.require_instance(
        invocation,
        operation_admission_pb2.OperationInvocation,
        "invocation: expected OperationInvocation",
    )
    projected = _VALIDATION.project_message(invocation, "invocation")
    contract_context = projected.get("contract")
    if not isinstance(contract_context, dict):
        raise OperationAdmissionValidationError(
            "invocation: contract must be an object"
        )
    roles = contract_context.get("requiredImplementationRoles")
    if not isinstance(roles, list) or not all(
        isinstance(role, str) for role in roles
    ):
        raise OperationAdmissionValidationError(
            "invocation: implementation roles must be strings"
        )
    roles.sort()
    return _VALIDATION.canonicalize_json(
        projected,
        maximum_bytes=contract.MAX_REQUEST_BYTES,
        limit_message="invocation: canonical content limit exceeded",
        invalid_message="invocation: content is not canonical JSON",
    )


def compute_request_fingerprint(
    invocation: operation_admission_pb2.OperationInvocation,
) -> str:
    """Return the canonical fingerprint for one immutable invocation."""
    digest = hashlib.sha256(canonical_invocation(invocation))
    return f"sha256:{digest.hexdigest()}"
