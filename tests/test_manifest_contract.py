"""Conformance vectors for the manifest wire and validation schemas."""

import copy
import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest
import rfc8785
from google.protobuf import descriptor_pb2, json_format
from google.protobuf.descriptor import FieldDescriptor
from jsonschema import Draft202012Validator, ValidationError

from stateforge_protocol.sfp.manifest.v1 import contract, manifest_pb2

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


def test_versioned_contract_exposes_normative_limits() -> None:
    expected = {
        "MAX_REQUEST_BYTES": 8 * 1024,
        "MAX_RESPONSE_BYTES": 2 * 1024 * 1024,
        "MAX_CANONICAL_REVISION_PREIMAGE_BYTES": 1 * 1024 * 1024,
        "MAX_EMBEDDED_JSON_DEPTH": 64,
        "MAX_OPERATIONS": 1_024,
        "MAX_TRIGGERS": 1_024,
        "MAX_RUNTIME_REQUIREMENTS": 1_024,
        "MAX_PLATFORMS": 256,
        "MAX_PROFILE_CLAIMS_PER_OPERATION": 64,
    }

    assert {name: getattr(contract, name) for name in expected} == expected


def test_versioned_contract_limits_match_packaged_schema() -> None:
    definitions = _SCHEMA["$defs"]
    manifest = definitions["providerManifest"]["properties"]

    assert manifest["operations"]["maxProperties"] == contract.MAX_OPERATIONS
    assert manifest["triggers"]["maxProperties"] == contract.MAX_TRIGGERS
    assert (
        manifest["runtimeRequirements"]["maxProperties"]
        == contract.MAX_RUNTIME_REQUIREMENTS
    )
    assert manifest["platforms"]["maxItems"] == contract.MAX_PLATFORMS
    assert (
        definitions["operation"]["properties"]["implements"]["maxItems"]
        == contract.MAX_PROFILE_CLAIMS_PER_OPERATION
    )


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
        expected_session_id="manifest-session-A",
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
        "expectedSessionId": "manifest-session-A",
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

    assert service.full_name == contract.SERVICE_NAME
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


def test_provider_manifest_has_no_generic_target_kinds() -> None:
    descriptor = manifest_pb2.ProviderManifest.DESCRIPTOR
    assert "target_kinds" not in descriptor.fields_by_name
    message = descriptor_pb2.DescriptorProto()
    descriptor.CopyToProto(message)
    assert not message.reserved_range
    assert not message.reserved_name
    schema = _SCHEMA["$defs"]["providerManifest"]
    assert "targetKinds" not in schema["properties"]
    assert "targetKinds" not in schema["required"]


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
        (("manifest", "targetKinds"), ["stateforge.git/repository@1"]),
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


def test_unchanged_revision_is_independent_of_map_order_and_generation(
    response,
) -> None:
    original = _preimage(response)
    response["endpointGeneration"] = "5"
    response["manifest"] = dict(reversed(response["manifest"].items()))
    assert _preimage(response) == original


