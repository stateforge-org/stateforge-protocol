"""Executable semantic validation for Capability Assessment v1."""

import json
from pathlib import Path

import pytest
from google.protobuf.json_format import ParseDict

from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2,
    contract,
    validation,
)
from stateforge_protocol.sfp.endpoint_discovery.v1 import (
    contract as discovery_contract,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "capability_assessment"


def _document(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _request(
    document: dict[str, object] | None = None,
) -> capability_assessment_pb2.AssessCapabilitiesRequest:
    return ParseDict(
        document or _document("request.json"),
        capability_assessment_pb2.AssessCapabilitiesRequest(),
    )


def _response(
    document: dict[str, object] | None = None,
) -> capability_assessment_pb2.AssessCapabilitiesResponse:
    return ParseDict(
        document or _document("response-mixed-states.json"),
        capability_assessment_pb2.AssessCapabilitiesResponse(),
    )


def _set_nested_context(
    request: capability_assessment_pb2.AssessCapabilitiesRequest,
    depth: int,
) -> None:
    container = request.execution_context
    for level in range(depth):
        if level == depth - 1:
            container.fields["leaf"].string_value = "value"
        else:
            container = container.fields["nested"].struct_value


def test_validates_complete_request_response_and_exchange() -> None:
    request = _request()
    response = _response()

    assert validation.validate_assess_capabilities_request(request) is None
    assert validation.validate_assess_capabilities_response(response) is None
    assert validation.validate_assessment_exchange(request, response) is None


@pytest.mark.parametrize("message", [object(), None, "request"])
def test_rejects_wrong_request_message_type(message: object) -> None:
    with pytest.raises(validation.CapabilityAssessmentValidationError):
        validation.validate_assess_capabilities_request(message)  # type: ignore[arg-type]


@pytest.mark.parametrize("message", [object(), None, "response"])
def test_rejects_wrong_response_message_type(message: object) -> None:
    with pytest.raises(validation.CapabilityAssessmentValidationError):
        validation.validate_assess_capabilities_response(message)  # type: ignore[arg-type]


def test_rejects_invalid_request_schema_projection() -> None:
    request = _request()
    request.ClearField("operation_identifiers")

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="request: violates",
    ):
        validation.validate_assess_capabilities_request(request)


def test_rejects_invalid_response_schema_projection() -> None:
    response = _response()
    response.findings[
        0
    ].support_state = capability_assessment_pb2.SUPPORT_STATE_UNSPECIFIED

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="response: violates",
    ):
        validation.validate_assess_capabilities_response(response)


@pytest.mark.parametrize(
    ("name", "message_type", "validator"),
    [
        (
            "duplicate-operation-request.json",
            capability_assessment_pb2.AssessCapabilitiesRequest,
            validation.validate_assess_capabilities_request,
        ),
        (
            "invariant-violation-response.json",
            capability_assessment_pb2.AssessCapabilitiesResponse,
            validation.validate_assess_capabilities_response,
        ),
        (
            "unspecified-support-state-response.json",
            capability_assessment_pb2.AssessCapabilitiesResponse,
            validation.validate_assess_capabilities_response,
        ),
    ],
)
def test_rejects_invalid_conformance_fixture(
    name: str,
    message_type,
    validator,
) -> None:
    document = json.loads(
        (_FIXTURES / "invalid" / name).read_text(encoding="utf-8")
    )
    message = ParseDict(document, message_type())

    with pytest.raises(validation.CapabilityAssessmentValidationError):
        validator(message)


def test_execution_context_accepts_exact_depth_limit() -> None:
    request = _request()
    _set_nested_context(request, contract.MAX_EXECUTION_CONTEXT_JSON_DEPTH)

    validation.validate_assess_capabilities_request(request)


def test_execution_context_rejects_excessive_depth_before_schema() -> None:
    request = _request()
    _set_nested_context(request, contract.MAX_EXECUTION_CONTEXT_JSON_DEPTH + 1)

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="nesting limit",
    ):
        validation.validate_assess_capabilities_request(request)


def test_execution_context_rejects_excessive_breadth() -> None:
    request = _request()
    request.ClearField("execution_context")
    for index in range(contract.MAX_EXECUTION_CONTEXT_CONTAINER_ENTRIES + 1):
        request.execution_context.fields[f"key_{index}"].string_value = "value"

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="container limit",
    ):
        validation.validate_assess_capabilities_request(request)


