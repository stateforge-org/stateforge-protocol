"""Conformance vectors for trigger publication and acknowledgement."""

import copy
import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest
import rfc8785
import yaml
from google.protobuf import json_format
from jsonschema import Draft202012Validator, ValidationError
from tests.documentation import annotated_json_example

from stateforge_protocol.sfp.manifest.v1 import manifest_pb2
from stateforge_protocol.sfp.trigger_publication.v1 import (
    contract,
    trigger_publication_pb2,
    validation,
)

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = Path(__file__).parent / "fixtures" / "trigger_publication"
_SCHEMA = json.loads(
    files("stateforge_protocol.sfp.trigger_publication.v1")
    .joinpath("trigger_publication.schema.json")
    .read_text()
)
_REQUEST_SCHEMA = {
    "$ref": "#/$defs/triggerStreamRequest",
    "$defs": _SCHEMA["$defs"],
}
_RESPONSE_SCHEMA = {
    "$ref": "#/$defs/triggerStreamResponse",
    "$defs": _SCHEMA["$defs"],
}
_REQUEST_VALIDATOR = Draft202012Validator(_REQUEST_SCHEMA)
_RESPONSE_VALIDATOR = Draft202012Validator(_RESPONSE_SCHEMA)


def _read_json(name: str):
    return json.loads((_FIXTURES / name).read_text())


def _canonical_content(publication_data: dict) -> bytes:
    message = json_format.ParseDict(
        publication_data,
        trigger_publication_pb2.StreamTriggersResponse(),
    )
    projection = json_format.MessageToDict(
        message.publication,
        always_print_fields_with_no_presence=True,
    )
    del projection["publicationId"]
    return rfc8785.dumps(projection)


def _content_fingerprint(publication_data: dict) -> str:
    digest = hashlib.sha256(_canonical_content(publication_data)).hexdigest()
    return f"sha256:{digest}"


@pytest.fixture
def publication_data():
    return _read_json("publication.json")


def test_validation_schema_is_valid() -> None:
    Draft202012Validator.check_schema(_SCHEMA)


@pytest.mark.parametrize(
    ("fixture_name", "message_type", "validator"),
    [
        (
            "open.json",
            trigger_publication_pb2.StreamTriggersRequest,
            _REQUEST_VALIDATOR,
        ),
        (
            "acknowledgement-accepted-new.json",
            trigger_publication_pb2.StreamTriggersRequest,
            _REQUEST_VALIDATOR,
        ),
        (
            "acknowledgement-accepted-duplicate.json",
            trigger_publication_pb2.StreamTriggersRequest,
            _REQUEST_VALIDATOR,
        ),
        (
            "acknowledgement-rejected.json",
            trigger_publication_pb2.StreamTriggersRequest,
            _REQUEST_VALIDATOR,
        ),
        (
            "ready.json",
            trigger_publication_pb2.StreamTriggersResponse,
            _RESPONSE_VALIDATOR,
        ),
        (
            "publication.json",
            trigger_publication_pb2.StreamTriggersResponse,
            _RESPONSE_VALIDATOR,
        ),
    ],
)
def test_valid_vectors_round_trip_complete_protojson(
    fixture_name,
    message_type,
    validator,
) -> None:
    vector = _read_json(fixture_name)
    validator.validate(vector)
    message = json_format.ParseDict(vector, message_type())
    decoded = message_type.FromString(message.SerializeToString())
    projected = json_format.MessageToDict(
        decoded,
        always_print_fields_with_no_presence=True,
    )

    assert decoded == message
    assert projected == vector


def test_service_is_versioned_and_bidirectional_streaming() -> None:
    service = trigger_publication_pb2.DESCRIPTOR.services_by_name[
        "TriggerPublicationService"
    ]
    method = service.methods_by_name["StreamTriggers"]

    assert service.full_name == contract.SERVICE_NAME
    assert tuple(service.methods_by_name) == ("StreamTriggers",)
    assert method.input_type == (
        trigger_publication_pb2.StreamTriggersRequest.DESCRIPTOR
    )
    assert method.output_type == (
        trigger_publication_pb2.StreamTriggersResponse.DESCRIPTOR
    )
    assert method.client_streaming
    assert method.server_streaming


