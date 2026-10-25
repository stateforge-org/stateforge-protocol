"""Conformance vectors for the capability-assessment wire and schema."""

import copy
import hashlib
import json
import re
from importlib.resources import files
from pathlib import Path

import pytest
import rfc8785
from google.protobuf import json_format
from jsonschema import Draft202012Validator, ValidationError

from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2,
    contract,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "capability_assessment"
_SCHEMA = json.loads(
    files("stateforge_protocol.sfp.capability_assessment.v1")
    .joinpath("capability_assessment.schema.json")
    .read_text()
)
_REQUEST_SCHEMA = {
    "$ref": "#/$defs/assessCapabilitiesRequest",
    "$defs": _SCHEMA["$defs"],
}
_REQUEST_VALIDATOR = Draft202012Validator(_REQUEST_SCHEMA)
_FINDING_SCHEMA = {
    "$ref": "#/$defs/capabilityFinding",
    "$defs": _SCHEMA["$defs"],
}
_REQUIREMENT_SCHEMA = {
    "$ref": "#/$defs/requirementFinding",
    "$defs": _SCHEMA["$defs"],
}
_MANIFEST_SCHEMA = json.loads(
    files("stateforge_protocol.sfp.manifest.v1")
    .joinpath("manifest.schema.json")
    .read_text()
)
_CANONICAL_REASON_CODES = {
    "REASON_CODE_ACCESS_DENIED": (
        "stateforge.capability_assessment.v1.access_denied"
    ),
    "REASON_CODE_PERMISSION_UNCERTAIN": (
        "stateforge.capability_assessment.v1.permission_uncertain"
    ),
    "REASON_CODE_UNSUPPORTED_VENDOR_STATE": (
        "stateforge.capability_assessment.v1.unsupported_vendor_state"
    ),
    "REASON_CODE_INSUFFICIENT_EVIDENCE": (
        "stateforge.capability_assessment.v1.insufficient_evidence"
    ),
    "REASON_CODE_REQUIREMENT_UNMET": (
        "stateforge.capability_assessment.v1.requirement_unmet"
    ),
}


def _container_depth(value) -> int:
    maximum = 0
    pending = [(value, 0)]
    while pending:
        current, parent_depth = pending.pop()
        if isinstance(current, dict):
            depth = parent_depth + 1
            maximum = max(maximum, depth)
            pending.extend((item, depth) for item in current.values())
        elif isinstance(current, list):
            depth = parent_depth + 1
            maximum = max(maximum, depth)
            pending.extend((item, depth) for item in current)
    return maximum


def _nested_context(depth: int):
    value = "leaf"
    for _ in range(depth):
        value = {"nested": value}
    return value


@pytest.fixture
def response():
    return json.loads((_FIXTURES / "response-mixed-states.json").read_text())


@pytest.fixture
def request_data():
    return json.loads((_FIXTURES / "request.json").read_text())


@pytest.fixture
def manifest_response():
    return json.loads((_FIXTURES / "accepted-manifest.json").read_text())


@pytest.fixture
def validator():
    return Draft202012Validator(_SCHEMA)


def test_validation_schema_is_valid() -> None:
    Draft202012Validator.check_schema(_SCHEMA)


def test_versioned_contract_exposes_normative_limits() -> None:
    expected = {
        "MAX_REQUEST_BYTES": 8 * 1024 * 1024,
        "MAX_RESPONSE_BYTES": 16 * 1024 * 1024,
        "MAX_EXECUTION_CONTEXT_JSON_DEPTH": 64,
        "MAX_EXECUTION_CONTEXT_CONTAINER_ENTRIES": 32,
        "MAX_OPERATION_IDENTIFIERS": 64,
        "MAX_REQUIREMENT_FINDINGS_PER_OPERATION": 64,
        "MAX_REASONS_PER_OPERATION": 16,
        "MAX_CONSTRAINTS_PER_OPERATION": 32,
    }

    assert {name: getattr(contract, name) for name in expected} == expected


