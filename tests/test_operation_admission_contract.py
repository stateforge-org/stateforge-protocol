"""Conformance vectors for operation admission and idempotency."""

import copy
import hashlib
import json
from datetime import datetime
from importlib.resources import files
from pathlib import Path

import pytest
import rfc8785
from google.protobuf import json_format
from jsonschema import Draft202012Validator, ValidationError

from stateforge_protocol.sfp.operation_admission.v1 import (
    contract,
    operation_admission_pb2,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "operation_admission"
_SCHEMA = json.loads(
    files("stateforge_protocol.sfp.operation_admission.v1")
    .joinpath("operation_admission.schema.json")
    .read_text()
)
_REQUEST_SCHEMA = {
    "$ref": "#/$defs/startOperationRequest",
    "$defs": _SCHEMA["$defs"],
}
_ERROR_SCHEMA = {
    "$ref": "#/$defs/operationAdmissionErrorDetail",
    "$defs": _SCHEMA["$defs"],
}
_REQUEST_VALIDATOR = Draft202012Validator(_REQUEST_SCHEMA)
_RESPONSE_VALIDATOR = Draft202012Validator(_SCHEMA)
_ERROR_VALIDATOR = Draft202012Validator(_ERROR_SCHEMA)


def _read_json(name: str):
    return json.loads((_FIXTURES / name).read_text())


def _canonical_invocation(request_data: dict) -> bytes:
    request = json_format.ParseDict(
        request_data,
        operation_admission_pb2.StartOperationRequest(),
    )
    projection = json_format.MessageToDict(
        request.invocation,
        always_print_fields_with_no_presence=True,
    )
    projection["contract"]["requiredImplementationRoles"].sort()
    return rfc8785.dumps(projection)


def _fingerprint(request_data: dict) -> str:
    digest = hashlib.sha256(_canonical_invocation(request_data)).hexdigest()
    return f"sha256:{digest}"


@pytest.fixture
def request_data():
    return _read_json("request.json")


@pytest.fixture
def accepted_response():
    return _read_json("response-accepted-new.json")


@pytest.fixture
def resolved_response():
    return _read_json("response-resolved-existing.json")


def test_validation_schema_is_valid() -> None:
    Draft202012Validator.check_schema(_SCHEMA)


def test_versioned_contract_exposes_normative_limits() -> None:
    expected = {
        "MAX_REQUEST_BYTES": 8 * 1024 * 1024,
        "MAX_RESPONSE_BYTES": 1 * 1024 * 1024,
        "MAX_ERROR_DETAIL_BYTES": 4 * 1024,
        "MAX_PAYLOAD_JSON_DEPTH": 64,
        "MAX_EXECUTION_CONTEXT_JSON_DEPTH": 64,
        "MAX_JSON_CONTAINER_ENTRIES": 256,
        "MAX_REQUIRED_IMPLEMENTATION_ROLES": 16,
    }

    assert {name: getattr(contract, name) for name in expected} == expected


def test_versioned_contract_limits_match_packaged_schema() -> None:
    definitions = _SCHEMA["$defs"]

    assert (
        definitions["boundedArray"]["maxItems"]
        == contract.MAX_JSON_CONTAINER_ENTRIES
    )
    assert (
        definitions["boundedObject"]["maxProperties"]
        == contract.MAX_JSON_CONTAINER_ENTRIES
    )
    assert (
        definitions["operationContractContext"]["properties"][
            "requiredImplementationRoles"
        ]["maxItems"]
        == contract.MAX_REQUIRED_IMPLEMENTATION_ROLES
    )


def test_request_round_trip_preserves_complete_projection(
    request_data,
) -> None:
    _REQUEST_VALIDATOR.validate(request_data)
    message = json_format.ParseDict(
        request_data,
        operation_admission_pb2.StartOperationRequest(),
    )
    decoded = operation_admission_pb2.StartOperationRequest.FromString(
        message.SerializeToString()
    )
    projected = json_format.MessageToDict(
        decoded,
        always_print_fields_with_no_presence=True,
    )

    assert decoded == message
    assert projected == request_data


@pytest.mark.parametrize(
    "fixture_name",
    ["response-accepted-new.json", "response-resolved-existing.json"],
)
def test_response_round_trip_preserves_complete_projection(
    fixture_name,
) -> None:
    response = _read_json(fixture_name)
    _RESPONSE_VALIDATOR.validate(response)
    message = json_format.ParseDict(
        response,
        operation_admission_pb2.StartOperationResponse(),
    )
    decoded = operation_admission_pb2.StartOperationResponse.FromString(
        message.SerializeToString()
    )
    projected = json_format.MessageToDict(
        decoded,
        always_print_fields_with_no_presence=True,
    )

    assert decoded == message
    assert projected == response


def test_proto_defaults_are_not_valid_wildcards() -> None:
    empty = operation_admission_pb2.StartOperationRequest.FromString(b"")
    projected = json_format.MessageToDict(
        empty,
        always_print_fields_with_no_presence=True,
    )

    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(projected)


@pytest.mark.parametrize(
    "fixture_name",
    ["invalid/default-request.json", "invalid/payload-array-request.json"],
)
def test_invalid_request_fixtures_are_rejected(fixture_name) -> None:
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(_read_json(fixture_name))


def test_service_is_versioned_unary_and_admission_only() -> None:
    service = operation_admission_pb2.DESCRIPTOR.services_by_name[
        "OperationAdmissionService"
    ]
    method = service.methods_by_name["StartOperation"]

    assert service.full_name == contract.SERVICE_NAME
    assert tuple(service.methods_by_name) == ("StartOperation",)
    assert method.input_type == (
        operation_admission_pb2.StartOperationRequest.DESCRIPTOR
    )
    assert method.output_type == (
        operation_admission_pb2.StartOperationResponse.DESCRIPTOR
    )
    assert not method.client_streaming
    assert not method.server_streaming


def test_invocation_and_session_controls_are_structurally_separate() -> None:
    request_fields = {
        field.name: field
        for field in (
            operation_admission_pb2.StartOperationRequest.DESCRIPTOR.fields
        )
    }
    invocation_fields = {
        field.name
        for field in (
            operation_admission_pb2.OperationInvocation.DESCRIPTOR.fields
        )
    }

    assert set(request_fields) == {
        "session_binding",
        "invocation",
        "admission_mode",
    }
    assert request_fields["session_binding"].message_type == (
        operation_admission_pb2.OperationSessionBinding.DESCRIPTOR
    )
    assert request_fields["invocation"].message_type == (
        operation_admission_pb2.OperationInvocation.DESCRIPTOR
    )
    assert {
        "operation_id",
        "operation_identifier",
        "payload",
        "execution_deadline",
        "contract",
        "execution_context",
    } == invocation_fields
    assert (
        not {
            "expected_session_id",
            "expected_endpoint_generation",
            "admission_mode",
        }
        & invocation_fields
    )


def test_invocation_has_no_generic_target_field_or_message(
    request_data,
) -> None:
    assert "target" not in (
        operation_admission_pb2.OperationInvocation.DESCRIPTOR.fields_by_name
    )
    assert "OperationTarget" not in (
        operation_admission_pb2.DESCRIPTOR.message_types_by_name
    )
    assert "operationTarget" not in _SCHEMA["$defs"]

    obsolete = copy.deepcopy(request_data)
    obsolete["invocation"]["target"] = {
        "targetKind": "example.database/cluster@1",
        "configuration": {},
    }
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(obsolete)
    with pytest.raises(json_format.ParseError):
        json_format.ParseDict(
            obsolete,
            operation_admission_pb2.StartOperationRequest(),
        )


def test_resource_selection_is_operation_specific_payload(
    request_data,
) -> None:
    invocation = request_data["invocation"]
    resource_schema = {
        "type": "object",
        "properties": {
            "resource": {
                "type": "object",
                "properties": {"cluster": {"type": "string"}},
                "required": ["cluster"],
            }
        },
        "required": ["resource"],
    }
    Draft202012Validator(resource_schema).validate(invocation["payload"])

    without_resource = copy.deepcopy(request_data)
    without_resource["invocation"]["operationIdentifier"] = (
        "example.utility/heartbeat.ping@1"
    )
    without_resource["invocation"]["payload"] = {}
    without_resource["invocation"]["contract"][
        "requiredImplementationRoles"
    ] = []
    _REQUEST_VALIDATOR.validate(without_resource)
    json_format.ParseDict(
        without_resource,
        operation_admission_pb2.StartOperationRequest(),
    )
    Draft202012Validator({"type": "object", "maxProperties": 0}).validate(
        without_resource["invocation"]["payload"]
    )


def test_p4_does_not_define_lifecycle_or_cancellation_rpc() -> None:
    names = " ".join(
        [
            *operation_admission_pb2.DESCRIPTOR.message_types_by_name,
            *operation_admission_pb2.DESCRIPTOR.enum_types_by_name,
            *operation_admission_pb2.DESCRIPTOR.services_by_name,
        ]
    ).lower()

    for forbidden in ("watch", "progress", "cancel", "terminalresult"):
        assert forbidden not in names


def test_success_dispositions_are_closed_and_complete() -> None:
    values = {
        value.name
        for value in (
            operation_admission_pb2.AdmissionDisposition.DESCRIPTOR.values
        )
    }

    assert values == {
        "ADMISSION_DISPOSITION_UNSPECIFIED",
        "ADMISSION_DISPOSITION_ACCEPTED_NEW",
        "ADMISSION_DISPOSITION_RESOLVED_EXISTING",
    }


def test_admission_modes_include_a_non_dispatching_resolution_mode() -> None:
    values = {
        value.name
        for value in operation_admission_pb2.AdmissionMode.DESCRIPTOR.values
    }

    assert values == {
        "ADMISSION_MODE_UNSPECIFIED",
        "ADMISSION_MODE_ADMIT_OR_RESOLVE",
        "ADMISSION_MODE_RESOLVE_ONLY",
    }


def test_golden_fingerprint_vector(request_data) -> None:
    vector = _read_json("fingerprint-vector.json")
    canonical = _canonical_invocation(request_data)

    assert canonical.decode() == vector["canonicalJson"]
    assert _fingerprint(request_data) == vector["fingerprint"]


def test_required_role_order_is_not_semantic(request_data) -> None:
    reordered = copy.deepcopy(request_data)
    reordered["invocation"]["contract"][
        "requiredImplementationRoles"
    ].reverse()

    assert _fingerprint(reordered) == _fingerprint(request_data)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("operationId",), "33333333-3333-4333-8333-333333333333"),
        (("operationIdentifier",), "example.database/index.rebuild@1"),
        (("payload", "resource", "cluster"), "secondary"),
        (("payload", "resource", "region"), "us-east-1"),
        (("payload", "mode"), "offline"),
        (("executionDeadline",), "2026-09-20T13:00:00Z"),
        (
            ("contract", "manifestRevision"),
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ),
        (("executionContext", "authority"), "policy-run-456"),
    ],
)
def test_every_immutable_semantic_change_changes_fingerprint(
    request_data,
    path,
    replacement,
) -> None:
    changed = copy.deepcopy(request_data)
    cursor = changed["invocation"]
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = replacement

    assert _fingerprint(changed) != _fingerprint(request_data)