def test_versioned_contract_exposes_normative_limits() -> None:
    expected = {
        "MAX_REQUEST_BYTES": 64 * 1024,
        "MAX_RESPONSE_BYTES": 2 * 1024 * 1024,
        "MAX_CANONICAL_PAYLOAD_BYTES": 1 * 1024 * 1024,
        "MAX_PAYLOAD_JSON_DEPTH": 64,
        "MAX_PAYLOAD_CONTAINER_ENTRIES": 256,
        "MAX_PAYLOAD_PROPERTY_NAME_CODE_POINTS": 128,
        "MAX_PAYLOAD_STRING_CODE_POINTS": 65_536,
        "MAX_TRIGGER_IDENTIFIER_CODE_POINTS": 255,
        "MAX_SESSION_ID_CODE_POINTS": 255,
        "MAX_EXPLANATION_CODE_POINTS": 1_024,
        "MAX_RETRY_AFTER_SECONDS": 24 * 60 * 60,
        "MAX_IN_FLIGHT_PUBLICATIONS": 1_024,
    }

    assert {name: getattr(contract, name) for name in expected} == expected


def test_versioned_contract_limits_match_packaged_schema() -> None:
    definitions = _SCHEMA["$defs"]
    string_schema = next(
        option
        for option in definitions["boundedScalar"]["anyOf"]
        if option.get("type") == "string"
    )

    assert (
        definitions["boundedArray"]["maxItems"]
        == contract.MAX_PAYLOAD_CONTAINER_ENTRIES
    )
    assert (
        definitions["boundedObject"]["maxProperties"]
        == contract.MAX_PAYLOAD_CONTAINER_ENTRIES
    )
    assert (
        definitions["boundedObject"]["propertyNames"]["maxLength"]
        == contract.MAX_PAYLOAD_PROPERTY_NAME_CODE_POINTS
    )
    assert (
        string_schema["maxLength"] == contract.MAX_PAYLOAD_STRING_CODE_POINTS
    )
    assert (
        definitions["versionedIdentifier"]["maxLength"]
        == contract.MAX_TRIGGER_IDENTIFIER_CODE_POINTS
    )
    assert (
        definitions["sessionId"]["maxLength"]
        == contract.MAX_SESSION_ID_CODE_POINTS
    )
    assert (
        definitions["triggerRejection"]["properties"]["explanation"][
            "maxLength"
        ]
        == contract.MAX_EXPLANATION_CODE_POINTS
    )
    assert (
        definitions["receiveWindow"]["maximum"]
        == contract.MAX_IN_FLIGHT_PUBLICATIONS
    )


def test_stream_directions_are_closed_oneof_envelopes() -> None:
    request_descriptor = (
        trigger_publication_pb2.StreamTriggersRequest.DESCRIPTOR
    )
    response_descriptor = (
        trigger_publication_pb2.StreamTriggersResponse.DESCRIPTOR
    )
    request_oneof = request_descriptor.oneofs_by_name["message"]
    response_oneof = response_descriptor.oneofs_by_name["message"]

    assert {field.name for field in request_oneof.fields} == {
        "open",
        "acknowledgement",
    }
    assert {field.name for field in response_oneof.fields} == {
        "ready",
        "publication",
    }


def test_stream_binding_pins_session_and_manifest() -> None:
    open_data = _read_json("open.json")["open"]
    ready_data = _read_json("ready.json")["ready"]
    binding = open_data["sessionBinding"]

    assert (
        ready_data["providerInstanceId"]
        == (binding["expectedProviderInstanceId"])
    )
    assert (
        ready_data["endpointGeneration"]
        == (binding["expectedEndpointGeneration"])
    )
    assert ready_data["sessionId"] == binding["expectedSessionId"]
    assert (
        ready_data["manifestRevision"] == (binding["expectedManifestRevision"])
    )
    assert (
        ready_data["maximumInFlightPublications"]
        <= (open_data["requestedMaxInFlightPublications"])
    )