def test_versioned_contract_exposes_canonical_reason_codes() -> None:
    assert {
        name: getattr(contract, name) for name in _CANONICAL_REASON_CODES
    } == _CANONICAL_REASON_CODES

    procedure = Path("docs/procedures/capability-assessment.md").read_text()
    reason_section = procedure.split("### Reason-code vocabulary", 1)[1].split(
        "## Structural and semantic validation", 1
    )[0]
    documented = set(
        re.findall(r"^\| `([^`]+)` \|", reason_section, flags=re.MULTILINE)
    )
    assert documented == set(_CANONICAL_REASON_CODES.values())


def test_versioned_contract_limits_match_packaged_schema() -> None:
    definitions = _SCHEMA["$defs"]
    finding = definitions["capabilityFinding"]["properties"]
    request = definitions["assessCapabilitiesRequest"]["properties"]

    assert (
        definitions["boundedArray"]["maxItems"]
        == contract.MAX_EXECUTION_CONTEXT_CONTAINER_ENTRIES
    )
    assert (
        definitions["boundedNestedObject"]["maxProperties"]
        == contract.MAX_EXECUTION_CONTEXT_CONTAINER_ENTRIES
    )
    assert (
        request["operationIdentifiers"]["maxItems"]
        == contract.MAX_OPERATION_IDENTIFIERS
    )
    assert (
        finding["requirementFindings"]["maxItems"]
        == contract.MAX_REQUIREMENT_FINDINGS_PER_OPERATION
    )
    assert finding["reasons"]["maxItems"] == contract.MAX_REASONS_PER_OPERATION
    assert (
        finding["constraints"]["maxItems"]
        == contract.MAX_CONSTRAINTS_PER_OPERATION
    )


# -- Wire round trips --------------------------------------------------


def test_response_round_trip_preserves_structure(response, validator):
    validator.validate(response)
    message = json_format.ParseDict(
        response, capability_assessment_pb2.AssessCapabilitiesResponse()
    )
    decoded = capability_assessment_pb2.AssessCapabilitiesResponse.FromString(
        message.SerializeToString()
    )
    projected = json_format.MessageToDict(
        decoded, always_print_fields_with_no_presence=True
    )

    assert decoded == message
    assert projected == response


def test_request_round_trip_and_operation_order(request_data) -> None:
    _REQUEST_VALIDATOR.validate(request_data)
    message = json_format.ParseDict(
        request_data, capability_assessment_pb2.AssessCapabilitiesRequest()
    )
    decoded = capability_assessment_pb2.AssessCapabilitiesRequest.FromString(
        message.SerializeToString()
    )

    assert decoded == message
    assert (
        list(decoded.operation_identifiers)
        == request_data["operationIdentifiers"]
    )


def test_generation_outside_uint64_cannot_enter_wire_message() -> None:
    with pytest.raises(ValueError, match="range"):
        capability_assessment_pb2.AssessCapabilitiesRequest(
            expected_endpoint_generation=2**64
        )


def test_protobuf_decoding_does_not_perform_semantic_validation(validator):
    # Proto3 accepts defaults. Consumers must run schema and session checks
    # before trusting a response, regardless of channel health.
    empty = capability_assessment_pb2.AssessCapabilitiesResponse.FromString(
        b""
    )
    with pytest.raises(ValidationError):
        validator.validate(
            json_format.MessageToDict(
                empty, always_print_fields_with_no_presence=True
            )
        )


# -- Service and message shape -----------------------------------------