def test_reconnect_and_resolution_controls_do_not_change_fingerprint(
    request_data,
) -> None:
    retry = copy.deepcopy(request_data)
    retry["sessionBinding"]["expectedSessionId"] = "new-session-same-gen"
    retry["admissionMode"] = "ADMISSION_MODE_RESOLVE_ONLY"

    assert _fingerprint(retry) == _fingerprint(request_data)


def test_response_record_matches_request_and_golden_fingerprint(
    request_data,
    accepted_response,
) -> None:
    record = accepted_response["record"]

    assert record["operationId"] == request_data["invocation"]["operationId"]
    assert record["requestFingerprint"] == _fingerprint(request_data)
    assert (
        accepted_response["manifestRevision"]
        == (request_data["invocation"]["contract"]["manifestRevision"])
    )
    assert (
        accepted_response["endpointGeneration"]
        == (request_data["sessionBinding"]["expectedEndpointGeneration"])
    )


def test_resolved_retry_returns_the_same_immutable_record(
    accepted_response,
    resolved_response,
) -> None:
    assert accepted_response["record"] == resolved_response["record"]
    assert accepted_response["sessionId"] != resolved_response["sessionId"]
    assert accepted_response["disposition"] == (
        "ADMISSION_DISPOSITION_ACCEPTED_NEW"
    )
    assert resolved_response["disposition"] == (
        "ADMISSION_DISPOSITION_RESOLVED_EXISTING"
    )