def test_trigger_payload_uses_the_exact_manifest_declaration(
    publication_data,
) -> None:
    declaration = _read_json("trigger-declaration.json")
    manifest = manifest_pb2.ProviderManifest()
    json_format.ParseDict(
        {
            "triggers": {
                declaration["triggerIdentifier"]: {
                    "payloadSchema": declaration["payloadSchema"]
                }
            }
        },
        manifest,
    )
    publication = publication_data["publication"]
    selected = manifest.triggers[publication["triggerIdentifier"]]
    payload_schema = json_format.MessageToDict(selected.payload_schema)

    Draft202012Validator.check_schema(payload_schema)
    Draft202012Validator(payload_schema).validate(publication["payload"])

    invalid = copy.deepcopy(publication["payload"])
    invalid["commitSha"] = "not-a-commit-sha"
    with pytest.raises(ValidationError):
        Draft202012Validator(payload_schema).validate(invalid)


def test_publication_has_no_generic_identity_or_schema_version_field(
    publication_data,
) -> None:
    fields = {
        field.name
        for field in (
            trigger_publication_pb2.TriggerPublication.DESCRIPTOR.fields
        )
    }

    assert fields == {
        "publication_id",
        "trigger_identifier",
        "observed_at",
        "payload",
    }
    assert (
        not {
            "target",
            "target_kind",
            "source_identity",
            "resource_identity",
            "project_id",
            "component_id",
            "schema_version",
            "provider_instance_id",
        }
        & fields
    )

    obsolete = _read_json("invalid/source-identity-publication.json")
    with pytest.raises(ValidationError):
        _RESPONSE_VALIDATOR.validate(obsolete)
    with pytest.raises(json_format.ParseError):
        json_format.ParseDict(
            obsolete,
            trigger_publication_pb2.StreamTriggersResponse(),
        )

    _RESPONSE_VALIDATOR.validate(publication_data)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "invalid/default-open.json",
        "invalid/accepted-with-rejection.json",
        "invalid/rejected-without-rejection.json",
        "invalid/source-identity-publication.json",
    ],
)
def test_invalid_vectors_are_rejected(fixture_name) -> None:
    vector = _read_json(fixture_name)
    validator = (
        _REQUEST_VALIDATOR
        if "publication" not in vector
        else _RESPONSE_VALIDATOR
    )
    with pytest.raises(ValidationError):
        validator.validate(vector)


def test_proto_defaults_are_not_valid_wildcards() -> None:
    empty_request = trigger_publication_pb2.StreamTriggersRequest.FromString(
        b""
    )
    empty_response = trigger_publication_pb2.StreamTriggersResponse.FromString(
        b""
    )

    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(
            json_format.MessageToDict(
                empty_request,
                always_print_fields_with_no_presence=True,
            )
        )
    with pytest.raises(ValidationError):
        _RESPONSE_VALIDATOR.validate(
            json_format.MessageToDict(
                empty_response,
                always_print_fields_with_no_presence=True,
            )
        )


def test_acknowledgements_correlate_by_publication_id() -> None:
    publication_id = _read_json("publication.json")["publication"][
        "publicationId"
    ]

    for fixture_name in (
        "acknowledgement-accepted-new.json",
        "acknowledgement-accepted-duplicate.json",
        "acknowledgement-rejected.json",
    ):
        acknowledgement = _read_json(fixture_name)["acknowledgement"]
        assert acknowledgement["publicationId"] == publication_id