def test_service_is_versioned_and_unary() -> None:
    service = capability_assessment_pb2.DESCRIPTOR.services_by_name[
        "CapabilityAssessmentService"
    ]
    method = service.methods_by_name["AssessCapabilities"]

    assert service.full_name == contract.SERVICE_NAME
    assert tuple(service.methods_by_name) == ("AssessCapabilities",)
    request_type = capability_assessment_pb2.AssessCapabilitiesRequest
    response_type = capability_assessment_pb2.AssessCapabilitiesResponse
    assert method.input_type == request_type.DESCRIPTOR
    assert method.output_type == response_type.DESCRIPTOR
    assert not method.client_streaming
    assert not method.server_streaming


def test_findings_field_is_repeated_capability_finding() -> None:
    response_type = capability_assessment_pb2.AssessCapabilitiesResponse
    field = response_type.DESCRIPTOR.fields_by_name["findings"]

    assert field.is_repeated
    assert (
        field.message_type
        == capability_assessment_pb2.CapabilityFinding.DESCRIPTOR
    )


def test_request_message_has_no_deadline_or_dispatch_fields() -> None:
    # Deadlines are a gRPC call option, not a message field; this guards the
    # read-only, non-dispatching boundary against regressions.
    forbidden = ("deadline", "dispatch", "dry_run", "execute", "cancel")
    request_type = capability_assessment_pb2.AssessCapabilitiesRequest
    for name in request_type.DESCRIPTOR.fields_by_name:
        assert not any(token in name for token in forbidden)


def test_request_has_no_generic_target_fields() -> None:
    descriptor = capability_assessment_pb2.AssessCapabilitiesRequest.DESCRIPTOR
    assert "target_kind" not in descriptor.fields_by_name
    assert "target_configuration" not in descriptor.fields_by_name
    properties = _SCHEMA["$defs"]["assessCapabilitiesRequest"]["properties"]
    assert "targetKind" not in properties
    assert "targetConfiguration" not in properties


def test_session_id_fences_independently_of_instance_and_generation(
    request_data,
) -> None:
    request_type = capability_assessment_pb2.AssessCapabilitiesRequest
    message = json_format.ParseDict(request_data, request_type())
    field_names = {field.name for field in request_type.DESCRIPTOR.fields}
    session_id = message.expected_session_id
    instance_id = message.expected_provider_instance_id

    assert session_id == request_data["expectedSessionId"]
    assert session_id != instance_id
    assert {
        "expected_provider_instance_id",
        "expected_endpoint_generation",
        "expected_session_id",
    } <= field_names


# -- Support and requirement states --------------------------------------


@pytest.mark.parametrize(
    "support_state",
    [
        "SUPPORT_STATE_SUPPORTED",
        "SUPPORT_STATE_SUPPORTED_WITH_REQUIREMENTS",
        "SUPPORT_STATE_UNSUPPORTED",
        "SUPPORT_STATE_INDETERMINATE",
    ],
)
def test_every_support_state_round_trips(support_state) -> None:
    finding = {
        "operationIdentifier": "example.vendor/op@1",
        "supportState": support_state,
        "requirementFindings": [],
        "reasons": [],
        "constraints": [],
    }
    if support_state == "SUPPORT_STATE_SUPPORTED_WITH_REQUIREMENTS":
        finding["constraints"] = [
            {
                "constraintId": "example.vendor.constraint",
                "value": "",
                "explanation": "Actionable constraint.",
            }
        ]
    elif support_state in {
        "SUPPORT_STATE_UNSUPPORTED",
        "SUPPORT_STATE_INDETERMINATE",
    }:
        finding["reasons"] = [
            {
                "reasonCode": "example.vendor.reason",
                "explanation": "A reason.",
            }
        ]
    Draft202012Validator(_FINDING_SCHEMA).validate(finding)
    message = json_format.ParseDict(
        finding, capability_assessment_pb2.CapabilityFinding()
    )
    decoded = capability_assessment_pb2.CapabilityFinding.FromString(
        message.SerializeToString()
    )
    assert decoded == message


