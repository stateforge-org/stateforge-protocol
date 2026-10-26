"""Verify Operation Lifecycle contracts without implementing a runtime."""

import copy
import itertools
import json
from importlib.resources import files
from pathlib import Path

import grpc
import pytest
import yaml
from google.protobuf import json_format
from google.protobuf.any_pb2 import Any
from jsonschema import Draft202012Validator
from tests.documentation import annotated_json_example

from stateforge_protocol.sfp.operation_admission.v1 import (
    operation_admission_pb2 as admission_pb,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    operation_lifecycle_pb2 as pb,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    operation_lifecycle_pb2_grpc as rpc,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    validation as lifecycle_validation,
)
from stateforge_protocol.sfp.operation_lifecycle.v1.contract import (
    MAX_ERROR_DETAIL_BYTES,
    MAX_EXPLANATION_CODE_POINTS,
    MAX_IN_FLIGHT_RESPONSES_PER_OBSERVER,
    MAX_OBSERVERS_PER_OPERATION,
    MAX_PENDING_SNAPSHOTS_PER_OBSERVER,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_RESULT_CONTAINER_ENTRIES,
    MAX_RESULT_JSON_DEPTH,
    MAX_RESULT_PROPERTY_NAME_CODE_POINTS,
    MAX_RESULT_STRING_CODE_POINTS,
    MAX_SNAPSHOT_BYTES,
    MAX_STALLED_DELIVERY_SECONDS,
    SERVICE_NAME,
)

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = Path(__file__).parent / "fixtures" / "operation_lifecycle"
_SCHEMA = json.loads(
    files("stateforge_protocol.sfp.operation_lifecycle.v1")
    .joinpath("operation_lifecycle.schema.json")
    .read_text()
)
_TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}
_UINT64_MAX = 2**64 - 1
_FIRST_PROGRESS_SEQUENCE = 3
_SESSION_MAX_LENGTH = 255
_DIAGNOSTIC_MAX_LENGTH = MAX_EXPLANATION_CODE_POINTS


def _read(name):
    return json.loads((_FIXTURES / name).read_text())


_SNAPSHOTS = _read("snapshots.json")
_TRANSITIONS = _read("transitions.json")


def _validator(definition):
    return Draft202012Validator(
        {"$ref": f"#/$defs/{definition}", "$defs": _SCHEMA["$defs"]}
    )


def _state(snapshot):
    return snapshot["state"].removeprefix("OPERATION_STATE_")


def _project(message):
    return json_format.MessageToDict(
        message, always_print_fields_with_no_presence=True
    )


def _assert_snapshot(snapshot):
    """Check cross-field obligations which JSON Schema cannot express."""
    _validator("operationSnapshot").validate(snapshot)
    message = json_format.ParseDict(snapshot, pb.OperationSnapshot())
    assert 0 < message.sequence <= _UINT64_MAX
    state = _state(snapshot)
    minimum = 3 if state in {"SUCCEEDED", "CANCELLED"} else 2
    if state == "ACCEPTED":
        assert (
            snapshot["updatedAt"] == snapshot["admissionRecord"]["admittedAt"]
        )
    else:
        assert message.sequence >= minimum
    if message.HasField("progress"):
        assert (
            _FIRST_PROGRESS_SEQUENCE
            <= message.progress.sequence
            <= message.sequence
        )
        if message.progress.sequence == message.sequence:
            assert message.progress.updated_at == message.updated_at
        if state in _TERMINAL:
            assert message.progress.sequence < message.sequence


def _assert_committed_pair(before, after):
    """Check adjacent committed snapshots, with no coalescing or replay."""
    _assert_snapshot(before)
    _assert_snapshot(after)
    for field in (
        "admissionRecord",
        "operationIdentifier",
        "manifestRevision",
    ):
        assert before[field] == after[field]
    assert int(after["sequence"]) == int(before["sequence"]) + 1
    assert _state(after) in _TRANSITIONS[_state(before)]
    if _state(before) == _state(after):
        assert after["progress"] != before.get("progress")
        assert after["progress"]["sequence"] == after["sequence"]
    else:
        assert before.get("progress") == after.get("progress")


def _assert_watch(case):
    """Validate a captured transcript without implementing an RPC runtime."""
    cursor = int(case["cursor"])
    seen_terminal = False
    for index, (name, skipped) in enumerate(
        zip(case["snapshots"], case["skipped"], strict=True)
    ):
        snapshot = _SNAPSHOTS[name]
        _assert_snapshot(snapshot)
        sequence = int(snapshot["sequence"])
        assert not seen_terminal
        assert sequence >= cursor if index == 0 else sequence > cursor
        assert skipped == (cursor > 0 and sequence > cursor + 1)
        cursor = sequence
        seen_terminal = _state(snapshot) in _TERMINAL
    assert case["status"] != "OK" or seen_terminal
    assert case["evidence"] == (
        "terminal" if seen_terminal else "indeterminate"
    )