def test_execution_context_rejects_oversized_value() -> None:
    request = _request()
    request.execution_context.fields["value"].string_value = "x" * 2049

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="request: violates",
    ):
        validation.validate_assess_capabilities_request(request)


def test_rejects_generation_outside_discovery_contract() -> None:
    request = _request()
    request.expected_endpoint_generation = (
        discovery_contract.MAX_ENDPOINT_GENERATION + 1
    )

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="generation",
    ):
        validation.validate_assess_capabilities_request(request)


@pytest.mark.parametrize(
    ("collection", "error"),
    [
        ("requirement_findings", "requirement identifiers"),
        ("reasons", "reason codes"),
        ("constraints", "constraint identifiers"),
    ],
)
def test_rejects_duplicate_finding_detail_identifiers(
    collection: str,
    error: str,
) -> None:
    response = _response()
    finding = response.findings[1]
    values = getattr(finding, collection)
    if not values:
        finding = response.findings[2]
        values = getattr(finding, collection)
    values.add().CopyFrom(values[0])

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match=error,
    ):
        validation.validate_assess_capabilities_response(response)


def test_rejects_duplicate_operation_findings() -> None:
    response = _response()
    response.findings[1].operation_identifier = response.findings[
        0
    ].operation_identifier

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="operation findings",
    ):
        validation.validate_assess_capabilities_response(response)


@pytest.mark.parametrize(
    "mismatch",
    [
        "request-id",
        "provider-id",
        "generation",
        "session",
        "manifest",
    ],
)
def test_rejects_exchange_correlation_mismatch(mismatch: str) -> None:
    request = _request()
    response = _response()
    if mismatch == "request-id":
        response.assessment_request_id = "241232a9-42d9-43b0-a0de-524e36d56075"
    elif mismatch == "provider-id":
        response.provider_instance_id = "738c2ebc-0f0f-40dc-a483-f83400685bbe"
    elif mismatch == "generation":
        response.endpoint_generation += 1
    elif mismatch == "session":
        response.session_id = "different-session"
    else:
        response.manifest_revision = "sha256:" + ("0" * 64)

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match=r"exchange: .* mismatch",
    ):
        validation.validate_assessment_exchange(request, response)


def test_rejects_assessment_identity_derived_from_request() -> None:
    request = _request()
    response = _response()
    response.assessment_id = request.assessment_request_id

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="independently minted",
    ):
        validation.validate_assessment_exchange(request, response)


def test_rejects_missing_operation_finding() -> None:
    request = _request()
    response = _response()
    del response.findings[-1]

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="findings are missing",
    ):
        validation.validate_assessment_exchange(request, response)


def test_rejects_additional_operation_finding() -> None:
    request = _request()
    response = _response()
    extra = response.findings.add()
    extra.CopyFrom(response.findings[0])
    extra.operation_identifier = "example.vendor/additional@1"

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="additional operations",
    ):
        validation.validate_assessment_exchange(request, response)


def test_rejects_reordered_operation_findings() -> None:
    request = _request()
    response = _response()
    first = capability_assessment_pb2.CapabilityFinding()
    second = capability_assessment_pb2.CapabilityFinding()
    first.CopyFrom(response.findings[0])
    second.CopyFrom(response.findings[1])
    response.findings[0].CopyFrom(second)
    response.findings[1].CopyFrom(first)

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="request order",
    ):
        validation.validate_assessment_exchange(request, response)


def test_rejects_invalid_timestamp_with_protocol_error() -> None:
    response = _response()
    response.assessment_timestamp.seconds = 253402300800

    with pytest.raises(
        validation.CapabilityAssessmentValidationError,
        match="response:",
    ):
        validation.validate_assess_capabilities_response(response)


def test_validation_errors_do_not_echo_rejected_values() -> None:
    request = _request()
    secret = "sensitive-canary-never-in-errors"  # noqa: S105
    request.assessment_request_id = secret

    with pytest.raises(
        validation.CapabilityAssessmentValidationError
    ) as error:
        validation.validate_assess_capabilities_request(request)

    assert secret not in str(error.value)