def test_acknowledgement_correlation_is_scoped_to_the_current_stream() -> None:
    scenarios = {
        item["scenario"]: item
        for item in _read_json("acknowledgement-correlation-scenarios.json")
    }

    assert set(scenarios) == {
        "outstanding_on_current_stream",
        "replayed_on_current_stream",
        "unknown_publication",
        "already_acknowledged",
        "previous_stream_without_replay",
    }
    assert {
        name
        for name, scenario in scenarios.items()
        if scenario["expectedOutcome"] == "ACCEPTED"
    } == {
        "outstanding_on_current_stream",
        "replayed_on_current_stream",
    }
    assert all(
        scenario["expectedOutcome"] == "INVALID_ARGUMENT"
        and scenario["streamTerminates"]
        for scenario in scenarios.values()
        if scenario["expectedOutcome"] != "ACCEPTED"
    )


def test_acknowledgement_dispositions_are_closed_and_complete() -> None:
    values = {
        value.name
        for value in (
            trigger_publication_pb2.TriggerAcknowledgementDisposition.DESCRIPTOR.values
        )
    }

    assert values == {
        "TRIGGER_ACKNOWLEDGEMENT_DISPOSITION_UNSPECIFIED",
        "TRIGGER_ACKNOWLEDGEMENT_DISPOSITION_ACCEPTED_NEW",
        "TRIGGER_ACKNOWLEDGEMENT_DISPOSITION_ACCEPTED_DUPLICATE",
        "TRIGGER_ACKNOWLEDGEMENT_DISPOSITION_REJECTED",
    }


def test_rejection_fixture_covers_every_reason() -> None:
    cases = _read_json("rejection-cases.json")
    fixture_reasons = {case["reason"] for case in cases}
    wire_reasons = {
        value.name
        for value in (
            trigger_publication_pb2.TriggerRejectionReason.DESCRIPTOR.values
        )
        if value.number != 0
    }

    assert fixture_reasons == wire_reasons
    assert {case["reason"] for case in cases if case["retryable"]} == {
        "TRIGGER_REJECTION_REASON_AGENT_CAPACITY_EXHAUSTED",
        "TRIGGER_REJECTION_REASON_DELIVERY_RESPONSIBILITY_UNAVAILABLE",
    }


@pytest.mark.parametrize("case", _read_json("rejection-cases.json"))
def test_every_rejection_reason_round_trips(case) -> None:
    acknowledgement = {
        "acknowledgement": {
            "publicationId": "11111111-1111-4111-8111-111111111111",
            "disposition": ("TRIGGER_ACKNOWLEDGEMENT_DISPOSITION_REJECTED"),
            "rejection": {
                "reason": case["reason"],
                "retryable": case["retryable"],
                "explanation": case["condition"],
            },
        }
    }
    if case["retryable"]:
        acknowledgement["acknowledgement"]["rejection"]["retryAfter"] = "5s"

    _REQUEST_VALIDATOR.validate(acknowledgement)
    message = json_format.ParseDict(
        acknowledgement,
        trigger_publication_pb2.StreamTriggersRequest(),
    )
    assert (
        json_format.MessageToDict(
            message,
            always_print_fields_with_no_presence=True,
        )
        == acknowledgement
    )


def test_retry_after_requires_a_retryable_rejection() -> None:
    acknowledgement = _read_json("acknowledgement-rejected.json")
    rejection = acknowledgement["acknowledgement"]["rejection"]
    rejection["retryAfter"] = "5s"

    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(acknowledgement)


@pytest.mark.parametrize("duration", ["0.5s", "0.500s", "0.000000001s"])
def test_positive_subsecond_retry_after_is_valid(duration: str) -> None:
    acknowledgement = _read_json("acknowledgement-rejected.json")
    rejection = acknowledgement["acknowledgement"]["rejection"]
    rejection["retryable"] = True
    rejection["retryAfter"] = duration

    _REQUEST_VALIDATOR.validate(acknowledgement)
    json_format.ParseDict(
        acknowledgement,
        trigger_publication_pb2.StreamTriggersRequest(),
    )