def test_record_expiry_is_after_admission(accepted_response) -> None:
    record = accepted_response["record"]
    admitted = datetime.fromisoformat(
        record["admittedAt"].replace("Z", "+00:00")
    )
    expires = datetime.fromisoformat(
        record["recordExpiresAt"].replace("Z", "+00:00")
    )

    assert expires > admitted


def test_error_fixture_covers_every_reason_and_creates_no_record() -> None:
    cases = _read_json("error-cases.json")
    documented_reasons = {case["reason"] for case in cases}
    wire_reasons = {
        value.name
        for value in (
            operation_admission_pb2.AdmissionErrorReason.DESCRIPTOR.values
        )
        if value.number != 0
    }

    assert documented_reasons == wire_reasons
    assert all(case["createsAcceptedRecord"] is False for case in cases)
    assert {case["grpcStatus"] for case in cases} == {
        "ALREADY_EXISTS",
        "DEADLINE_EXCEEDED",
        "FAILED_PRECONDITION",
        "INVALID_ARGUMENT",
        "RESOURCE_EXHAUSTED",
        "UNAVAILABLE",
        "UNIMPLEMENTED",
    }


@pytest.mark.parametrize("case", _read_json("error-cases.json"))
def test_error_detail_round_trips_for_every_documented_case(case) -> None:
    detail = {
        "operationId": "22222222-2222-4222-8222-222222222222",
        "reason": case["reason"],
        "retryable": case["retryable"],
        "explanation": case["condition"],
    }
    if case["retryable"]:
        detail["retryAfter"] = "5s"
    _ERROR_VALIDATOR.validate(detail)
    message = json_format.ParseDict(
        detail,
        operation_admission_pb2.OperationAdmissionErrorDetail(),
    )
    projected = json_format.MessageToDict(
        message,
        always_print_fields_with_no_presence=True,
    )

    assert projected == detail