@pytest.mark.parametrize(
    "change",
    ["identity", "version", "configuration", "operation", "profile", "result"],
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
    elif change == "result":
        next(iter(manifest["operations"].values()))["resultSchema"][
            "properties"
        ] = {"count": {"type": "integer"}}
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


def test_operation_fields_and_legacy_reservations():
    descriptor = manifest_pb2.OperationDeclaration.DESCRIPTOR
    assert {field.name: field.number for field in descriptor.fields} == {
        "input_schema": 1,
        "result_schema": 2,
        "implements": 3,
    }
    proto = descriptor_pb2.DescriptorProto()
    descriptor.CopyToProto(proto)
    assert [(item.start, item.end) for item in proto.reserved_range] == [
        (4, 5)
    ]
    assert list(proto.reserved_name) == ["backup_source_modes"]


def test_checked_in_legacy_property_fixture_is_rejected():
    response = json.loads(
        (_FIXTURES / "invalid-backup-source-modes.json").read_text()
    )
    with pytest.raises(ValidationError, match="Additional properties"):
        Draft202012Validator(_SCHEMA).validate(response)
    with pytest.raises(json_format.ParseError, match="backupSourceModes"):
        json_format.ParseDict(response, manifest_pb2.GetManifestResponse())


@pytest.mark.parametrize("field", ["backupSourceModes", "backup_source_modes"])
@pytest.mark.parametrize("value", [[], ["provider_reference"]])
def test_no_legacy_property_even_when_empty(response, field, value):
    operation = next(iter(response["manifest"]["operations"].values()))
    operation[field] = value
    with pytest.raises(ValidationError, match="Additional properties"):
        Draft202012Validator(_SCHEMA).validate(response)


@pytest.mark.parametrize(
    "field", ["inputSchema", "resultSchema", "implements"]
)
def test_all_declaration_fields_are_explicitly_required(response, field):
    operation = next(iter(response["manifest"]["operations"].values()))
    del operation[field]
    with pytest.raises(ValidationError, match="required property"):
        Draft202012Validator(_SCHEMA).validate(response)


@pytest.mark.parametrize(
    ("identifier", "roles"),
    [
        ("stateforge.git/reference.resolve@1", []),
        ("example.vendor/backup.prepare@3", []),
        ("example.vendor/collect@1", ["stateforge.backup.v1.prepare"]),
        (
            "example.vendor/reconstruct@1",
            ["stateforge.disaster_recovery.v1.reconstruct"],
        ),
        ("example.vendor/custom@2", ["example.vendor.manifest_pb2.custom"]),
    ],
)
def test_all_operation_categories_share_generic_declaration(
    response, identifier, roles
):
    # These are structural claim examples, not certification of the future
    # backup/DR profiles. Their exact schemas belong to those milestones.
    operation = next(iter(response["manifest"]["operations"].values()))
    operation["implements"] = roles
    response["manifest"]["operations"] = {identifier: operation}
    Draft202012Validator(_SCHEMA).validate(response)
    message = json_format.ParseDict(
        response, manifest_pb2.GetManifestResponse()
    )
    projected = json_format.MessageToDict(
        message, always_print_fields_with_no_presence=True
    )["manifest"]["operations"][identifier]
    assert projected == operation
    assert set(projected) == {"inputSchema", "resultSchema", "implements"}
    assert projected["implements"] == roles


def test_incidental_result_shape_creates_no_manifest_semantics(response):
    operation = next(iter(response["manifest"]["operations"].values()))
    # A custom schema can use these words as data without a compliance role.
    operation["resultSchema"]["properties"] = {
        "backupSourceModes": {"type": "string"},
        "kind": {"enum": ["materialized_source", "provider_reference"]},
    }
    Draft202012Validator(_SCHEMA).validate(response)
    message = json_format.ParseDict(
        response, manifest_pb2.GetManifestResponse()
    )
    projected = json_format.MessageToDict(
        message, always_print_fields_with_no_presence=True
    )
    assert projected == response
    assert not operation["implements"]
    assert set(operation) == {"inputSchema", "resultSchema", "implements"}


@pytest.mark.parametrize("field", ["inputSchema", "resultSchema"])
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("$schema", "http://json-schema.org/draft-07/schema#"),
        ("type", "string"),
        ("required", "invalid"),
        ("$ref", "https://example.invalid/schema"),
        ("$id", "urn:example:change-base"),
    ],
)
def test_input_and_result_schemas_use_bounded_draft_2020_12(
    response, field, key, value
):
    operation = next(iter(response["manifest"]["operations"].values()))
    operation[field][key] = value
    with pytest.raises(ValidationError):
        Draft202012Validator(_SCHEMA).validate(response)


def test_revision_ignores_nested_map_order_and_generation(response):
    before = _preimage(response)

    def reverse_maps(value):
        if isinstance(value, dict):
            return {
                key: reverse_maps(item)
                for key, item in reversed(value.items())
            }
        if isinstance(value, list):
            return [reverse_maps(item) for item in value]
        return value

    reordered = reverse_maps(response)
    reordered["endpointGeneration"] = "5"
    assert _preimage(reordered) == before