@pytest.mark.parametrize("duration", ["0s", "0.0s", "0.000000000s"])
def test_zero_retry_after_is_invalid(duration: str) -> None:
    acknowledgement = _read_json("acknowledgement-rejected.json")
    rejection = acknowledgement["acknowledgement"]["rejection"]
    rejection["retryable"] = True
    rejection["retryAfter"] = duration

    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(acknowledgement)


def test_canonical_content_excludes_delivery_and_session_identity(
    publication_data,
) -> None:
    changed_publication_id = copy.deepcopy(publication_data)
    changed_publication_id["publication"]["publicationId"] = (
        "22222222-2222-4222-8222-222222222222"
    )

    assert _canonical_content(changed_publication_id) == (
        _canonical_content(publication_data)
    )
    assert "providerInstanceId" not in publication_data["publication"]
    assert "sessionId" not in publication_data["publication"]


def test_golden_canonical_content_vector(publication_data) -> None:
    vector = _read_json("content-fingerprint-vector.json")

    assert (
        _canonical_content(publication_data).decode()
        == (vector["canonicalJson"])
    )
    assert _content_fingerprint(publication_data) == vector["fingerprint"]


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (
            ("triggerIdentifier",),
            "stateforge.git/reference.deleted@1",
        ),
        (("observedAt",), "2026-09-27T08:31:00Z"),
        (("payload", "repository"), "stateforge-org/stateforge-agent"),
        (("payload", "ref"), "refs/heads/main"),
        (
            ("payload", "commitSha"),
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
    ],
)
def test_every_semantic_change_changes_canonical_content(
    publication_data,
    path,
    replacement,
) -> None:
    changed = copy.deepcopy(publication_data)
    cursor = changed["publication"]
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = replacement

    assert _content_fingerprint(changed) != (
        _content_fingerprint(publication_data)
    )


def test_idempotency_scenarios_preserve_one_logical_event() -> None:
    scenarios = {
        item["scenario"]: item
        for item in _read_json("publication-scenarios.json")
    }

    assert set(scenarios) == {
        "first_valid_publication",
        "identical_replay",
        "lost_acknowledgement",
        "agent_restart_after_commit_before_ack",
        "same_id_different_content",
        "crash_before_durable_acceptance",
    }
    assert all(
        scenario["durableRecordCount"] == 1 for scenario in scenarios.values()
    )
    assert scenarios["lost_acknowledgement"]["expected"] == (
        "TRIGGER_ACKNOWLEDGEMENT_DISPOSITION_ACCEPTED_DUPLICATE"
    )
    assert scenarios["same_id_different_content"]["expected"] == (
        "TRIGGER_REJECTION_REASON_IDEMPOTENCY_CONFLICT"
    )


def test_stream_scenarios_cover_framing_session_and_backpressure() -> None:
    scenarios = {
        item["scenario"]: item for item in _read_json("stream-scenarios.json")
    }

    assert set(scenarios) == {
        "valid_open",
        "acknowledgement_before_open",
        "publication_before_ready",
        "stale_session_or_manifest",
        "receive_window_exceeded",
        "ready_binding_mismatch",
    }
    assert scenarios["valid_open"]["expectedOutcome"] == "OK"
    assert scenarios["acknowledgement_before_open"]["expectedWireStatus"] == (
        "INVALID_ARGUMENT"
    )
    assert scenarios["stale_session_or_manifest"]["expectedWireStatus"] == (
        "FAILED_PRECONDITION"
    )
    assert scenarios["publication_before_ready"]["expectedAgentError"] == (
        "INTERNAL"
    )
    assert scenarios["receive_window_exceeded"]["expectedAgentError"] == (
        "RESOURCE_EXHAUSTED"
    )
    assert scenarios["ready_binding_mismatch"]["expectedAgentError"] == (
        "FAILED_PRECONDITION"
    )
    assert all(
        scenario["providerObserves"] == "CANCELLED_OR_TRANSPORT_CLOSED"
        for scenario in scenarios.values()
        if scenario["detectingPeer"] == "AGENT"
    )


