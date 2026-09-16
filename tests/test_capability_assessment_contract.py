"""Conformance vectors for the capability-assessment wire and schema."""

import copy
import json
from importlib.resources import files
from pathlib import Path

import pytest
from google.protobuf import json_format
from jsonschema import Draft202012Validator, ValidationError

from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2,
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


@pytest.fixture
def response():
    return json.loads((_FIXTURES / "response-mixed-states.json").read_text())


@pytest.fixture
def backup_response():
    path = _FIXTURES / "response-backup-source-modes.json"
    return json.loads(path.read_text())


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

    assert service.full_name == (
        "stateforge.sfp.capability_assessment.v1.CapabilityAssessmentService"
    )
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
        "backupSourceModes": [],
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
        "backupSourceModes": [],
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
        "stateforge.git/backup.prepare@1": "SUPPORT_STATE_INDETERMINATE",
    }


def test_findings_cover_every_requested_operation_exactly_once(
    request_data, response
) -> None:
    # JSON Schema cannot express request/response completeness; this is a
    # dedicated Python-level check of the invariant instead.
    requested = request_data["operationIdentifiers"]
    returned = [f["operationIdentifier"] for f in response["findings"]]
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
    # sub-key" over an array of objects; this gap is documented in the
    # schema description and procedure page. A caller-side check (as done
    # here) is what actually guards the invariant, not the static schema.
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


# -- Backup source modes ---------------------------------------------------


def test_ordinary_operation_has_empty_backup_source_modes(
    backup_response,
) -> None:
    ordinary = backup_response["findings"][0]
    assert ordinary["backupSourceModes"] == []


def test_backup_operation_carries_declared_source_modes(
    backup_response,
) -> None:
    backup = backup_response["findings"][1]
    assert backup["backupSourceModes"]
    assert set(backup["backupSourceModes"]) <= {
        "staged_filesystem",
        "provider_reference",
    }


def test_backup_source_mode_outside_closed_vocabulary_is_rejected(
    response, validator
) -> None:
    finding = response["findings"][3]
    finding["backupSourceModes"] = ["full_snapshot"]
    with pytest.raises(ValidationError):
        validator.validate(response)


# -- Identifiers, configuration, and secrecy -------------------------------


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
        ("targetKind", "repository"),
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
        (("findings", 3, "backupSourceModes"), ["full_snapshot"]),
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


@pytest.mark.parametrize(
    "identifier",
    [
        "repository",
        "example.vendor/foo@0",
        "example.vendor/foo@01",
        "example.vendor/Foo@1",
        "example.vendor/foo@1\n",
    ],
)
def test_invalid_target_kind_identifiers(request_data, identifier) -> None:
    request_data["targetKind"] = identifier
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(request_data)


def test_undeclared_target_kind_passes_structural_validation(
    request_data,
) -> None:
    # Whether target_kind is actually declared by the accepted manifest is a
    # FAILED_PRECONDITION check the Provider performs at runtime; this
    # static schema can only enforce identifier syntax.
    request_data["targetKind"] = "example.vendor/unknown_target@1"
    _REQUEST_VALIDATOR.validate(request_data)


def test_custom_reason_and_requirement_identifiers_are_extensible(
    response, validator
) -> None:
    finding = response["findings"][2]
    finding["reasons"][0]["reasonCode"] = "example.vendor.custom_reason"
    validator.validate(response)


@pytest.mark.parametrize(
    "reason_code",
    [
        "stateforge.capability_assessment.v1.access_denied",
        "stateforge.capability_assessment.v1.permission_uncertain",
        "stateforge.capability_assessment.v1.unsupported_vendor_state",
        "stateforge.capability_assessment.v1.insufficient_evidence",
        "stateforge.capability_assessment.v1.target_not_found",
        "stateforge.capability_assessment.v1.requirement_unmet",
    ],
)
def test_canonical_reason_codes_validate(
    response, validator, reason_code
) -> None:
    response["findings"][2]["reasons"][0]["reasonCode"] = reason_code
    validator.validate(response)


