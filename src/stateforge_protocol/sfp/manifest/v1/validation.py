"""Validate the complete Provider Manifest v1 semantic contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from stateforge_protocol.sfp import _validation
from stateforge_protocol.sfp.manifest.v1 import (
    _schema_inspection,
    contract,
    manifest_pb2,
)

if TYPE_CHECKING:
    from jsonschema import Draft202012Validator

__all__ = [
    "DEFAULT_VALIDATION_LIMITS",
    "JSON_SCHEMA_DRAFT_2020_12_URI",
    "ManifestRevisionKey",
    "ManifestValidationError",
    "ManifestValidationLimits",
    "bounded_json",
    "canonical_bytes",
    "compute_manifest_revision",
    "contract_validator",
    "validate_manifest_document",
    "validate_manifest_key",
    "validate_manifest_response",
    "validate_schema",
    "validate_structure",
]

JSON_SCHEMA_DRAFT_2020_12_URI = (
    _schema_inspection.JSON_SCHEMA_DRAFT_2020_12_URI
)

_SCHEMA: Final = _validation.PackagedSchema(
    package="stateforge_protocol.sfp.manifest.v1",
    resource="manifest.schema.json",
    contract_name="P1",
)


class ManifestValidationError(ValueError):
    """Report invalid Manifest data without exposing rejected values."""


_VALIDATION: Final = _validation.ValidationContext(ManifestValidationError)


@dataclass(frozen=True, slots=True)
class ManifestValidationLimits:
    """Apply optional tighter runtime budgets within the v1 contract."""

    max_json_nodes: int = contract.MAX_JSON_NODES
    max_schema_nodes: int = contract.MAX_SCHEMA_NODES

    def __post_init__(self) -> None:
        """Reject budgets outside the interoperable contract."""
        for name, maximum in (
            ("max_json_nodes", contract.MAX_JSON_NODES),
            ("max_schema_nodes", contract.MAX_SCHEMA_NODES),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= maximum
            ):
                raise ValueError(f"{name} must be from 1 through {maximum}")


DEFAULT_VALIDATION_LIMITS = ManifestValidationLimits()


@dataclass(frozen=True, slots=True)
class ManifestRevisionKey:
    """Identify one structurally valid versioned manifest declaration."""

    provider_instance_id: UUID
    schema_version: int
    revision: str


def bounded_json(
    value: object,
    path: str,
    *,
    depth_limit: int = contract.MAX_EMBEDDED_JSON_DEPTH,
    limits: ManifestValidationLimits = DEFAULT_VALIDATION_LIMITS,
) -> None:
    """Reject excessive or non-JSON content before schema processing."""
    _VALIDATION.require_bounded_json(
        value,
        path,
        maximum_depth=depth_limit,
        maximum_nodes=limits.max_json_nodes,
        maximum_bytes=contract.MAX_CANONICAL_REVISION_PREIMAGE_BYTES,
    )


def canonical_bytes(value: dict[str, Any]) -> bytes:
    """Return bounded RFC 8785 bytes for a JSON-compatible object."""
    return _VALIDATION.canonicalize_json(
        value,
        maximum_bytes=contract.MAX_CANONICAL_REVISION_PREIMAGE_BYTES,
        limit_message="manifest: canonical preimage limit exceeded",
        invalid_message="manifest: non-interoperable JSON value",
    )


def contract_validator(definition: str) -> Draft202012Validator:
    """Load a validation projection from the installed Protocol package."""
    return _SCHEMA.validator(definition)


def validate_structure(value: object, definition: str, path: str) -> None:
    """Validate one packaged ProtoJSON projection without leaking values."""
    _VALIDATION.validate_schema_definition(
        _SCHEMA,
        value,
        definition,
        path,
    )


def validate_schema(
    document: dict[str, Any],
    path: str,
    *,
    limits: ManifestValidationLimits = DEFAULT_VALIDATION_LIMITS,
) -> None:
    """Resolve local schema references and reject indirect secret values."""
    bounded_json(document, path, limits=limits)
    canonical_bytes(document)
    validate_structure(document, "schemaDocument", path)
    _schema_inspection.inspect_schema(
        document,
        path,
        maximum_nodes=limits.max_schema_nodes,
        error_type=ManifestValidationError,
    )


def validate_manifest_document(
    document: dict[str, Any],
    *,
    limits: ManifestValidationLimits = DEFAULT_VALIDATION_LIMITS,
) -> bytes:
    """Validate and canonicalize one complete manifest declaration."""
    bounded_json(
        document,
        "manifest",
        depth_limit=contract.MAX_EMBEDDED_JSON_DEPTH + 4,
        limits=limits,
    )
    validate_structure(document, "providerManifest", "manifest")
    _validate_embedded_schemas(document, limits=limits)
    return canonical_bytes(document)


def compute_manifest_revision(
    manifest: dict[str, Any],
    manifest_schema_version: int,
    provider_instance_id: str,
) -> str:
    """Return the canonical revision for a validated declaration."""
    validate_structure(
        provider_instance_id, "instanceId", "providerInstanceId"
    )
    _validate_schema_version(manifest_schema_version)
    preimage = canonical_bytes(
        {
            "manifest": manifest,
            "manifestSchemaVersion": manifest_schema_version,
            "providerInstanceId": provider_instance_id,
        }
    )
    return "sha256:" + hashlib.sha256(preimage).hexdigest()


def validate_manifest_response(
    response: manifest_pb2.GetManifestResponse,
    *,
    limits: ManifestValidationLimits = DEFAULT_VALIDATION_LIMITS,
) -> bytes:
    """Validate a response and return its canonical manifest bytes."""
    projected = _VALIDATION.project_message(response, "response")
    bounded_json(
        projected,
        "response",
        depth_limit=contract.MAX_EMBEDDED_JSON_DEPTH + 4,
        limits=limits,
    )
    validate_structure(projected, "getManifestResponse", "response")
    manifest = projected.get("manifest")
    if not isinstance(manifest, dict):
        raise ManifestValidationError("response: manifest must be an object")
    document = validate_manifest_document(manifest, limits=limits)
    revision = compute_manifest_revision(
        manifest,
        response.manifest_schema_version,
        response.provider_instance_id,
    )
    if revision != response.manifest_revision:
        raise ManifestValidationError("response: manifest revision mismatch")
    return document


def validate_manifest_key(
    provider_instance_id: str,
    manifest_schema_version: int,
    manifest_revision: str,
) -> ManifestRevisionKey:
    """Validate the scalar key used for an accepted manifest cache entry."""
    if not _SCHEMA.is_valid(provider_instance_id, "instanceId"):
        raise ManifestValidationError(
            "response: provider identity must be a canonical UUIDv4"
        )
    _validate_schema_version(manifest_schema_version)
    if not _SCHEMA.is_valid(manifest_revision, "revision"):
        raise ManifestValidationError("response: manifest revision is invalid")
    return ManifestRevisionKey(
        provider_instance_id=UUID(provider_instance_id),
        schema_version=manifest_schema_version,
        revision=manifest_revision,
    )


def _validate_embedded_schemas(
    manifest: dict[str, Any],
    *,
    limits: ManifestValidationLimits,
) -> None:
    """Validate every embedded JSON Schema without retrieving content."""
    configuration = manifest.get("configurationSchema")
    if not isinstance(configuration, dict):
        raise ManifestValidationError(
            "manifest.configurationSchema: must be an object"
        )
    validate_schema(
        configuration,
        "manifest.configurationSchema",
        limits=limits,
    )

    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        raise ManifestValidationError("manifest.operations: must be an object")
    for index, declaration in enumerate(operations.values()):
        if not isinstance(declaration, dict):
            raise ManifestValidationError(
                f"manifest.operations[{index}]: must be an object"
            )
        for field in ("inputSchema", "resultSchema"):
            schema = declaration.get(field)
            if not isinstance(schema, dict):
                raise ManifestValidationError(
                    f"manifest.operations[{index}].{field}: must be an object"
                )
            validate_schema(
                schema,
                f"manifest.operations[{index}].{field}",
                limits=limits,
            )

    triggers = manifest.get("triggers")
    if not isinstance(triggers, dict):
        raise ManifestValidationError("manifest.triggers: must be an object")
    for index, declaration in enumerate(triggers.values()):
        if not isinstance(declaration, dict):
            raise ManifestValidationError(
                f"manifest.triggers[{index}]: must be an object"
            )
        schema = declaration.get("payloadSchema")
        if not isinstance(schema, dict):
            raise ManifestValidationError(
                f"manifest.triggers[{index}].payloadSchema: must be an object"
            )
        validate_schema(
            schema,
            f"manifest.triggers[{index}].payloadSchema",
            limits=limits,
        )


def _validate_schema_version(value: int) -> None:
    """Reject values outside the manifest schema version wire field."""
    _VALIDATION.require_integer_range(
        value,
        minimum=1,
        maximum=contract.MAX_SCHEMA_VERSION,
        message="response: manifest schema version is invalid",
    )