def test_schema_and_shared_p4_definitions_are_unchanged() -> None:
    Draft202012Validator.check_schema(_SCHEMA)
    admission_schema = json.loads(
        files("stateforge_protocol.sfp.operation_admission.v1")
        .joinpath("operation_admission.schema.json")
        .read_text()
    )
    common = _SCHEMA["$defs"].keys() & admission_schema["$defs"].keys()
    assert {"operationSessionBinding", "operationAdmissionRecord"} <= common
    for name in common:
        assert _SCHEMA["$defs"][name] == admission_schema["$defs"][name]


@pytest.mark.parametrize(
    ("fixture", "definition", "message_type"),
    [
        (
            "watch-request.json",
            "watchOperationRequest",
            pb.WatchOperationRequest,
        ),
        (
            "cancel-request.json",
            "cancelOperationRequest",
            pb.CancelOperationRequest,
        ),
        (
            "watch-terminal.json",
            "watchOperationResponse",
            pb.WatchOperationResponse,
        ),
        (
            "cancel-requested.json",
            "cancelOperationResponse",
            pb.CancelOperationResponse,
        ),
    ],
)
def test_wire_fixture_round_trip(fixture, definition, message_type) -> None:
    data = _read(fixture)
    _validator(definition).validate(data)
    message = json_format.ParseDict(data, message_type())
    decoded = message_type.FromString(message.SerializeToString())
    assert _project(decoded) == data


def test_service_streaming_descriptors_and_p4_reuse() -> None:
    service = pb.DESCRIPTOR.services_by_name["OperationLifecycleService"]
    assert service.full_name == SERVICE_NAME
    assert set(service.methods_by_name) == {
        "WatchOperation",
        "CancelOperation",
    }
    for name, streaming in (
        ("WatchOperation", True),
        ("CancelOperation", False),
    ):
        method = service.methods_by_name[name]
        assert not method.client_streaming
        assert method.server_streaming == streaming
        assert method.input_type == getattr(pb, name + "Request").DESCRIPTOR
        assert method.output_type == getattr(pb, name + "Response").DESCRIPTOR
        assert method.input_type.fields_by_name[
            "session_binding"
        ].message_type == (admission_pb.OperationSessionBinding.DESCRIPTOR)
    assert (
        pb.OperationSnapshot.DESCRIPTOR.fields_by_name[
            "admission_record"
        ].message_type
        == admission_pb.OperationAdmissionRecord.DESCRIPTOR
    )
    with grpc.insecure_channel("127.0.0.1:1") as channel:
        stub = rpc.OperationLifecycleServiceStub(channel)
        assert isinstance(stub.WatchOperation, grpc.UnaryStreamMultiCallable)
        assert isinstance(stub.CancelOperation, grpc.UnaryUnaryMultiCallable)


@pytest.mark.parametrize("name", sorted(_SNAPSHOTS))
def test_snapshot_vectors_preserve_admission_and_presence(name) -> None:
    data = _SNAPSHOTS[name]
    _assert_snapshot(data)
    admitted = json.loads(
        (
            _FIXTURES.parent / "operation_admission/response-accepted-new.json"
        ).read_text()
    )
    assert data["admissionRecord"] == admitted["record"]
    assert data["manifestRevision"] == admitted["manifestRevision"]
    message = json_format.ParseDict(data, pb.OperationSnapshot())
    assert (
        _project(pb.OperationSnapshot.FromString(message.SerializeToString()))
        == data
    )
    assert message.WhichOneof("outcome") == {
        "SUCCEEDED": "success",
        "FAILED": "failure",
        "CANCELLED": "cancellation",
    }.get(_state(data))


@pytest.mark.parametrize(
    ("state", "arm"),
    list(
        itertools.product(
            _TRANSITIONS, (None, "success", "failure", "cancellation")
        )
    ),
)
def test_every_state_outcome_presence_combination(state, arm) -> None:
    snapshot = copy.deepcopy(_SNAPSHOTS["accepted"])
    snapshot.update(state="OPERATION_STATE_" + state)
    if state != "ACCEPTED":
        snapshot["sequence"] = "7"
    if arm:
        snapshot[arm] = copy.deepcopy(
            _SNAPSHOTS[
                {
                    "success": "succeeded",
                    "failure": "failed",
                    "cancellation": "cancelled",
                }[arm]
            ][arm]
        )
    expected = {
        "SUCCEEDED": "success",
        "FAILED": "failure",
        "CANCELLED": "cancellation",
    }.get(state)
    assert _validator("operationSnapshot").is_valid(snapshot) == (
        arm == expected
    )


def test_multiple_outcome_arms_rejected_by_schema_and_proto() -> None:
    snapshot = copy.deepcopy(_SNAPSHOTS["succeeded"])
    snapshot["failure"] = _SNAPSHOTS["failed"]["failure"]
    assert not _validator("operationSnapshot").is_valid(snapshot)
    with pytest.raises(json_format.ParseError):
        json_format.ParseDict(snapshot, pb.OperationSnapshot())