@pytest.mark.parametrize("field", ["targetConfiguration", "executionContext"])
@pytest.mark.parametrize("value", ["not-an-object", [], 1, True, None])
def test_target_configuration_and_execution_context_must_be_objects(
    request_data, field, value
) -> None:
    request_data[field] = value
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(request_data)


@pytest.mark.parametrize("field", ["targetConfiguration", "executionContext"])
def test_target_configuration_and_execution_context_accept_objects(
    request_data, field
) -> None:
    # One level of nesting (an array or object of scalars) is allowed under
    # each top-level entry; a second level is not (see the bounds test
    # below), matching the documented "root object, one nested level" cap.
    request_data[field] = {
        "list": [1, 2, 3],
        "nested": {"anything": "a value"},
        "scalar": "value",
    }
    _REQUEST_VALIDATOR.validate(request_data)


@pytest.mark.parametrize("field", ["targetConfiguration", "executionContext"])
def test_target_configuration_and_execution_context_bound_nesting_depth(
    request_data, field
) -> None:
    # A second level of nesting (an object/array nested inside an
    # already-nested object/array) exceeds the documented depth bound.
    request_data[field] = {"nested": {"anything": [1, 2, 3]}}
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(request_data)


@pytest.mark.parametrize("field", ["targetConfiguration", "executionContext"])
def test_target_configuration_and_execution_context_bound_leaf_length(
    request_data, field
) -> None:
    request_data[field] = {"huge": "x" * 1_000_000}
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(request_data)


@pytest.mark.parametrize("field", ["targetConfiguration", "executionContext"])
def test_target_configuration_and_execution_context_bound_breadth(
    request_data, field
) -> None:
    request_data[field] = {f"key_{i}": "value" for i in range(33)}
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
# request.json, response-mixed-states.json, and response-backup-source-modes
# .json share identity, manifest revision, target kind, operation, and
# configuration values with accepted-manifest.json, so they can be used
# together as one interoperable conformance set: this is what a Provider or
# Agent integration test actually pairs against, not a manifest fixture
# declaring an unrelated single operation and a different identity/revision.


def test_accepted_manifest_fixture_is_a_valid_p1_manifest(
    manifest_response,
) -> None:
    Draft202012Validator(_MANIFEST_SCHEMA).validate(manifest_response)


def test_request_and_response_correlate_with_accepted_manifest(
    request_data, response, manifest_response
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


def test_target_kind_is_declared_in_accepted_manifest(
    request_data, manifest_response
) -> None:
    assert (
        request_data["targetKind"]
        in manifest_response["manifest"]["targetKinds"]
    )


def test_operation_identifiers_are_declared_in_accepted_manifest(
    request_data, manifest_response
) -> None:
    declared = set(manifest_response["manifest"]["operations"])
    requested = set(request_data["operationIdentifiers"])
    assert requested <= declared


def test_target_configuration_validates_against_accepted_manifest_schema(
    request_data, manifest_response
) -> None:
    # This is the semantic check the packaged capability-assessment schema
    # explicitly cannot perform on its own (see "Structural and semantic
    # validation" in the procedure page): validating target_configuration's
    # actual contents against the accepted manifest's configuration_schema
    # for target_kind.
    configuration_schema = manifest_response["manifest"]["configurationSchema"]
    Draft202012Validator(configuration_schema).validate(
        request_data["targetConfiguration"]
    )


@pytest.mark.parametrize("fixture_name", ["response", "backup_response"])
def test_backup_source_modes_are_a_subset_of_accepted_manifest_declaration(
    request, fixture_name, manifest_response
) -> None:
    data = request.getfixturevalue(fixture_name)
    operations = manifest_response["manifest"]["operations"]
    for finding in data["findings"]:
        if not finding["backupSourceModes"]:
            continue
        declared = set(
            operations[finding["operationIdentifier"]]["backupSourceModes"]
        )
        assert set(finding["backupSourceModes"]) <= declared


def test_ordinary_operation_backup_relevance_is_absent_from_manifest_too(
    manifest_response,
) -> None:
    ordinary = manifest_response["manifest"]["operations"][
        "stateforge.git/reference.resolve@1"
    ]
    assert ordinary["backupSourceModes"] == []
    assert ordinary["implements"] == []