def test_support_state_unspecified_is_invalid() -> None:
    finding = {
        "operationIdentifier": "example.vendor/op@1",
        "supportState": "SUPPORT_STATE_UNSPECIFIED",
        "requirementFindings": [],
        "reasons": [],
        "constraints": [],
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(_FINDING_SCHEMA).validate(finding)


@pytest.mark.parametrize(
    "state",
    [
        "REQUIREMENT_STATE_SATISFIED",
        "REQUIREMENT_STATE_UNSATISFIED",
        "REQUIREMENT_STATE_UNKNOWN",
    ],
)
def test_every_requirement_state_round_trips(state) -> None:
    requirement = {
        "requirementId": "example.vendor.requirement",
        "state": state,
        "description": "A requirement.",
        "versionConstraint": "",
    }
    Draft202012Validator(_REQUIREMENT_SCHEMA).validate(requirement)


def test_requirement_state_unspecified_is_invalid() -> None:
    requirement = {
        "requirementId": "example.vendor.requirement",
        "state": "REQUIREMENT_STATE_UNSPECIFIED",
        "description": "A requirement.",
        "versionConstraint": "",
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(_REQUIREMENT_SCHEMA).validate(requirement)


def test_mixed_support_states_correlate_by_identifier(response) -> None:
    states_by_operation = {
        finding["operationIdentifier"]: finding["supportState"]
        for finding in response["findings"]
    }
    assert states_by_operation == {
        "stateforge.git/reference.resolve@1": "SUPPORT_STATE_SUPPORTED",
        "stateforge.git/branch.list@1": (
            "SUPPORT_STATE_SUPPORTED_WITH_REQUIREMENTS"
        ),
        "stateforge.git/tag.list@1": "SUPPORT_STATE_UNSUPPORTED",
        "stateforge.git/configuration.inspect@1": (
            "SUPPORT_STATE_INDETERMINATE"
        ),
    }


def test_findings_cover_every_requested_operation_exactly_once(
    response, request_data
) -> None:
    # JSON Schema cannot express request/response completeness; this is a
    # conformance-vector check. The packaged validation module enforces it.
    requested = request_data["operationIdentifiers"]
    returned = [
        finding["operationIdentifier"] for finding in response["findings"]
    ]
    assert returned == requested
    assert set(returned) == set(requested)
    assert len(returned) == len(set(returned))


# -- Cross-field invariants ----------------------------------------------


def test_supported_state_rejects_unsatisfied_requirement(
    response, validator
) -> None:
    finding = response["findings"][0]
    finding["requirementFindings"] = [
        {
            "requirementId": "example.vendor.requirement",
            "state": "REQUIREMENT_STATE_UNSATISFIED",
            "description": "Unsatisfied.",
            "versionConstraint": "",
        }
    ]
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_supported_with_requirements_needs_an_actionable_item(
    response, validator
) -> None:
    finding = response["findings"][1]
    finding["requirementFindings"] = []
    finding["constraints"] = []
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_supported_with_requirements_rejects_all_satisfied_with_no_constraints(
    response, validator
) -> None:
    # A finding whose requirements are all already SATISFIED, and which
    # carries no constraints, has nothing left pending: it does not justify
    # SUPPORTED_WITH_REQUIREMENTS even though "a" requirement is present.
    finding = response["findings"][1]
    finding["requirementFindings"] = [
        {
            "requirementId": "example.vendor.requirement",
            "state": "REQUIREMENT_STATE_SATISFIED",
            "description": "Already satisfied.",
            "versionConstraint": "",
        }
    ]
    finding["constraints"] = []
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_supported_with_requirements_allows_all_satisfied_with_a_constraint(
    response, validator
) -> None:
    finding = response["findings"][1]
    finding["requirementFindings"] = [
        {
            "requirementId": "example.vendor.requirement",
            "state": "REQUIREMENT_STATE_SATISFIED",
            "description": "Already satisfied.",
            "versionConstraint": "",
        }
    ]
    # A constraint alone (e.g. a standing rate limit) still justifies the
    # state even when every requirement happens to already be satisfied.
    validator.validate(response)


@pytest.mark.parametrize(
    "support_state",
    ["SUPPORT_STATE_UNSUPPORTED", "SUPPORT_STATE_INDETERMINATE"],
)
def test_terminal_negative_states_need_a_reason(
    response, validator, support_state
) -> None:
    finding = response["findings"][2]
    finding["supportState"] = support_state
    finding["reasons"] = []
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_duplicate_requirement_ids_are_not_schema_enforced(
    response, validator
) -> None:
    # JSON Schema 2020-12 has no practical way to express "unique by a
    # sub-key" over an array of objects. The packaged validation module,
    # rather than the static schema, guards this invariant.
    finding = response["findings"][1]
    finding["requirementFindings"].append(
        copy.deepcopy(finding["requirementFindings"][0])
    )
    validator.validate(response)  # still schema-valid
    ids = [r["requirementId"] for r in finding["requirementFindings"]]
    assert len(ids) != len(set(ids))


def test_duplicate_reason_codes_are_not_schema_enforced(
    response, validator
) -> None:
    finding = response["findings"][2]
    finding["reasons"].append(copy.deepcopy(finding["reasons"][0]))
    validator.validate(response)  # still schema-valid
    codes = [r["reasonCode"] for r in finding["reasons"]]
    assert len(codes) != len(set(codes))


def test_duplicate_constraint_ids_are_not_schema_enforced(
    response, validator
) -> None:
    finding = response["findings"][1]
    finding["constraints"].append(copy.deepcopy(finding["constraints"][0]))
    validator.validate(response)  # still schema-valid
    ids = [c["constraintId"] for c in finding["constraints"]]
    assert len(ids) != len(set(ids))


# -- Requirement/constraint detail ----------------------------------------


def test_version_constraint_round_trips_and_empty_means_unconstrained(
    response,
) -> None:
    message = json_format.ParseDict(
        response, capability_assessment_pb2.AssessCapabilitiesResponse()
    )
    findings_by_op = {
        finding.operation_identifier: finding for finding in message.findings
    }
    satisfied, unknown = findings_by_op[
        "stateforge.git/branch.list@1"
    ].requirement_findings

    assert satisfied.version_constraint == ""
    assert unknown.version_constraint == ">=2.30"


def test_constraint_detail_round_trips(response) -> None:
    message = json_format.ParseDict(
        response, capability_assessment_pb2.AssessCapabilitiesResponse()
    )
    finding = next(
        f
        for f in message.findings
        if f.operation_identifier == "stateforge.git/branch.list@1"
    )

    assert len(finding.constraints) == 1
    assert (
        finding.constraints[0].constraint_id
        == "stateforge.capability_assessment.v1.read_only_window"
    )


# -- Operation-generic findings -------------------------------------------


# -- Identifiers, context, and secrecy -------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assessmentRequestId", ""),
        ("assessmentRequestId", "not-a-uuid"),
        ("expectedProviderInstanceId", "not-a-uuid"),
        ("expectedEndpointGeneration", "0"),
        ("expectedEndpointGeneration", "01"),
        ("expectedSessionId", ""),
        ("expectedManifestRevision", "sha256:bad"),
        ("targetKind", "stateforge.git/repository@1"),
        ("targetConfiguration", "not-an-object"),
        ("targetConfiguration", []),
        ("executionContext", "not-an-object"),
        ("operationIdentifiers", []),
        (
            "operationIdentifiers",
            ["stateforge.git/reference.resolve@1"] * 2,
        ),
        (
            "operationIdentifiers",
            [f"example.vendor/op_{i}@1" for i in range(65)],
        ),
    ],
)
def test_invalid_request_declarations(request_data, field, value) -> None:
    request_data[field] = value
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(request_data)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("assessmentId",), "not-a-uuid"),
        (("assessmentId",), "3FA85F64-5717-4562-B3FC-2C963F66AFA6"),
        (("sessionId",), ""),
        (("manifestRevision",), "sha256:bad"),
        (("assessmentTimestamp",), "not-a-timestamp"),
        (("assessmentTimestamp",), "2026-09-16"),
        (("findings", 0, "operationIdentifier"), "not-an-identifier"),
        (("findings", 0, "supportState"), "SUPPORT_STATE_UNSPECIFIED"),
        (
            ("findings", 1, "requirementFindings", 0, "state"),
            "REQUIREMENT_STATE_UNSPECIFIED",
        ),
        (
            ("findings", 1, "requirementFindings", 0, "requirementId"),
            "not dotted",
        ),
        (
            ("findings", 1, "constraints", 0, "constraintId"),
            "Not_Dotted",
        ),
        (("findings", 2, "reasons", 0, "reasonCode"), "not dotted"),
    ],
)
def test_invalid_or_incomplete_responses_are_rejected(
    response, validator, path, value
) -> None:
    target = response
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        validator.validate(response)


