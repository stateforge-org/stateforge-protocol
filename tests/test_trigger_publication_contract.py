"""Conformance vectors for trigger publication and acknowledgement."""

import copy
import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest
import rfc8785
from google.protobuf import json_format
from jsonschema import Draft202012Validator, ValidationError

from stateforge_protocol.sfp.manifest.v1 import manifest_pb2
from stateforge_protocol.sfp.trigger_publication.v1 import (
    trigger_publication_pb2,
)

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

    assert service.full_name == (
        "stateforge.sfp.trigger_publication.v1.TriggerPublicationService"
    )
    assert tuple(service.methods_by_name) == ("StreamTriggers",)
    assert method.input_type == (
        trigger_publication_pb2.StreamTriggersRequest.DESCRIPTOR
    )
    assert method.output_type == (
        trigger_publication_pb2.StreamTriggersResponse.DESCRIPTOR
    )
    assert method.client_streaming
    assert method.server_streaming


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

    assert _canonical_content(publication_data).decode() == (
        vector["canonicalJson"]
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
    }
    assert scenarios["valid_open"]["expectedStatus"] == "OK"
    assert scenarios["stale_session_or_manifest"]["expectedStatus"] == (
        "FAILED_PRECONDITION"
    )
    assert scenarios["receive_window_exceeded"]["expectedStatus"] == (
        "RESOURCE_EXHAUSTED"
    )


def test_structural_bounds_reject_oversized_values(
    publication_data,
) -> None:
    oversized_payload = copy.deepcopy(publication_data)
    oversized_payload["publication"]["payload"]["repository"] = "x" * 65537
    with pytest.raises(ValidationError):
        _RESPONSE_VALIDATOR.validate(oversized_payload)

    oversized_window = _read_json("open.json")
    oversized_window["open"]["requestedMaxInFlightPublications"] = 1025
    with pytest.raises(ValidationError):
        _REQUEST_VALIDATOR.validate(oversized_window)


def test_generation_outside_uint64_cannot_enter_wire_message() -> None:
    with pytest.raises(ValueError, match="range"):
        trigger_publication_pb2.TriggerSessionBinding(
            expected_endpoint_generation=2**64
        )
