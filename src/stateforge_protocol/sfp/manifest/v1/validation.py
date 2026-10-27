"""Validate the complete Provider Manifest v1 semantic contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import UUID

from stateforge_protocol.sfp import _validation
from stateforge_protocol.sfp.manifest.v1 import (
    _presentation,
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
    "PresentationRevisionKey",
    "PresentationValidationStatus",
    "ValidatedManifestExchange",
    "bounded_json",
    "canonical_bytes",
    "canonical_presentation_bytes",
    "compute_manifest_revision",
    "compute_presentation_revision",
    "contract_validator",
    "validate_manifest_document",
    "validate_manifest_exchange",
    "validate_manifest_key",
    "validate_manifest_response",
    "validate_presentation_document",
    "validate_presentation_key",
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


@dataclass(frozen=True, slots=True)
class PresentationRevisionKey:
    """Identify one valid presentation bound to an operational manifest."""

    provider_instance_id: UUID
    manifest_revision: str
    schema_version: int
    revision: str


class PresentationValidationStatus(StrEnum):
    """Describe how an optional presentation snapshot was handled."""

    ABSENT = "absent"
    ACCEPTED = "accepted"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class ValidatedManifestExchange:
    """Retain independently validated operational and presentation data."""

    manifest_key: ManifestRevisionKey
    manifest_document: bytes
    presentation_status: PresentationValidationStatus
    presentation_key: PresentationRevisionKey | None = None
    presentation_document: bytes | None = None


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


def canonical_presentation_bytes(value: dict[str, Any]) -> bytes:
    """Return bounded RFC 8785 bytes for a presentation document."""
    return _VALIDATION.canonicalize_json(
        value,
        maximum_bytes=contract.MAX_PRESENTATION_REVISION_PREIMAGE_BYTES,
        limit_message="presentation: canonical preimage limit exceeded",
        invalid_message="presentation: non-interoperable JSON value",
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


def compute_presentation_revision(
    presentation: dict[str, Any],
    manifest_revision: str,
    provider_instance_id: str,
) -> str:
    """Return the revision for presentation bound to one manifest."""
    validate_structure(
        provider_instance_id, "instanceId", "providerInstanceId"
    )
    if not _SCHEMA.is_valid(manifest_revision, "revision"):
        raise ManifestValidationError(
            "presentation: manifest revision is invalid"
        )
    preimage = canonical_presentation_bytes(
        {
            "manifestRevision": manifest_revision,
            "presentation": presentation,
            "providerInstanceId": provider_instance_id,
        }
    )
    return "sha256:" + hashlib.sha256(preimage).hexdigest()


def validate_presentation_document(
    presentation: manifest_pb2.ProviderPresentation,
    manifest: dict[str, Any],
    *,
    limits: ManifestValidationLimits = DEFAULT_VALIDATION_LIMITS,
) -> bytes:
    """Validate one complete presentation overlay and its references."""
    presentation = _VALIDATION.require_instance(
        presentation,
        manifest_pb2.ProviderPresentation,
        "presentation: expected ProviderPresentation",
    )
    document = cast(
        dict[str, Any],
        _VALIDATION.project_message(presentation, "presentation"),
    )
    _VALIDATION.require_bounded_json(
        document,
        "presentation",
        maximum_depth=contract.MAX_EMBEDDED_JSON_DEPTH + 4,
        maximum_nodes=limits.max_json_nodes,
        maximum_bytes=contract.MAX_PRESENTATION_REVISION_PREIMAGE_BYTES,
    )
    validate_structure(document, "providerPresentation", "presentation")
    _presentation.validate_presentation_semantics(
        document,
        manifest,
        presentation,
        error_type=ManifestValidationError,
    )
    return canonical_presentation_bytes(document)


def validate_manifest_exchange(
    response: manifest_pb2.GetManifestResponse,
    *,
    limits: ManifestValidationLimits = DEFAULT_VALIDATION_LIMITS,
) -> ValidatedManifestExchange:
    """Validate a manifest and independently accept its presentation."""
    response = _VALIDATION.require_instance(
        response,
        manifest_pb2.GetManifestResponse,
        "response: expected GetManifestResponse",
    )
    _VALIDATION.require_serialized_size(
        response,
        maximum_bytes=contract.MAX_RESPONSE_BYTES,
        path="response",
    )
    projected = _VALIDATION.project_message(response, "response")
    _VALIDATION.require_bounded_json(
        projected,
        "response",
        maximum_depth=contract.MAX_EMBEDDED_JSON_DEPTH + 6,
        maximum_nodes=limits.max_json_nodes,
        maximum_bytes=contract.MAX_RESPONSE_BYTES * 2,
    )
    operational = {
        key: projected[key]
        for key in (
            "providerInstanceId",
            "endpointGeneration",
            "manifestSchemaVersion",
            "manifestRevision",
            "manifest",
            "sessionId",
        )
    }
    validate_structure(operational, "getManifestResponse", "response")
    manifest = cast(dict[str, Any], projected["manifest"])
    manifest_document = validate_manifest_document(manifest, limits=limits)
    revision = compute_manifest_revision(
        manifest,
        response.manifest_schema_version,
        response.provider_instance_id,
    )
    if revision != response.manifest_revision:
        raise ManifestValidationError("response: manifest revision mismatch")
    manifest_key = validate_manifest_key(
        response.provider_instance_id,
        response.manifest_schema_version,
        response.manifest_revision,
    )

    if not response.HasField("presentation"):
        status = (
            PresentationValidationStatus.ABSENT
            if not response.HasField("presentation_revision")
            else PresentationValidationStatus.INVALID
        )
        return ValidatedManifestExchange(
            manifest_key=manifest_key,
            manifest_document=manifest_document,
            presentation_status=status,
        )
    if not _SCHEMA.is_valid(response.presentation_revision, "revision"):
        return ValidatedManifestExchange(
            manifest_key=manifest_key,
            manifest_document=manifest_document,
            presentation_status=PresentationValidationStatus.INVALID,
        )
    presentation_schema_version = (
        response.presentation.presentation_schema_version
    )
    if presentation_schema_version == 0:
        return ValidatedManifestExchange(
            manifest_key=manifest_key,
            manifest_document=manifest_document,
            presentation_status=PresentationValidationStatus.INVALID,
        )
    if presentation_schema_version != contract.PRESENTATION_SCHEMA_VERSION:
        return ValidatedManifestExchange(
            manifest_key=manifest_key,
            manifest_document=manifest_document,
            presentation_status=PresentationValidationStatus.UNSUPPORTED,
        )

    presentation = cast(dict[str, Any], projected["presentation"])
    try:
        presentation_document = validate_presentation_document(
            response.presentation,
            manifest,
            limits=limits,
        )
        expected_revision = compute_presentation_revision(
            presentation,
            response.manifest_revision,
            response.provider_instance_id,
        )
        if expected_revision != response.presentation_revision:
            raise ManifestValidationError("presentation: revision mismatch")
        presentation_key = validate_presentation_key(
            response.provider_instance_id,
            response.manifest_revision,
            presentation_schema_version,
            response.presentation_revision,
        )
    except ManifestValidationError:
        return ValidatedManifestExchange(
            manifest_key=manifest_key,
            manifest_document=manifest_document,
            presentation_status=PresentationValidationStatus.INVALID,
        )
    return ValidatedManifestExchange(
        manifest_key=manifest_key,
        manifest_document=manifest_document,
        presentation_status=PresentationValidationStatus.ACCEPTED,
        presentation_key=presentation_key,
        presentation_document=presentation_document,
    )


def validate_manifest_response(
    response: manifest_pb2.GetManifestResponse,
    *,
    limits: ManifestValidationLimits = DEFAULT_VALIDATION_LIMITS,
) -> bytes:
    """Validate a response and return its canonical operational manifest."""
    return validate_manifest_exchange(
        response, limits=limits
    ).manifest_document


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


def validate_presentation_key(
    provider_instance_id: str,
    manifest_revision: str,
    presentation_schema_version: int,
    presentation_revision: str,
) -> PresentationRevisionKey:
    """Validate the scalar key for an accepted presentation snapshot."""
    if not _SCHEMA.is_valid(provider_instance_id, "instanceId"):
        raise ManifestValidationError(
            "presentation: provider identity must be a canonical UUIDv4"
        )
    if not _SCHEMA.is_valid(manifest_revision, "revision"):
        raise ManifestValidationError(
            "presentation: manifest revision is invalid"
        )
    _VALIDATION.require_equal(
        presentation_schema_version,
        contract.PRESENTATION_SCHEMA_VERSION,
        "presentation: schema version is unsupported",
    )
    if not _SCHEMA.is_valid(presentation_revision, "revision"):
        raise ManifestValidationError("presentation: revision is invalid")
    return PresentationRevisionKey(
        provider_instance_id=UUID(provider_instance_id),
        manifest_revision=manifest_revision,
        schema_version=presentation_schema_version,
        revision=presentation_revision,
    )


def _validate_embedded_schemas(
    manifest: dict[str, Any],
    *,
    limits: ManifestValidationLimits,
) -> None:
    """Validate every embedded JSON Schema without retrieving content."""
    # validate_manifest_document establishes these shapes through the packaged
    # schema before this domain-specific traversal begins.
    configuration = cast(dict[str, Any], manifest["configurationSchema"])
    validate_schema(
        configuration,
        "manifest.configurationSchema",
        limits=limits,
    )

    operations = cast(dict[str, dict[str, Any]], manifest["operations"])
    for index, declaration in enumerate(operations.values()):
        for field in ("inputSchema", "resultSchema"):
            schema = cast(dict[str, Any], declaration[field])
            validate_schema(
                schema,
                f"manifest.operations[{index}].{field}",
                limits=limits,
            )

    triggers = cast(dict[str, dict[str, Any]], manifest["triggers"])
    for index, declaration in enumerate(triggers.values()):
        schema = cast(dict[str, Any], declaration["payloadSchema"])
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