@pytest.mark.parametrize(
    "field",
    [
        "assessmentRequestId",
        "providerInstanceId",
        "endpointGeneration",
        "sessionId",
        "manifestRevision",
        "assessmentId",
        "assessmentTimestamp",
        "findings",
    ],
)
def test_success_requires_complete_response(response, validator, field):
    del response[field]
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_undeclared_operation_passes_structure_but_fails_manifest_check(
    request_data, manifest_response
) -> None:
    request_data["operationIdentifiers"] = ["example.vendor/unknown@1"]
    _REQUEST_VALIDATOR.validate(request_data)
    declared = set(manifest_response["manifest"]["operations"])
    assert not set(request_data["operationIdentifiers"]) <= declared


def test_custom_reason_and_requirement_identifiers_are_extensible(
    response, validator
) -> None:
    finding = response["findings"][2]
    finding["reasons"][0]["reasonCode"] = "example.vendor.custom_reason"
    validator.validate(response)


@pytest.mark.parametrize(
    "reason_code",
    _CANONICAL_REASON_CODES.values(),
)
def test_canonical_reason_codes_validate(
    response, validator, reason_code
) -> None:
    response["findings"][2]["reasons"][0]["reasonCode"] = reason_code
    validator.validate(response)


@pytest.mark.parametrize("value", ["not-an-object", [], 1, True, None])
def test_execution_context_must_be_an_object(request_data, value) -> None:
    request_data["executionContext"] = value
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(request_data)