def test_structural_bounds_reject_oversized_values(
    publication_data,
) -> None:
    maximum_string = copy.deepcopy(publication_data)
    maximum_string["publication"]["payload"]["repository"] = (
        "x" * contract.MAX_PAYLOAD_STRING_CODE_POINTS
    )
    _RESPONSE_VALIDATOR.validate(maximum_string)

    oversized_payload = copy.deepcopy(publication_data)
    oversized_payload["publication"]["payload"]["repository"] = "x" * (
        contract.MAX_PAYLOAD_STRING_CODE_POINTS + 1
    )
    with pytest.raises(ValidationError):
        _RESPONSE_VALIDATOR.validate(oversized_payload)

    maximum_property_name = copy.deepcopy(publication_data)
    maximum_property_name["publication"]["payload"] = {
        "😀" * contract.MAX_PAYLOAD_PROPERTY_NAME_CODE_POINTS: "value"
    }
    _RESPONSE_VALIDATOR.validate(maximum_property_name)

    oversized_property_name = copy.deepcopy(publication_data)
    oversized_property_name["publication"]["payload"] = {
        "😀" * (contract.MAX_PAYLOAD_PROPERTY_NAME_CODE_POINTS + 1): "value"
    }
    with pytest.raises(ValidationError):
        _RESPONSE_VALIDATOR.validate(oversized_property_name)

    oversized_window = _read_json("open.json")
    oversized_window["open"]["requestedMaxInFlightPublications"] = (
        contract.MAX_IN_FLIGHT_PUBLICATIONS + 1
    )
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(oversized_window)


def test_generation_outside_uint64_cannot_enter_wire_message() -> None:
    with pytest.raises(ValueError, match="range"):
        trigger_publication_pb2.TriggerSessionBinding(
            expected_endpoint_generation=2**64
        )


def test_trigger_publication_documentation_matches_exported_limits() -> None:
    documentation = (
        _ROOT / "docs" / "v0.1.0" / "procedures" / "triggers.md"
    ).read_text(encoding="utf-8")

    assert (
        f"| Agent-to-Provider stream envelope | "
        f"{contract.MAX_REQUEST_BYTES // 1024} KiB serialized |"
        in documentation
    )
    assert (
        f"| Provider-to-Agent stream envelope | "
        f"{contract.MAX_RESPONSE_BYTES // (1024 * 1024)} MiB serialized |"
        in documentation
    )
    assert (
        f"| Canonical payload JSON | "
        f"{contract.MAX_CANONICAL_PAYLOAD_BYTES // (1024 * 1024)} MiB |"
        in documentation
    )
    assert (
        f"{contract.MAX_IN_FLIGHT_PUBLICATIONS:,} publications"
        in documentation
    )
    assert "trigger_publication/v1/contract.py" in documentation
    assert "trigger_publication/v1/validation.py" in documentation


def test_trigger_publication_walkthrough_covers_every_scenario() -> None:
    declaration = yaml.safe_load(
        (_ROOT / "docs" / "v0.1.0" / "procedures" / "triggers.yaml").read_text(
            encoding="utf-8"
        )
    )
    expected_markers = {
        "success": "ACCEPTED_NEW",
        "duplicate-replay": "ACCEPTED_DUPLICATE",
        "lost-acknowledgement": "Replay the same publication",
        "idempotency-conflict": "IDEMPOTENCY_CONFLICT",
        "retryable-rejection": "AGENT_CAPACITY_EXHAUSTED",
        "payload-rejected": "PAYLOAD_SCHEMA_VIOLATION",
        "acknowledgement-before-open": "INVALID_ARGUMENT",
        "stale-binding": "FAILED_PRECONDITION",
        "active-stream-exists": "ALREADY_EXISTS",
        "ready-mismatch": "Local FAILED_PRECONDITION",
        "publication-before-ready": "Local INTERNAL",
        "receive-window-exceeded": "Local RESOURCE_EXHAUSTED",
        "invalid-acknowledgement": "INVALID_ARGUMENT",
        "session-lost": "UNAVAILABLE",
    }

    assert set(declaration["scenarios"]) == set(expected_markers)
    for scenario_id, marker in expected_markers.items():
        serialized = json.dumps(declaration["scenarios"][scenario_id])
        assert marker in serialized


