"""Conformance vectors for the manifest wire and validation schemas."""

import copy
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


@pytest.fixture
def response():
    return json.loads((_FIXTURES / "response.json").read_text())


@pytest.fixture
def validator():
    return Draft202012Validator(_SCHEMA)


def _preimage(response):
    return rfc8785.dumps(
        {
            key: response[key]
            for key in (
                "manifest",
                "manifestSchemaVersion",
                "providerInstanceId",
            )
        }
    )


def test_validation_schema_is_valid() -> None:
    Draft202012Validator.check_schema(_SCHEMA)


def test_response_round_trip_preserves_canonical_representation(
    response, validator
) -> None:
    validator.validate(response)
    message = json_format.ParseDict(
        response, manifest_pb2.GetManifestResponse()
    )
    decoded = manifest_pb2.GetManifestResponse.FromString(
        message.SerializeToString()
    )
    projected = json_format.MessageToDict(
        decoded, always_print_fields_with_no_presence=True
    )

    assert decoded == message
    assert projected == response
    assert (
        _preimage(projected)
        == (_FIXTURES / "revision-preimage.json").read_bytes()
    )
    assert (
        "sha256:" + hashlib.sha256(_preimage(projected)).hexdigest()
        == response["manifestRevision"]
    )


def test_request_round_trip_and_offer_order() -> None:
    request = manifest_pb2.GetManifestRequest(
        expected_provider_instance_id="7f7db7d8-68b4-4f71-9769-065b5c4f941c",
        expected_endpoint_generation=4,
        supported_manifest_schema_versions=[2, 1],
    )
    decoded = manifest_pb2.GetManifestRequest.FromString(
        request.SerializeToString()
    )
    request_schema = {
        "$ref": "#/$defs/getManifestRequest",
        "$defs": _SCHEMA["$defs"],
    }
    Draft202012Validator(request_schema).validate(
        json_format.MessageToDict(decoded)
    )
    assert decoded == request
    assert list(decoded.supported_manifest_schema_versions) == [2, 1]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expectedProviderInstanceId", ""),
        ("expectedProviderInstanceId", "not-a-uuid"),
        ("expectedEndpointGeneration", "0"),
        ("expectedEndpointGeneration", "01"),
        ("supportedManifestSchemaVersions", []),
        ("supportedManifestSchemaVersions", [0]),
        ("supportedManifestSchemaVersions", [1, 1]),
        ("supportedManifestSchemaVersions", list(range(1, 34))),
    ],
)
def test_invalid_request_declarations(field, value) -> None:
    request = {
        "expectedProviderInstanceId": ("7f7db7d8-68b4-4f71-9769-065b5c4f941c"),
        "expectedEndpointGeneration": "4",
        "supportedManifestSchemaVersions": [1],
    }
    request[field] = value
    request_schema = {
        "$ref": "#/$defs/getManifestRequest",
        "$defs": _SCHEMA["$defs"],
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(request_schema).validate(request)


def test_generation_outside_uint64_cannot_enter_wire_message() -> None:
    with pytest.raises(ValueError, match="range"):
        manifest_pb2.GetManifestRequest(expected_endpoint_generation=2**64)


def test_service_is_versioned_and_unary() -> None:
    service = manifest_pb2.DESCRIPTOR.services_by_name["ManifestService"]
    method = service.methods_by_name["GetManifest"]

    assert service.full_name == "stateforge.sfp.manifest.v1.ManifestService"
    assert tuple(service.methods_by_name) == ("GetManifest",)
    assert method.input_type == manifest_pb2.GetManifestRequest.DESCRIPTOR
    assert method.output_type == manifest_pb2.GetManifestResponse.DESCRIPTOR
    assert not method.client_streaming
    assert not method.server_streaming


def test_operation_identifiers_are_string_map_keys() -> None:
    field = manifest_pb2.ProviderManifest.DESCRIPTOR.fields_by_name[
        "operations"
    ]
    assert field.message_type.GetOptions().map_entry
    assert (
        field.message_type.fields_by_name["key"].type
        == FieldDescriptor.TYPE_STRING
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("providerInstanceId",), "7F7DB7D8-68B4-4F71-9769-065B5C4F941C"),
        (("endpointGeneration",), "0"),
        (("manifestSchemaVersion",), 0),
        (("manifestSchemaVersion",), 2),
        (("manifestRevision",), "sha256:bad"),
        (("manifest", "providerIdentity"), "git"),
        (("manifest", "providerIdentity"), "stateforge.git\n"),
        (("manifest", "implementationVersion"), "1.0"),
        (("manifest", "implementationVersion"), "1.0.0\n"),
        (("manifest", "implementationVersion"), "1.0.0-01"),
        (("manifest", "displayName"), ""),
        (("manifest", "platforms"), []),
        (("manifest", "targetKinds"), ["repository"]),
        (("manifest", "targetKinds"), ["stateforge.git/repository@1"] * 2),
        (("manifest", "configuration"), {"token": "must-not-be-sent"}),
        (("manifest", "configurationSchema", "type"), "invalid-type"),
        (("manifest", "configurationSchema", "required"), "repository"),
        (("manifest", "configurationSchema", "$ref"), "https://example.com"),
        (("manifest", "configurationSchema", "$id"), "https://example.com"),
    ],
)
def test_invalid_or_incompatible_manifests_are_rejected(
    response, validator, path, value
) -> None:
    target = response
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        validator.validate(response)