def test_execution_context_accepts_nested_objects(request_data) -> None:
    request_data["executionContext"] = {
        "auth": {
            "oauth": {
                "clientId": "stateforge",
                "scopes": [{"name": "repository:read"}],
            }
        },
        "scalar": "value",
    }
    _REQUEST_VALIDATOR.validate(request_data)


def test_context_nesting_limit_is_a_consumer_check_not_a_schema_restriction(
    request_data,
) -> None:
    request_data["executionContext"] = _nested_context(
        contract.MAX_EXECUTION_CONTEXT_JSON_DEPTH
    )
    _REQUEST_VALIDATOR.validate(request_data)
    assert (
        _container_depth(request_data["executionContext"])
        == contract.MAX_EXECUTION_CONTEXT_JSON_DEPTH
    )

    # JSON Schema cannot express an aggregate recursive-depth ceiling. The
    # packaged validator's cheap pre-schema walk rejects the next container.
    request_data["executionContext"] = _nested_context(
        contract.MAX_EXECUTION_CONTEXT_JSON_DEPTH + 1
    )
    _REQUEST_VALIDATOR.validate(request_data)
    assert (
        _container_depth(request_data["executionContext"])
        > contract.MAX_EXECUTION_CONTEXT_JSON_DEPTH
    )


def test_execution_context_bounds_leaf_length(
    request_data,
) -> None:
    request_data["executionContext"] = {"huge": "x" * 1_000_000}
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(request_data)


