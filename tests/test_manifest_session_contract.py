"""Session-binding conformance vectors, not Provider or Agent runtimes.

The message/schema checks exercise distributed artifacts. The vector predicates
specify the additional semantic obligations consumer runtimes must enforce;
protobuf and JSON Schema cannot look up an active negotiated session.
"""

import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest
import rfc8785
from google.protobuf import json_format
from google.protobuf.descriptor import FieldDescriptor
from jsonschema import Draft202012Validator, ValidationError

from stateforge_protocol.sfp.manifest.v1 import manifest_pb2

_FIXTURES = Path(__file__).parent / "fixtures" / "manifest"
_SCHEMA = json.loads(
    files("stateforge_protocol.sfp.manifest.v1")
    .joinpath("manifest.schema.json")
    .read_text()
)
_VECTORS = json.loads((_FIXTURES / "session-binding.json").read_text())
_MESSAGES = {
    "getManifestRequest": manifest_pb2.GetManifestRequest,
    "getManifestResponse": manifest_pb2.GetManifestResponse,
}
_GOLDEN = (
    "sha256:34f54f69855f1fbebef4d3d6bb74c0238785e0f8ef43f9efb1a12e6b4353183d"
)


def _fixture(definition):
    name = (
        "request.json"
        if definition == "getManifestRequest"
        else "response.json"
    )
    return json.loads((_FIXTURES / name).read_text())


def _validator(definition):
    return Draft202012Validator(
        {"$ref": f"#/$defs/{definition}", "$defs": _SCHEMA["$defs"]}
    )


def _round_trip(document, definition):
    message_type = _MESSAGES[definition]
    message = json_format.ParseDict(document, message_type())
    decoded = message_type.FromString(message.SerializeToString())
    return json_format.MessageToDict(
        decoded, always_print_fields_with_no_presence=True
    )


def test_envelope_additions_preserve_existing_field_numbers():
    for message, expected in [
        (
            manifest_pb2.GetManifestRequest,
            {
                "expected_provider_instance_id": 1,
                "expected_endpoint_generation": 2,
                "supported_manifest_schema_versions": 3,
                "expected_session_id": 4,
            },
        ),
        (
            manifest_pb2.GetManifestResponse,
            {
                "provider_instance_id": 1,
                "endpoint_generation": 2,
                "manifest_schema_version": 3,
                "manifest_revision": 4,
                "manifest": 5,
                "session_id": 6,
            },
        ),
    ]:
        assert {
            field.name: field.number for field in message.DESCRIPTOR.fields
        } == expected
    for message, name in [
        (manifest_pb2.GetManifestRequest, "expected_session_id"),
        (manifest_pb2.GetManifestResponse, "session_id"),
    ]:
        field = message.DESCRIPTOR.fields_by_name[name]
        assert field.type == FieldDescriptor.TYPE_STRING
        assert not field.is_repeated
    assert (
        "session_id"
        not in manifest_pb2.ProviderManifest.DESCRIPTOR.fields_by_name
    )


@pytest.mark.parametrize("definition", _MESSAGES)
def test_paired_wire_fixtures_validate_and_round_trip(definition):
    document = _fixture(definition)
    _validator(definition).validate(document)
    assert _round_trip(document, definition) == document
    assert (
        _fixture("getManifestResponse")["sessionId"]
        == (_fixture("getManifestRequest")["expectedSessionId"])
    )


@pytest.mark.parametrize(
    ("definition", "field"),
    [
        ("getManifestRequest", "expectedSessionId"),
        ("getManifestResponse", "sessionId"),
    ],
)
@pytest.mark.parametrize(
    "value", ["x", "A opaque/session:非UUID", "x" * 255, "é" * 255]
)
def test_session_ids_are_opaque_strings_with_code_point_bounds(
    definition, field, value
):
    document = _fixture(definition)
    document[field] = value
    _validator(definition).validate(document)
    assert _round_trip(document, definition)[field] == value


@pytest.mark.parametrize(
    ("definition", "field"),
    [
        ("getManifestRequest", "expectedSessionId"),
        ("getManifestResponse", "sessionId"),
    ],
)
@pytest.mark.parametrize("value", ["", "x" * 256, None, 123, [], {}])
def test_invalid_session_shapes_are_rejected(definition, field, value):
    document = _fixture(definition)
    document[field] = value
    with pytest.raises(ValidationError):
        _validator(definition).validate(document)


@pytest.mark.parametrize(
    ("definition", "field"),
    [
        ("getManifestRequest", "expectedSessionId"),
        ("getManifestResponse", "sessionId"),
    ],
)
def test_missing_or_defaulted_session_is_not_a_legacy_bypass(
    definition, field
):
    document = _fixture(definition)
    del document[field]
    with pytest.raises(ValidationError, match="required property"):
        _validator(definition).validate(document)
    # An older protobuf message still decodes but projects an empty default.
    # That binary compatibility does not satisfy the current session contract.
    projected = _round_trip(document, definition)
    assert projected[field] == ""
    with pytest.raises(ValidationError):
        _validator(definition).validate(projected)


def test_session_bounds_match_capability_assessment():
    assessment_schema = json.loads(
        files("stateforge_protocol.sfp.capability_assessment.v1")
        .joinpath("capability_assessment.schema.json")
        .read_text()
    )
    assert (
        _SCHEMA["$defs"]["sessionId"]
        == assessment_schema["$defs"]["sessionId"]
    )


@pytest.mark.parametrize("case", _VECTORS["providerCases"])
def test_provider_session_validation_conformance(case):
    request = _fixture("getManifestRequest")
    if "sessionId" in case:
        request["expectedSessionId"] = case["sessionId"]
    else:
        del request["expectedSessionId"]
    if not _validator("getManifestRequest").is_valid(request):
        status = "INVALID_ARGUMENT"
    else:
        request = _round_trip(request, "getManifestRequest")
        session = _VECTORS["sessions"].get(request["expectedSessionId"])
        matches = (
            session is not None
            and session["active"]
            and session["providerInstanceId"]
            == request["expectedProviderInstanceId"]
            and session["endpointGeneration"]
            == request["expectedEndpointGeneration"]
        )
        status = "OK" if matches else "FAILED_PRECONDITION"
    assert status == case["status"]


@pytest.mark.parametrize("case", _VECTORS["agentCases"])
def test_agent_rejects_wrong_or_superseded_response_session(case):
    response = _fixture("getManifestResponse")
    response["sessionId"] = case["responseSession"]
    _validator("getManifestResponse").validate(response)
    projected = _round_trip(response, "getManifestResponse")
    # Identity, generation and revision are identical in every case. A valid
    # shape or cached revision does not let a late/wrong-session reply through.
    matches = (
        projected["sessionId"]
        == case["requestSession"]
        == case["currentSession"]
    )
    assert matches == case["accept"]


def test_session_changes_preserve_exact_canonical_preimage_and_golden():
    response = _fixture("getManifestResponse")
    for session_id in ("manifest-session-A", "manifest-session-B"):
        response["sessionId"] = session_id
        response = _round_trip(response, "getManifestResponse")
        preimage = rfc8785.dumps(
            {
                key: response[key]
                for key in (
                    "manifest",
                    "manifestSchemaVersion",
                    "providerInstanceId",
                )
            }
        )
        assert preimage == (_FIXTURES / "revision-preimage.json").read_bytes()
        assert "sha256:" + hashlib.sha256(preimage).hexdigest() == _GOLDEN
        assert response["manifestRevision"] == _GOLDEN