@pytest.mark.parametrize(
    ("definition", "message_type"),
    [
        ("watchOperationRequest", pb.WatchOperationRequest),
        ("cancelOperationRequest", pb.CancelOperationRequest),
        ("watchOperationResponse", pb.WatchOperationResponse),
        ("cancelOperationResponse", pb.CancelOperationResponse),
    ],
)
def test_defaults_never_identify_an_operation(
    definition, message_type
) -> None:
    assert not _validator(definition).is_valid(_project(message_type()))


@pytest.mark.parametrize(
    "fixture", ["watch-request.json", "cancel-request.json"]
)
def test_request_fields_required_and_unknown_properties_rejected(
    fixture,
) -> None:
    data = _read(fixture)
    definition = (
        "watchOperationRequest"
        if fixture.startswith("watch")
        else "cancelOperationRequest"
    )
    for field in data:
        invalid = {key: value for key, value in data.items() if key != field}
        assert not _validator(definition).is_valid(invalid)
    data["invocation"] = {}
    assert not _validator(definition).is_valid(data)


@pytest.mark.parametrize("length", [0, 1, 255, 256])
def test_session_identifier_bounds(length) -> None:
    request = _read("watch-request.json")
    request["sessionBinding"]["expectedSessionId"] = "界" * length
    assert _validator("watchOperationRequest").is_valid(request) == (
        1 <= length <= _SESSION_MAX_LENGTH
    )


@pytest.mark.parametrize("cursor", ["0", "1", str(_UINT64_MAX)])
def test_cursor_accepts_zero_and_uint64_bounds(cursor) -> None:
    data = _read("watch-request.json")
    data["afterSequence"] = cursor
    _validator("watchOperationRequest").validate(data)
    assert json_format.ParseDict(
        data, pb.WatchOperationRequest()
    ).after_sequence == int(cursor)


@pytest.mark.parametrize("cursor", ["-1", "01", "1\n", "", 1])
def test_noncanonical_cursor_rejected(cursor) -> None:
    data = _read("watch-request.json")
    data["afterSequence"] = cursor
    assert not _validator("watchOperationRequest").is_valid(data)


def test_uint64_overflow_requires_protobuf_range_validation() -> None:
    data = _read("watch-request.json")
    data["afterSequence"] = str(_UINT64_MAX + 1)
    # Decimal-string shape alone cannot compare numeric magnitude.
    _validator("watchOperationRequest").validate(data)
    with pytest.raises(json_format.ParseError):
        json_format.ParseDict(data, pb.WatchOperationRequest())


@pytest.mark.parametrize("percentage", [0, 100, 12.5, None])
def test_progress_presence_and_zero_percent(percentage) -> None:
    progress = copy.deepcopy(_SNAPSHOTS["progress-25"]["progress"])
    if percentage is None:
        del progress["percentage"]
    else:
        progress["percentage"] = percentage
        progress["message"] = ""
    _validator("operationProgress").validate(progress)
    parsed = json_format.ParseDict(progress, pb.OperationProgress())
    assert parsed.HasField("percentage") == (percentage is not None)
    assert _project(parsed) == progress
    assert _state(_SNAPSHOTS["progress-100"]) == "RUNNING"


@pytest.mark.parametrize("percentage", [-1, 101, "NaN", "Infinity", True])
def test_invalid_percentages_rejected(percentage) -> None:
    progress = copy.deepcopy(_SNAPSHOTS["progress-25"]["progress"])
    progress["percentage"] = percentage
    assert not _validator("operationProgress").is_valid(progress)


def test_progress_requires_message_or_percentage() -> None:
    progress = copy.deepcopy(_SNAPSHOTS["progress-25"]["progress"])
    del progress["percentage"]
    progress["message"] = ""
    assert not _validator("operationProgress").is_valid(progress)


@pytest.mark.parametrize(
    "definition", ["operationProgress", "operationFailure", "operationEffects"]
)
@pytest.mark.parametrize(
    "length",
    [MAX_EXPLANATION_CODE_POINTS, MAX_EXPLANATION_CODE_POINTS + 1],
)
def test_diagnostic_bounds(definition, length) -> None:
    samples = {
        "operationProgress": _SNAPSHOTS["progress-25"]["progress"],
        "operationFailure": _SNAPSHOTS["failed"]["failure"],
        "operationEffects": _SNAPSHOTS["failed"]["failure"]["effects"],
    }
    value = copy.deepcopy(samples[definition])
    value[
        "message" if definition == "operationProgress" else "explanation"
    ] = "界" * length
    assert _validator(definition).is_valid(value) == (
        length <= _DIAGNOSTIC_MAX_LENGTH
    )