def test_execution_context_bounds_breadth(
    request_data,
) -> None:
    request_data["executionContext"] = {f"key_{i}": "value" for i in range(33)}
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(request_data)


def test_response_schema_has_no_configuration_or_secret_field() -> None:
    response_related = (
        "assessCapabilitiesResponse",
        "capabilityFinding",
        "requirementFinding",
        "reasonDetail",
        "constraintDetail",
    )
    for name in response_related:
        for property_name in _SCHEMA["$defs"][name]["properties"]:
            lowered = property_name.lower()
            assert "configuration" not in lowered
            assert "secret" not in lowered


# -- Bounds -----------------------------------------------------------------


def test_operation_identifiers_bound_enforced(request_data) -> None:
    request_data["operationIdentifiers"] = [
        f"example.vendor/op_{i}@1" for i in range(65)
    ]
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(request_data)


def test_requirement_findings_bound_enforced(response, validator) -> None:
    finding = response["findings"][1]
    finding["requirementFindings"] = [
        {
            "requirementId": f"example.vendor.requirement_{i}",
            "state": "REQUIREMENT_STATE_SATISFIED",
            "description": "x",
            "versionConstraint": "",
        }
        for i in range(65)
    ]
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_reasons_bound_enforced(response, validator) -> None:
    finding = response["findings"][2]
    finding["reasons"] = [
        {"reasonCode": f"example.vendor.reason_{i}", "explanation": "x"}
        for i in range(17)
    ]
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_constraints_bound_enforced(response, validator) -> None:
    finding = response["findings"][1]
    finding["constraints"] = [
        {
            "constraintId": f"example.vendor.constraint_{i}",
            "value": "",
            "explanation": "x",
        }
        for i in range(33)
    ]
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_serialized_resource_limits_are_independent_of_schema_bounds(
    request_data, response, validator
) -> None:
    request_message = json_format.ParseDict(
        request_data,
        capability_assessment_pb2.AssessCapabilitiesRequest(),
    )
    response_message = json_format.ParseDict(
        response,
        capability_assessment_pb2.AssessCapabilitiesResponse(),
    )
    assert request_message.ByteSize() <= contract.MAX_REQUEST_BYTES
    assert response_message.ByteSize() <= contract.MAX_RESPONSE_BYTES

    # JSON Schema maxLength counts code points, not encoded bytes. This is
    # structurally valid but deliberately exceeds the independent wire cap.
    leaf = "\U0001f600" * 2048
    large_context = {f"key_{index}": [leaf] * 32 for index in range(32)}
    request_data["executionContext"] = large_context
    _REQUEST_VALIDATOR.validate(request_data)
    oversized_message = json_format.ParseDict(
        request_data,
        capability_assessment_pb2.AssessCapabilitiesRequest(),
    )
    assert oversized_message.ByteSize() > contract.MAX_REQUEST_BYTES

    requirement_findings = [
        {
            "requirementId": f"example.vendor.requirement_{index}",
            "state": "REQUIREMENT_STATE_SATISFIED",
            "description": leaf,
            "versionConstraint": "",
        }
        for index in range(64)
    ]
    large_response = copy.deepcopy(response)
    finding = copy.deepcopy(response["findings"][0])
    finding["requirementFindings"] = requirement_findings
    large_response["findings"] = []
    for index in range(32):
        item = copy.deepcopy(finding)
        item["operationIdentifier"] = f"example.vendor/op_{index}@1"
        large_response["findings"].append(item)
    validator.validate(large_response)
    oversized_response = json_format.ParseDict(
        large_response,
        capability_assessment_pb2.AssessCapabilitiesResponse(),
    )
    assert oversized_response.ByteSize() > contract.MAX_RESPONSE_BYTES


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("findings", 2, "reasons", 0, "explanation"), "x" * 1025),
        (
            ("findings", 1, "requirementFindings", 0, "description"),
            "x" * 2049,
        ),
        (
            ("findings", 1, "requirementFindings", 0, "versionConstraint"),
            "x" * 256,
        ),
        (("findings", 1, "constraints", 0, "value"), "x" * 513),
        (("findings", 1, "constraints", 0, "explanation"), "x" * 1025),
    ],
)
def test_string_length_bounds_enforced(
    response, validator, path, value
) -> None:
    target = response
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        validator.validate(response)


