"""Executable semantic-validation evidence for Provider Manifest v1."""

import copy
import json
from pathlib import Path

import pytest
from google.protobuf.json_format import ParseDict

from stateforge_protocol.sfp.manifest.v1 import contract, manifest_pb2
from stateforge_protocol.sfp.manifest.v1.validation import (
    ManifestValidationError,
    ManifestValidationLimits,
    bounded_json,
    canonical_bytes,
    compute_manifest_revision,
    contract_validator,
    validate_manifest_key,
    validate_manifest_response,
    validate_schema,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "manifest"
_GOLDEN_REVISION = (
    "sha256:6bfdf3aedc2d4e45d77d4787cc0e744a488208b2510d81788291f51d24a623e8"
)


def _response() -> manifest_pb2.GetManifestResponse:
    document = json.loads((_FIXTURES / "response.json").read_text())
    return ParseDict(document, manifest_pb2.GetManifestResponse())


def _schema(**overrides):
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        **overrides,
    }


def test_validates_and_canonicalizes_the_cross_language_vector() -> None:
    response = _response()

    document = validate_manifest_response(response)

    projected = json.loads((_FIXTURES / "response.json").read_text())
    assert json.loads(document) == projected["manifest"]
    assert response.manifest_revision == _GOLDEN_REVISION
    assert (
        compute_manifest_revision(
            projected["manifest"],
            projected["manifestSchemaVersion"],
            projected["providerInstanceId"],
        )
        == _GOLDEN_REVISION
    )


def test_public_contract_validator_uses_the_packaged_schema() -> None:
    validator = contract_validator("schemaDocument")

    validator.validate(_schema())
    assert not validator.is_valid({"type": "unknown"})


def test_rejects_revision_mismatch() -> None:
    response = _response()
    response.manifest_revision = "sha256:" + ("0" * 64)

    with pytest.raises(ManifestValidationError, match="revision mismatch"):
        validate_manifest_response(response)


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef"])
def test_rejects_remote_schema_references_without_echoing_them(
    keyword: str,
) -> None:
    reference = "https://sensitive.invalid/schema"
    document = _schema(properties={"value": {keyword: reference}})

    with pytest.raises(ManifestValidationError) as error:
        validate_schema(document, "manifest.configurationSchema")

    assert reference not in str(error.value)


@pytest.mark.parametrize("keyword", ["default", "examples", "const", "enum"])
def test_rejects_indirect_secret_values_without_echoing_them(
    keyword: str,
) -> None:
    secret = "sensitive-canary-never-in-errors"  # noqa: S105
    annotation = [secret] if keyword in {"examples", "enum"} else secret
    document = _schema(
        properties={"token": {"$ref": "#/$defs/secret"}},
        **{
            "$defs": {
                "secret": {
                    "type": "string",
                    "writeOnly": True,
                    keyword: annotation,
                }
            }
        },
    )

    with pytest.raises(ManifestValidationError) as error:
        validate_schema(document, "manifest.configurationSchema")

    assert secret not in str(error.value)


def test_local_reference_propagates_write_only_secret_semantics() -> None:
    secret = "sensitive-canary-never-in-errors"  # noqa: S105
    document = _schema(
        properties={
            "token": {
                "writeOnly": True,
                "$ref": "#/$defs/tokenValue",
            }
        },
        **{
            "$defs": {
                "tokenValue": {
                    "type": "string",
                    "default": secret,
                }
            }
        },
    )

    with pytest.raises(ManifestValidationError) as error:
        validate_schema(document, "manifest.configurationSchema")

    assert secret not in str(error.value)


def test_rejects_nested_schema_dialect_changes() -> None:
    document = _schema(
        properties={
            "value": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "string",
            }
        }
    )

    with pytest.raises(ManifestValidationError, match="nested schema dialect"):
        validate_schema(document, "manifest.configurationSchema")


def test_enforces_contract_and_tighter_runtime_resource_limits() -> None:
    with pytest.raises(ValueError, match="max_json_nodes"):
        ManifestValidationLimits(max_json_nodes=contract.MAX_JSON_NODES + 1)
    with pytest.raises(ValueError, match="max_schema_nodes"):
        ManifestValidationLimits(
            max_schema_nodes=contract.MAX_SCHEMA_NODES + 1
        )

    limits = ManifestValidationLimits(max_json_nodes=2, max_schema_nodes=1)
    with pytest.raises(ManifestValidationError, match="resource limit"):
        bounded_json(
            {"first": None, "second": None},
            "manifest",
            limits=limits,
        )
    schema_limits = ManifestValidationLimits(
        max_json_nodes=100,
        max_schema_nodes=1,
    )
    with pytest.raises(ManifestValidationError, match="schema node limit"):
        validate_schema(
            _schema(properties={"value": {"type": "string"}}),
            "manifest.configurationSchema",
            limits=schema_limits,
        )


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), 2**53 + 1, "\ud800"],
)
def test_rejects_non_interoperable_canonical_json(value: object) -> None:
    with pytest.raises(ManifestValidationError):
        canonical_bytes({"value": value})


def test_validates_manifest_revision_cache_keys() -> None:
    response = _response()

    key = validate_manifest_key(
        response.provider_instance_id,
        response.manifest_schema_version,
        response.manifest_revision,
    )

    assert str(key.provider_instance_id) == response.provider_instance_id
    assert key.schema_version == response.manifest_schema_version
    assert key.revision == response.manifest_revision

    invalid = copy.deepcopy(response)
    invalid.manifest_revision = "not-a-revision"
    with pytest.raises(ManifestValidationError, match="revision"):
        validate_manifest_key(
            invalid.provider_instance_id,
            invalid.manifest_schema_version,
            invalid.manifest_revision,
        )


@pytest.mark.parametrize(
    ("provider_instance_id", "schema_version", "message"),
    [
        ("not-a-uuid", 1, "identity"),
        ("7F7DB7D8-68B4-4F71-9769-065B5C4F941C", 1, "identity"),
        ("7f7db7d8-68b4-4f71-9769-065b5c4f941c", 0, "schema version"),
        ("7f7db7d8-68b4-4f71-9769-065b5c4f941c", True, "schema version"),
    ],
)
def test_manifest_cache_key_rejects_invalid_identity_or_version(
    provider_instance_id: str,
    schema_version: int,
    message: str,
) -> None:
    with pytest.raises(ManifestValidationError, match=message):
        validate_manifest_key(
            provider_instance_id,
            schema_version,
            "sha256:" + ("a" * 64),
        )