def test_trigger_publication_overview_tracks_delivery_responsibility() -> None:
    declaration = yaml.safe_load(
        (
            _ROOT
            / "docs"
            / "v0.1.0"
            / "procedures"
            / "trigger-publication-overview.yaml"
        ).read_text(encoding="utf-8")
    )

    assert declaration["schema"] == "stateforge.docs/entity-flow/v1"
    assert [entity["id"] for entity in declaration["entities"]] == [
        "nginx",
        "systemd",
        "provider",
        "agent",
    ]
    assert [step["id"] for step in declaration["steps"]] == [
        "nginx-fails",
        "provider-observes",
        "retain-publication",
        "publish-trigger",
        "accept-durably",
        "acknowledge",
        "release-publication",
    ]
    assert declaration["steps"][3]["responsibility"]["entities"] == [
        "provider"
    ]
    assert declaration["steps"][4]["responsibility"]["entities"] == ["agent"]
    assert declaration["steps"][5]["transitions"] == [
        {
            "source": "agent",
            "target": "provider",
            "label": "ACCEPTED_NEW",
            "tone": "success",
        }
    ]


def test_documented_trigger_protojson_matches_the_contract() -> None:
    documentation = (
        _ROOT / "docs" / "v0.1.0" / "procedures" / "triggers.md"
    ).read_text(encoding="utf-8")
    open_data = annotated_json_example(
        documentation,
        title="StreamTriggersRequest · open",
    )
    ready_data = annotated_json_example(
        documentation,
        title="StreamTriggersResponse · ready",
    )
    publication_data = annotated_json_example(
        documentation,
        title="StreamTriggersResponse · publication",
    )
    accepted_data = annotated_json_example(
        documentation,
        title="StreamTriggersRequest · accepted",
    )
    rejected_data = annotated_json_example(
        documentation,
        title="StreamTriggersRequest · rejected",
    )

    assert open_data == _read_json("open.json")
    assert ready_data == _read_json("ready.json")
    assert publication_data == _read_json("publication.json")
    assert accepted_data == _read_json("acknowledgement-accepted-new.json")
    assert rejected_data == _read_json("acknowledgement-rejected.json")

    for data in (open_data, accepted_data, rejected_data):
        _REQUEST_VALIDATOR.validate(data)
    for data in (ready_data, publication_data):
        _RESPONSE_VALIDATOR.validate(data)

    open_message = json_format.ParseDict(
        open_data,
        trigger_publication_pb2.StreamTriggersRequest(),
    )
    ready_message = json_format.ParseDict(
        ready_data,
        trigger_publication_pb2.StreamTriggersResponse(),
    )
    publication_message = json_format.ParseDict(
        publication_data,
        trigger_publication_pb2.StreamTriggersResponse(),
    )
    accepted_message = json_format.ParseDict(
        accepted_data,
        trigger_publication_pb2.StreamTriggersRequest(),
    )
    rejected_message = json_format.ParseDict(
        rejected_data,
        trigger_publication_pb2.StreamTriggersRequest(),
    )

    validation.validate_stream_request(open_message)
    validation.validate_stream_response(ready_message)
    validation.validate_stream_open_exchange(
        open_message.open,
        ready_message.ready,
    )
    validation.validate_stream_response(publication_message)
    validation.validate_stream_request(accepted_message)
    validation.validate_publication_acknowledgement(
        publication_message.publication,
        accepted_message.acknowledgement,
    )
    validation.validate_stream_request(rejected_message)