@pytest.mark.parametrize("field", ["manifest", "manifestRevision"])
def test_success_requires_complete_manifest(response, validator, field):
    del response[field]
    with pytest.raises(ValidationError):
        validator.validate(response)


@pytest.mark.parametrize("keyword", ["default", "examples", "const", "enum"])
@pytest.mark.parametrize("nested", [False, True])
def test_secret_schema_fields_cannot_embed_values(
    response, validator, keyword, nested
) -> None:
    secret = response["manifest"]["configurationSchema"]["properties"]["token"]
    value = ["secret"] if keyword in {"examples", "enum"} else "secret"
    secret[keyword] = value
    if nested:
        configuration = response["manifest"]["configurationSchema"]
        configuration["properties"]["token"] = {"$ref": "#/$defs/secret"}
        configuration["$defs"] = {"secret": secret}
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_custom_operations_do_not_imply_compliance(response, validator):
    operations = response["manifest"]["operations"]
    declaration = operations.pop("stateforge.git/reference.resolve@1")
    operations["example.vendor/backup.prepare@3"] = declaration
    validator.validate(response)

    message = json_format.ParseDict(
        response, manifest_pb2.GetManifestResponse()
    )
    assert not message.manifest.operations[
        "example.vendor/backup.prepare@3"
    ].implements


@pytest.mark.parametrize(
    "identifier",
    [
        "prepare_backup",
        "example.vendor/foo@0",
        "example.vendor/foo@01",
        "example.vendor/Foo@1",
        "example.vendor/foo@1\n",
    ],
)
def test_invalid_operation_identifiers(response, validator, identifier):
    operations = response["manifest"]["operations"]
    declaration = operations.pop("stateforge.git/reference.resolve@1")
    operations[identifier] = declaration
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_compliance_claims_and_trigger_schemas_survive_wire(
    response, validator
):
    manifest = response["manifest"]
    operation = next(iter(manifest["operations"].values()))
    operation["implements"] = ["stateforge.backup.v1.prepare"]
    operation["backupSourceModes"] = ["provider_reference"]
    manifest["triggers"]["stateforge.git/reference.changed@1"] = {
        "payloadSchema": copy.deepcopy(operation["resultSchema"])
    }
    validator.validate(response)
    message = json_format.ParseDict(
        response, manifest_pb2.GetManifestResponse()
    )
    decoded = manifest_pb2.GetManifestResponse.FromString(
        message.SerializeToString()
    )
    assert list(
        decoded.manifest.operations[
            "stateforge.git/reference.resolve@1"
        ].implements
    ) == ["stateforge.backup.v1.prepare"]
    assert "stateforge.git/reference.changed@1" in decoded.manifest.triggers


def test_backup_modes_require_explicit_profile_claim(response, validator):
    operation = next(iter(response["manifest"]["operations"].values()))
    operation["backupSourceModes"] = ["provider_reference"]
    with pytest.raises(ValidationError):
        validator.validate(response)


def test_unchanged_revision_is_independent_of_map_order_and_generation(
    response,
) -> None:
    original = _preimage(response)
    response["endpointGeneration"] = "5"
    response["manifest"] = dict(reversed(response["manifest"].items()))
    assert _preimage(response) == original


@pytest.mark.parametrize(
    "change", ["identity", "version", "configuration", "operation", "profile"]
)
def test_interoperability_changes_change_revision(response, change):
    original = hashlib.sha256(_preimage(response)).digest()
    manifest = response["manifest"]
    if change == "identity":
        response["providerInstanceId"] = "68d818de-3671-471d-a0ba-044cf60e2c8e"
    elif change == "version":
        manifest["implementationVersion"] = "1.1.0"
    elif change == "configuration":
        manifest["configurationSchema"]["properties"]["repository"][
            "minLength"
        ] = 1
    elif change == "operation":
        manifest["operations"] = {}
    else:
        next(iter(manifest["operations"].values()))["implements"] = [
            "stateforge.backup.v1.prepare"
        ]
    assert hashlib.sha256(_preimage(response)).digest() != original


def test_protobuf_decoding_does_not_perform_semantic_validation(validator):
    # Proto3 accepts defaults. Consumers must run the schema and session checks
    # before considering the Provider usable, regardless of channel health.
    empty = manifest_pb2.GetManifestResponse.FromString(b"")
    with pytest.raises(ValidationError):
        validator.validate(
            json_format.MessageToDict(
                empty, always_print_fields_with_no_presence=True
            )
        )