def test_retry_after_is_forbidden_for_non_retryable_error() -> None:
    detail = {
        "operationId": "22222222-2222-4222-8222-222222222222",
        "reason": "ADMISSION_ERROR_REASON_IDEMPOTENCY_CONFLICT",
        "retryable": False,
        "retryAfter": "5s",
        "explanation": "Same ID has different immutable content.",
    }

    with pytest.raises(ValidationError):
        _ERROR_VALIDATOR.validate(detail)


def test_scenarios_cover_required_idempotency_boundaries() -> None:
    scenarios = {
        item["scenario"]: item
        for item in _read_json("admission-scenarios.json")
    }

    assert set(scenarios) == {
        "first_admission",
        "equivalent_retry",
        "concurrent_duplicate",
        "changed_payload_or_context",
        "terminal_record_replay",
        "deadline_before_admission",
        "lost_state_after_generation_change",
        "expired_record",
    }
    assert scenarios["concurrent_duplicate"]["dispatchCount"] == 1
    assert scenarios["equivalent_retry"]["dispatchCount"] == 0
    assert scenarios["terminal_record_replay"]["dispatchCount"] == 0
    assert scenarios["lost_state_after_generation_change"]["mode"] == (
        "ADMISSION_MODE_RESOLVE_ONLY"
    )
    assert (
        scenarios["lost_state_after_generation_change"]["dispatchCount"] == 0
    )


def test_generation_outside_uint64_cannot_enter_wire_message() -> None:
    with pytest.raises(ValueError, match="range"):
        operation_admission_pb2.OperationSessionBinding(
            expected_endpoint_generation=2**64
        )


def test_duplicate_required_roles_are_structurally_invalid(
    request_data,
) -> None:
    duplicate = copy.deepcopy(request_data)
    roles = duplicate["invocation"]["contract"]["requiredImplementationRoles"]
    roles.append(roles[0])

    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(duplicate)