@pytest.mark.parametrize(
    ("name", "path", "value"),
    [
        ("running", ("sequence",), "1"),
        ("succeeded", ("sequence",), "2"),
        ("accepted", ("updatedAt",), "2026-09-19T12:01:00Z"),
        ("progress-25", ("progress", "sequence"), "4"),
        ("progress-25", ("progress", "sequence"), "1"),
        ("progress-25", ("progress", "updatedAt"), "2026-09-19T12:01:00Z"),
        ("succeeded", ("progress", "sequence"), "5"),
    ],
)
def test_cross_field_semantics_require_consumer_checks(
    name, path, value
) -> None:
    snapshot = copy.deepcopy(_SNAPSHOTS[name])
    target = snapshot
    for field in path[:-1]:
        target = target[field]
    target[path[-1]] = value
    _validator("operationSnapshot").validate(snapshot)
    with pytest.raises(AssertionError):
        _assert_snapshot(snapshot)


@pytest.mark.parametrize(
    "case", _read("traces.json"), ids=lambda case: case["name"]
)
def test_committed_transition_vectors(case) -> None:
    pairs = itertools.pairwise(case["snapshots"])
    if case["valid"]:
        for before, after in pairs:
            _assert_committed_pair(_SNAPSHOTS[before], _SNAPSHOTS[after])
    else:
        with pytest.raises(AssertionError):
            for before, after in pairs:
                _assert_committed_pair(_SNAPSHOTS[before], _SNAPSHOTS[after])


def test_transition_table_exhausts_wire_states() -> None:
    states = {
        name.removeprefix("OPERATION_STATE_")
        for name in pb.OperationState.keys()  # noqa: SIM118 - protobuf enum API
        if not name.endswith("UNSPECIFIED")
    }
    assert set(_TRANSITIONS) == states
    assert all(set(targets) <= states for targets in _TRANSITIONS.values())
    for terminal in _TERMINAL:
        assert _TRANSITIONS[terminal] == []
    assert "CANCELLED" not in _TRANSITIONS["ACCEPTED"]
    assert "CANCELLED" not in _TRANSITIONS["RUNNING"]


@pytest.mark.parametrize(
    "case", _read("watch-cases.json"), ids=lambda case: case["name"]
)
def test_watch_replay_gaps_and_stream_termination(case) -> None:
    if case["valid"]:
        _assert_watch(case)
    else:
        with pytest.raises(AssertionError):
            _assert_watch(case)


@pytest.mark.parametrize(
    "case", _read("cancel-cases.json"), ids=lambda case: case["name"]
)
def test_cancellation_atomic_decision_and_no_repeat_signal(case) -> None:
    before, after = (_SNAPSHOTS[case[key]] for key in ("before", "after"))
    state = _state(before)
    if state in _TERMINAL:
        expected = "ALREADY_TERMINAL"
    elif state == "CANCELLATION_REQUESTED":
        expected = "ALREADY_REQUESTED"
    else:
        expected = "REQUESTED" if case["supported"] else "UNSUPPORTED"
    assert case["disposition"] == expected
    assert case["signals"] == int(expected == "REQUESTED")
    if expected == "REQUESTED":
        _assert_committed_pair(before, after)
        assert _state(after) == "CANCELLATION_REQUESTED"
        assert not any(
            key in after for key in ("success", "failure", "cancellation")
        )
    else:
        assert before == after
    response = _read("cancel-requested.json")
    response.update(
        snapshot=after, disposition="CANCELLATION_DISPOSITION_" + expected
    )
    _validator("cancelOperationResponse").validate(response)
    assert (
        _project(json_format.ParseDict(response, pb.CancelOperationResponse()))
        == response
    )


@pytest.mark.parametrize(
    "disposition", list(pb.CancellationDisposition.keys())[1:]
)
def test_disposition_cannot_claim_a_different_decision(disposition) -> None:
    response = _read("cancel-requested.json")
    response["disposition"] = disposition
    assert _validator("cancelOperationResponse").is_valid(
        response
    ) == disposition.endswith("REQUESTED")


def test_terminal_replay_is_identical_across_new_session() -> None:
    response = _read("watch-terminal.json")
    original = json_format.ParseDict(response, pb.WatchOperationResponse())
    response.update(
        sessionId="new-negotiated-session",
        endpointGeneration="43",
        updatesSkipped=False,
    )
    _validator("watchOperationResponse").validate(response)
    recovered = json_format.ParseDict(response, pb.WatchOperationResponse())
    lifecycle_validation.validate_terminal_replay(
        original.snapshot, recovered.snapshot
    )
    assert recovered.snapshot == original.snapshot
    assert (
        recovered.snapshot.admission_record.admitted_endpoint_generation
        < recovered.endpoint_generation
    )
    assert recovered.session_id != original.session_id


