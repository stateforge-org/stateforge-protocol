"""Validate the complete SFP Capability Assessment v1 contract."""

from __future__ import annotations

from typing import Final

from stateforge_protocol.sfp import _validation
from stateforge_protocol.sfp.bootstrap.v1 import contract as bootstrap_contract
from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2,
    contract,
)
from stateforge_protocol.sfp.endpoint_discovery.v1 import (
    contract as discovery_contract,
)

__all__ = [
    "CapabilityAssessmentValidationError",
    "validate_assess_capabilities_request",
    "validate_assess_capabilities_response",
    "validate_assessment_exchange",
]

_REQUEST_DEFINITION: Final = "assessCapabilitiesRequest"
_RESPONSE_DEFINITION: Final = "assessCapabilitiesResponse"
_SCHEMA: Final = _validation.PackagedSchema(
    package="stateforge_protocol.sfp.capability_assessment.v1",
    resource="capability_assessment.schema.json",
    contract_name="Capability Assessment v1",
)


class CapabilityAssessmentValidationError(ValueError):
    """Report invalid assessment data without exposing rejected values."""


_VALIDATION: Final = _validation.ValidationContext(
    CapabilityAssessmentValidationError
)


def validate_assess_capabilities_request(
    request: capability_assessment_pb2.AssessCapabilitiesRequest,
) -> None:
    """Validate every context-independent assessment request obligation."""
    request = _VALIDATION.require_instance(
        request,
        capability_assessment_pb2.AssessCapabilitiesRequest,
        "request: expected AssessCapabilitiesRequest",
    )
    _VALIDATION.require_bounded_protojson_container(
        request.execution_context,
        maximum_depth=contract.MAX_EXECUTION_CONTEXT_JSON_DEPTH,
        maximum_entries=contract.MAX_EXECUTION_CONTEXT_CONTAINER_ENTRIES,
        nesting_message="request: execution context nesting limit exceeded",
        container_message=(
            "request: execution context container limit exceeded"
        ),
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA,
        request,
        _REQUEST_DEFINITION,
        "request",
    )
    _VALIDATION.require_canonical_uuid4(
        request.assessment_request_id,
        "request: assessment identity must be a canonical UUIDv4",
    )
    _VALIDATION.require_canonical_uuid4(
        request.expected_provider_instance_id,
        "request: Provider identity must be a canonical UUIDv4",
    )
    _VALIDATION.require(
        discovery_contract.is_allocated_endpoint_generation(
            request.expected_endpoint_generation
        ),
        "request: endpoint generation must be allocated",
    )
    _VALIDATION.require_code_point_length(
        request.expected_session_id,
        minimum=1,
        maximum=bootstrap_contract.MAX_SESSION_ID_CODE_POINTS,
        message="request: session identity is outside the SFP v1 contract",
    )
    _VALIDATION.require_unique(
        tuple(request.operation_identifiers),
        "request: operation identifiers must be unique",
    )


def validate_assess_capabilities_response(
    response: capability_assessment_pb2.AssessCapabilitiesResponse,
) -> None:
    """Validate every context-independent assessment response obligation."""
    response = _VALIDATION.require_instance(
        response,
        capability_assessment_pb2.AssessCapabilitiesResponse,
        "response: expected AssessCapabilitiesResponse",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA,
        response,
        _RESPONSE_DEFINITION,
        "response",
    )
    for value, message in (
        (
            response.assessment_request_id,
            "response: assessment request identity must be a canonical UUIDv4",
        ),
        (
            response.provider_instance_id,
            "response: Provider identity must be a canonical UUIDv4",
        ),
        (
            response.assessment_id,
            "response: assessment identity must be a canonical UUIDv4",
        ),
    ):
        _VALIDATION.require_canonical_uuid4(value, message)
    _VALIDATION.require(
        discovery_contract.is_allocated_endpoint_generation(
            response.endpoint_generation
        ),
        "response: endpoint generation must be allocated",
    )
    _VALIDATION.require_code_point_length(
        response.session_id,
        minimum=1,
        maximum=bootstrap_contract.MAX_SESSION_ID_CODE_POINTS,
        message="response: session identity is outside the SFP v1 contract",
    )
    _validate_response_findings(response)


def validate_assessment_exchange(
    request: capability_assessment_pb2.AssessCapabilitiesRequest,
    response: capability_assessment_pb2.AssessCapabilitiesResponse,
) -> None:
    """Validate request/response correlation and finding completeness."""
    validate_assess_capabilities_request(request)
    validate_assess_capabilities_response(response)
    _validate_exchange_correlation(request, response)
    _validate_operation_finding_coverage(request, response)


def _validate_response_findings(
    response: capability_assessment_pb2.AssessCapabilitiesResponse,
) -> None:
    """Enforce uniqueness within the normalized finding collection."""
    _VALIDATION.require_unique(
        tuple(finding.operation_identifier for finding in response.findings),
        "response: operation findings must be unique",
    )
    for finding in response.findings:
        _VALIDATION.require_unique(
            tuple(
                item.requirement_id for item in finding.requirement_findings
            ),
            "response: requirement identifiers must be unique per finding",
        )
        _VALIDATION.require_unique(
            tuple(item.reason_code for item in finding.reasons),
            "response: reason codes must be unique per finding",
        )
        _VALIDATION.require_unique(
            tuple(item.constraint_id for item in finding.constraints),
            "response: constraint identifiers must be unique per finding",
        )


def _validate_exchange_correlation(
    request: capability_assessment_pb2.AssessCapabilitiesRequest,
    response: capability_assessment_pb2.AssessCapabilitiesResponse,
) -> None:
    """Require response fencing fields to match their request."""
    for request_value, response_value, name in (
        (
            request.assessment_request_id,
            response.assessment_request_id,
            "assessment request identity",
        ),
        (
            request.expected_provider_instance_id,
            response.provider_instance_id,
            "Provider instance identity",
        ),
        (
            request.expected_endpoint_generation,
            response.endpoint_generation,
            "endpoint generation",
        ),
        (request.expected_session_id, response.session_id, "session identity"),
        (
            request.expected_manifest_revision,
            response.manifest_revision,
            "manifest revision",
        ),
    ):
        _VALIDATION.require_equal(
            request_value,
            response_value,
            f"exchange: {name} mismatch",
        )
    _VALIDATION.require(
        response.assessment_id != request.assessment_request_id,
        "exchange: assessment identity must be independently minted",
    )


def _validate_operation_finding_coverage(
    request: capability_assessment_pb2.AssessCapabilitiesRequest,
    response: capability_assessment_pb2.AssessCapabilitiesResponse,
) -> None:
    """Require one ordered finding for every requested operation."""
    requested = tuple(request.operation_identifiers)
    returned = tuple(
        finding.operation_identifier for finding in response.findings
    )
    requested_set = set(requested)
    returned_set = set(returned)
    _VALIDATION.require(
        not requested_set - returned_set,
        "exchange: operation findings are missing",
    )
    _VALIDATION.require(
        not returned_set - requested_set,
        "exchange: operation findings contain additional operations",
    )
    _VALIDATION.require_equal(
        requested,
        returned,
        "exchange: operation findings are not in request order",
    )