# -- Paired accepted-manifest conformance ----------------------------------
#
# request.json and response-mixed-states.json share identity, manifest
# revision and operation values with
# accepted-manifest.json, so they can be used together as one interoperable
# conformance set: this is what a Provider or Agent integration test actually
# pairs against, not a manifest fixture declaring an unrelated single
# operation and a different identity/revision.


def test_accepted_manifest_fixture_is_a_valid_p1_manifest(
    manifest_response,
) -> None:
    Draft202012Validator(_MANIFEST_SCHEMA).validate(manifest_response)


def test_accepted_manifest_fixture_revision_is_recomputable(
    manifest_response,
) -> None:
    preimage = rfc8785.dumps(
        {
            key: manifest_response[key]
            for key in (
                "manifest",
                "manifestSchemaVersion",
                "providerInstanceId",
            )
        }
    )
    expected = "sha256:" + hashlib.sha256(preimage).hexdigest()
    assert manifest_response["manifestRevision"] == expected


def test_assessment_does_not_require_operation_resource_input(
    request_data, manifest_response
) -> None:
    operations = manifest_response["manifest"]["operations"]
    resource_input = operations["stateforge.git/branch.list@1"]["inputSchema"]
    resource_input["properties"] = {"repository": {"type": "string"}}
    resource_input["required"] = ["repository"]
    ordinary_input = operations["stateforge.git/reference.resolve@1"][
        "inputSchema"
    ]
    preimage = rfc8785.dumps(
        {
            key: manifest_response[key]
            for key in (
                "manifest",
                "manifestSchemaVersion",
                "providerInstanceId",
            )
        }
    )
    revision = "sha256:" + hashlib.sha256(preimage).hexdigest()
    manifest_response["manifestRevision"] = revision
    request_data["expectedManifestRevision"] = revision
    Draft202012Validator(_MANIFEST_SCHEMA).validate(manifest_response)
    _REQUEST_VALIDATOR.validate(request_data)
    assert ordinary_input["properties"] == {}
    assert resource_input["required"] == ["repository"]
    assert "repository" not in request_data["executionContext"]


def test_request_and_response_correlate_with_accepted_manifest(
    response, request_data, manifest_response
) -> None:
    assert (
        request_data["expectedProviderInstanceId"]
        == manifest_response["providerInstanceId"]
    )
    assert (
        request_data["expectedManifestRevision"]
        == manifest_response["manifestRevision"]
    )
    assert (
        response["providerInstanceId"]
        == manifest_response["providerInstanceId"]
    )
    assert (
        response["manifestRevision"] == manifest_response["manifestRevision"]
    )
    assert (
        response["assessmentRequestId"] == request_data["assessmentRequestId"]
    )
    assert (
        response["endpointGeneration"]
        == request_data["expectedEndpointGeneration"]
    )
    assert response["sessionId"] == request_data["expectedSessionId"]
    assert manifest_response["sessionId"] == request_data["expectedSessionId"]
    assert response["assessmentId"] != request_data["assessmentRequestId"]


def test_operation_identifiers_are_declared_in_accepted_manifest(
    request_data, manifest_response
) -> None:
    declared = set(manifest_response["manifest"]["operations"])
    requested = set(request_data["operationIdentifiers"])
    assert requested <= declared