def test_terminal_replay_rejects_changed_or_nonterminal_state() -> None:
    retained = json_format.ParseDict(
        _SNAPSHOTS["succeeded"], pb.OperationSnapshot()
    )
    changed = copy.deepcopy(retained)
    changed.success.result.fields["reclaimedBytes"].number_value = 8192

    with pytest.raises(
        lifecycle_validation.OperationLifecycleValidationError,
        match="terminal snapshot changed",
    ):
        lifecycle_validation.validate_terminal_replay(retained, changed)

    running = json_format.ParseDict(
        _SNAPSHOTS["running"], pb.OperationSnapshot()
    )
    with pytest.raises(
        lifecycle_validation.OperationLifecycleValidationError,
        match="not terminal",
    ):
        lifecycle_validation.validate_terminal_replay(running, running)


@pytest.mark.parametrize(
    "field", ["sessionId", "providerInstanceId", "endpointGeneration"]
)
def test_structurally_valid_wrong_session_envelope_is_not_accepted(
    field,
) -> None:
    response = _read("watch-terminal.json")
    request = _read("watch-request.json")
    response[field] = {
        "sessionId": "another-active-session",
        "providerInstanceId": "33333333-3333-4333-8333-333333333333",
        "endpointGeneration": "43",
    }[field]
    _validator("watchOperationResponse").validate(response)
    binding_field = "expected" + field[0].upper() + field[1:]
    assert response[field] != request["sessionBinding"][binding_field]


@pytest.mark.parametrize(
    "field", ["admissionRecord", "manifestRevision", "operationIdentifier"]
)
def test_retained_identity_and_pin_cannot_change(field) -> None:
    before = _SNAPSHOTS["progress-100"]
    after = copy.deepcopy(_SNAPSHOTS["succeeded"])
    if field == "admissionRecord":
        after[field]["requestFingerprint"] = "sha256:" + "b" * 64
    elif field == "manifestRevision":
        after[field] = "sha256:" + "b" * 64
    else:
        after[field] = "example.database/maintenance.compact@2"
    _validator("operationSnapshot").validate(after)
    with pytest.raises(AssertionError):
        _assert_committed_pair(before, after)


def test_empty_result_has_presence_but_must_match_pinned_schema() -> None:
    success = json_format.ParseDict({"result": {}}, pb.OperationSuccess())
    assert success.HasField("result")
    _validator("operationSuccess").validate(_project(success))
    assert not _validator("operationSuccess").is_valid({})
    assert not Draft202012Validator(_read("result-schema.json")).is_valid({})
    Draft202012Validator({"type": "object"}).validate(
        _project(success)["result"]
    )


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"reclaimedBytes": -1},
        {"reclaimedBytes": "4096"},
        {"reclaimedBytes": True},
        {"reclaimedBytes": 1, "extra": "unvalidated author data"},
    ],
)
def test_invalid_author_result_becomes_sanitized_failure(result) -> None:
    schema = _read("result-schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(_SNAPSHOTS["succeeded"]["success"]["result"])
    assert not validator.is_valid(result)
    failure = _SNAPSHOTS["invalid-result"]
    _assert_snapshot(failure)
    assert _state(failure) == "FAILED"
    assert failure["failure"]["code"] == "stateforge.operation.invalid_result"
    assert "success" not in failure
    assert set(failure["failure"]) == {"code", "explanation", "effects"}
    assert "unvalidated author data" not in json.dumps(failure)


@pytest.mark.parametrize(
    "result",
    [
        {"v": "x" * (MAX_RESULT_STRING_CODE_POINTS + 1)},
        {"x" * (MAX_RESULT_PROPERTY_NAME_CODE_POINTS + 1): 0},
        {"v": [0] * (MAX_RESULT_CONTAINER_ENTRIES + 1)},
        {str(index): 0 for index in range(MAX_RESULT_CONTAINER_ENTRIES + 1)},
    ],
)
def test_result_structural_resource_limits(result) -> None:
    assert not _validator("operationSuccess").is_valid({"result": result})


def test_versioned_contract_exports_normative_resource_limits() -> None:
    assert MAX_REQUEST_BYTES == 8 * 1024
    assert MAX_RESPONSE_BYTES == 8 * 1024 * 1024
    assert MAX_SNAPSHOT_BYTES == 7 * 1024 * 1024
    assert MAX_ERROR_DETAIL_BYTES == 4 * 1024
    assert MAX_RESULT_JSON_DEPTH == 64  # noqa: PLR2004 - contract value
    assert MAX_PENDING_SNAPSHOTS_PER_OBSERVER == 1
    assert MAX_IN_FLIGHT_RESPONSES_PER_OBSERVER == 1
    assert MAX_OBSERVERS_PER_OPERATION == 16  # noqa: PLR2004 - contract value
    assert MAX_STALLED_DELIVERY_SECONDS == 30  # noqa: PLR2004 - contract value


def test_versioned_contract_limits_match_packaged_schema() -> None:
    definitions = _SCHEMA["$defs"]
    assert (
        definitions["boundedArray"]["maxItems"] == MAX_RESULT_CONTAINER_ENTRIES
    )
    assert (
        definitions["boundedObject"]["maxProperties"]
        == MAX_RESULT_CONTAINER_ENTRIES
    )
    assert (
        definitions["boundedObject"]["propertyNames"]["maxLength"]
        == MAX_RESULT_PROPERTY_NAME_CODE_POINTS
    )
    string_schema = next(
        option
        for option in definitions["boundedScalar"]["anyOf"]
        if option.get("type") == "string"
    )
    assert string_schema["maxLength"] == MAX_RESULT_STRING_CODE_POINTS
    assert (
        definitions["explanation"]["maxLength"] == MAX_EXPLANATION_CODE_POINTS
    )
    assert (
        definitions["operationProgress"]["properties"]["message"]["maxLength"]
        == MAX_EXPLANATION_CODE_POINTS
    )


def test_failure_and_cancellation_require_explicit_effects() -> None:
    reports = [
        snapshot[arm]
        for snapshot in _SNAPSHOTS.values()
        for arm in ("failure", "cancellation")
        if arm in snapshot
    ]
    for report in reports:
        effects = report["effects"]
        for field in effects:
            invalid = {
                key: value for key, value in effects.items() if key != field
            }
            assert not _validator("operationEffects").is_valid(invalid)
    assert {report["effects"]["sideEffects"] for report in reports} == set(
        pb.SideEffectState.keys()
    ) - {"SIDE_EFFECT_STATE_UNSPECIFIED"}
    assert {report["effects"]["cleanup"] for report in reports} == set(
        pb.CleanupState.keys()
    ) - {"CLEANUP_STATE_UNSPECIFIED"}
    assert (
        _SNAPSHOTS["cancelled"]["cancellation"]["effects"]["cleanup"]
        == "CLEANUP_STATE_INCOMPLETE"
    )


@pytest.mark.parametrize(
    "case", _read("error-cases.json"), ids=lambda case: case["name"]
)
def test_structured_transport_errors_are_not_business_outcomes(case) -> None:
    detail = case["detail"]
    _validator("operationLifecycleErrorDetail").validate(detail)
    message = json_format.ParseDict(detail, pb.OperationLifecycleErrorDetail())
    lifecycle_validation.validate_lifecycle_error_detail(message)
    assert _project(message) == detail
    assert case["grpcCode"] in grpc.StatusCode.__members__
    assert case["grpcCode"] != "OK"
    assert case["dispatches"] == 0
    assert case["operationOutcome"] == "indeterminate"
    assert "state" not in detail


def test_error_vectors_cover_every_wire_reason_and_mapping() -> None:
    cases = _read("error-cases.json")
    assert {case["detail"]["reason"] for case in cases} == set(
        pb.LifecycleErrorReason.keys()
    ) - {"LIFECYCLE_ERROR_REASON_UNSPECIFIED"}
    by_reason = {
        case["detail"]["reason"].removeprefix("LIFECYCLE_ERROR_REASON_"): case[
            "grpcCode"
        ]
        for case in cases
    }
    assert by_reason == {
        "INVALID_REQUEST": "INVALID_ARGUMENT",
        "SESSION_PRECONDITION_FAILED": "FAILED_PRECONDITION",
        "OPERATION_RECORD_UNAVAILABLE": "FAILED_PRECONDITION",
        "OPERATION_RECORD_EXPIRED": "FAILED_PRECONDITION",
        "OPERATION_STATE_UNAVAILABLE": "FAILED_PRECONDITION",
        "FINGERPRINT_MISMATCH": "FAILED_PRECONDITION",
        "CURSOR_AHEAD": "OUT_OF_RANGE",
        "OBSERVER_CAPACITY_EXHAUSTED": "RESOURCE_EXHAUSTED",
        "SLOW_OBSERVER": "RESOURCE_EXHAUSTED",
        "PROVIDER_UNAVAILABLE": "UNAVAILABLE",
    }


@pytest.mark.parametrize(
    "state", ["OPERATION_STATE_UNSPECIFIED", "OPERATION_STATE_PAUSED", 2]
)
def test_unknown_or_default_states_are_not_silently_reinterpreted(
    state,
) -> None:
    snapshot = copy.deepcopy(_SNAPSHOTS["running"])
    snapshot["state"] = state
    assert not _validator("operationSnapshot").is_valid(snapshot)


def test_progress_is_forbidden_in_accepted_and_zero_sequence_is_invalid() -> (
    None
):
    accepted = copy.deepcopy(_SNAPSHOTS["accepted"])
    accepted["progress"] = _SNAPSHOTS["progress-25"]["progress"]
    assert not _validator("operationSnapshot").is_valid(accepted)
    running = copy.deepcopy(_SNAPSHOTS["running"])
    running["sequence"] = "0"
    assert not _validator("operationSnapshot").is_valid(running)


@pytest.mark.parametrize("name", ["succeeded", "failed", "cancelled"])
def test_terminal_content_cannot_change_even_when_state_stays_terminal(
    name,
) -> None:
    original = _SNAPSHOTS[name]
    mutated = copy.deepcopy(original)
    arm = {
        "SUCCEEDED": "success",
        "FAILED": "failure",
        "CANCELLED": "cancellation",
    }[_state(original)]
    if arm == "success":
        mutated[arm]["result"]["reclaimedBytes"] = 8192
    elif arm == "failure":
        mutated[arm]["explanation"] = "A different explanation."
    else:
        mutated[arm]["effects"]["cleanup"] = "CLEANUP_STATE_COMPLETED"
    _assert_snapshot(mutated)
    assert (
        mutated != original
    )  # Equal sequence must compare the entire snapshot.
    mutated["sequence"] = str(int(original["sequence"]) + 1)
    with pytest.raises(AssertionError):
        _assert_committed_pair(original, mutated)


def test_state_transition_retains_progress_and_wall_clock_is_not_order() -> (
    None
):
    before = _SNAPSHOTS["progress-100"]
    after = copy.deepcopy(_SNAPSHOTS["requested"])
    after["updatedAt"] = "2026-09-19T11:59:59Z"
    _assert_committed_pair(before, after)
    lifecycle_validation.validate_snapshot_transition(
        json_format.ParseDict(before, pb.OperationSnapshot()),
        json_format.ParseDict(after, pb.OperationSnapshot()),
    )
    after["progress"]["message"] = "Unsequenced progress mutation."
    with pytest.raises(AssertionError):
        _assert_committed_pair(before, after)


def test_same_state_transition_requires_new_progress() -> None:
    before = json_format.ParseDict(
        _SNAPSHOTS["progress-25"], pb.OperationSnapshot()
    )
    after = json_format.ParseDict(
        _SNAPSHOTS["progress-100"], pb.OperationSnapshot()
    )

    lifecycle_validation.validate_snapshot_transition(before, after)

    unchanged = copy.deepcopy(after)
    unchanged.progress.CopyFrom(before.progress)
    with pytest.raises(
        lifecycle_validation.OperationLifecycleValidationError,
        match="new progress",
    ):
        lifecycle_validation.validate_snapshot_transition(before, unchanged)


def test_state_transition_without_progress_remains_valid() -> None:
    accepted = json_format.ParseDict(
        _SNAPSHOTS["accepted"], pb.OperationSnapshot()
    )
    running = json_format.ParseDict(
        _SNAPSHOTS["running"], pb.OperationSnapshot()
    )

    lifecycle_validation.validate_snapshot_transition(accepted, running)


def test_snapshot_wraps_an_invalid_admission_record() -> None:
    snapshot = copy.deepcopy(_SNAPSHOTS["running"])
    snapshot["admissionRecord"]["recordExpiresAt"] = snapshot[
        "admissionRecord"
    ]["admittedAt"]
    message = json_format.ParseDict(snapshot, pb.OperationSnapshot())

    with pytest.raises(
        lifecycle_validation.OperationLifecycleValidationError,
        match="admission record is invalid",
    ):
        lifecycle_validation.validate_operation_snapshot(message)


def test_structured_error_has_versioned_any_identity() -> None:
    error = json_format.ParseDict(
        _read("error-cases.json")[0]["detail"],
        pb.OperationLifecycleErrorDetail(),
    )
    packed = Any()
    packed.Pack(error)
    assert packed.type_url == (
        "type.googleapis.com/stateforge.sfp.operation_lifecycle.v1."
        "OperationLifecycleErrorDetail"
    )
    decoded = pb.OperationLifecycleErrorDetail()
    assert packed.Unpack(decoded)
    assert decoded == error


def test_late_cancel_response_does_not_regress_watch_cursor() -> None:
    observed = _SNAPSHOTS["cancelled"]
    delayed = _read("cancel-requested.json")["snapshot"]
    _assert_snapshot(delayed)
    assert int(delayed["sequence"]) < int(observed["sequence"])
    assert delayed["admissionRecord"] == observed["admissionRecord"]
    assert _state(observed) in _TERMINAL


def test_invalid_calendar_timestamp_requires_protobuf_validation() -> None:
    data = copy.deepcopy(_SNAPSHOTS["running"])
    data["updatedAt"] = "2026-02-30T00:00:00Z"
    _validator("operationSnapshot").validate(data)
    with pytest.raises(json_format.ParseError):
        json_format.ParseDict(data, pb.OperationSnapshot())


def test_oversized_result_requires_aggregate_serialized_size_check() -> None:
    snapshot = copy.deepcopy(_SNAPSHOTS["succeeded"])
    snapshot["success"]["result"] = {
        str(index): "x" * 65536 for index in range(128)
    }
    _validator("operationSnapshot").validate(snapshot)
    message = json_format.ParseDict(snapshot, pb.OperationSnapshot())
    assert message.ByteSize() > MAX_SNAPSHOT_BYTES
    # The normalized invalid-result fallback always fits, without author data.
    fallback = json_format.ParseDict(
        _SNAPSHOTS["invalid-result"], pb.OperationSnapshot()
    )
    assert fallback.ByteSize() < MAX_SNAPSHOT_BYTES


def test_operation_lifecycle_walkthrough_covers_documented_scenarios() -> None:
    declaration = yaml.safe_load(
        (
            _ROOT
            / "docs"
            / "v0.1.0"
            / "procedures"
            / "operation-lifecycle.yaml"
        ).read_text(encoding="utf-8")
    )
    expected_markers = {
        "success": "SUCCEEDED",
        "late-attachment": "zero cursor never reports a historical gap",
        "reconnect-gap": "updates_skipped true",
        "operation-failed": "FAILED",
        "invalid-result": "stateforge.operation.invalid_result",
        "cancellation-stops": "CANCELLED",
        "cancellation-unsupported": "UNSUPPORTED",
        "cancellation-race": "First terminal commit wins",
        "repeated-cancellation": "ALREADY_REQUESTED",
        "transport-disconnect": "Transport status is not a business outcome",
        "slow-observer": "SLOW_OBSERVER",
    }

    assert set(declaration["scenarios"]) == set(expected_markers)
    for scenario_id, marker in expected_markers.items():
        serialized = json.dumps(declaration["scenarios"][scenario_id])
        assert marker in serialized


def test_operation_lifecycle_overview_tracks_terminal_evidence() -> None:
    declaration = yaml.safe_load(
        (
            _ROOT
            / "docs"
            / "v0.1.0"
            / "procedures"
            / "operation-lifecycle-overview.yaml"
        ).read_text(encoding="utf-8")
    )

    assert declaration["schema"] == "stateforge.docs/entity-flow/v1"
    assert [entity["id"] for entity in declaration["entities"]] == [
        "agent",
        "provider",
        "record",
        "database",
    ]
    assert [step["id"] for step in declaration["steps"]] == [
        "watch-current-state",
        "execution-starts",
        "progress-committed",
        "result-validated",
        "terminal-delivered",
    ]
    assert declaration["steps"][3]["responsibility"]["entities"] == [
        "provider",
        "record",
    ]
    assert declaration["steps"][-1]["transitions"] == [
        {
            "source": "record",
            "target": "agent",
            "label": "SUCCEEDED · result",
            "tone": "success",
        }
    ]


def test_operation_lifecycle_documentation_identifies_contract_ownership() -> (
    None
):
    documentation = (
        _ROOT
        / "docs"
        / "v0.1.0"
        / "procedures"
        / "progress-results-cancellation.md"
    ).read_text(encoding="utf-8")

    assert "operation_lifecycle.proto" in documentation
    assert "operation_lifecycle.schema.json" in documentation
    assert "operation_lifecycle/v1/contract.py" in documentation
    assert "operation_lifecycle/v1/validation.py" in documentation
    assert "| Serialized Watch or Cancel request | 8 KiB |" in documentation
    assert "| Serialized Watch or Cancel response | 8 MiB |" in documentation
    assert "| Serialized complete snapshot | 7 MiB |" in documentation
    assert "| Serialized structured error detail | 4 KiB |" in documentation


def test_documented_operation_lifecycle_protojson_matches_contract() -> None:
    documentation = (
        _ROOT
        / "docs"
        / "v0.1.0"
        / "procedures"
        / "progress-results-cancellation.md"
    ).read_text(encoding="utf-8")
    watch_data = annotated_json_example(
        documentation,
        title="WatchOperationRequest",
    )
    cancel_data = annotated_json_example(
        documentation,
        title="CancelOperationRequest",
    )
    terminal_data = annotated_json_example(
        documentation,
        title="WatchOperationResponse · terminal",
    )
    requested_data = annotated_json_example(
        documentation,
        title="CancelOperationResponse · requested",
    )
    error_data = annotated_json_example(
        documentation,
        title="OperationLifecycleErrorDetail",
    )

    assert watch_data == _read("watch-request.json")
    assert cancel_data == _read("cancel-request.json")
    assert terminal_data == _read("watch-terminal.json")
    assert requested_data == _read("cancel-requested.json")

    watch = json_format.ParseDict(watch_data, pb.WatchOperationRequest())
    cancel = json_format.ParseDict(cancel_data, pb.CancelOperationRequest())
    terminal = json_format.ParseDict(
        terminal_data,
        pb.WatchOperationResponse(),
    )
    requested = json_format.ParseDict(
        requested_data,
        pb.CancelOperationResponse(),
    )
    error = json_format.ParseDict(
        error_data,
        pb.OperationLifecycleErrorDetail(),
    )

    lifecycle_validation.validate_watch_operation_request(watch)
    lifecycle_validation.validate_watch_operation_response(terminal)
    resumed_watch = copy.deepcopy(watch)
    resumed_watch.after_sequence = 2
    lifecycle_validation.validate_watch_exchange(resumed_watch, terminal)
    lifecycle_validation.validate_cancel_exchange(cancel, requested)
    lifecycle_validation.validate_lifecycle_error_detail(error)
