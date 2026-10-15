"""Validate the complete Provider Manifest v1 semantic contract."""

from __future__ import annotations

import hashlib
import io
import json
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any
from uuid import UUID

import rfc8785
from google.protobuf.json_format import MessageToDict
from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from stateforge_protocol.sfp.manifest.v1 import contract, manifest_pb2

JSON_SCHEMA_DRAFT_2020_12_URI = str(Draft202012Validator.META_SCHEMA["$id"])

_SCHEMA_MAPS = (
    "$defs",
    "definitions",
    "properties",
    "patternProperties",
    "dependentSchemas",
)
_SCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
_SCHEMA_SINGLE = (
    "additionalProperties",
    "unevaluatedProperties",
    "propertyNames",
    "items",
    "unevaluatedItems",
    "contains",
    "not",
    "if",
    "then",
    "else",
    "contentSchema",
)
_SAME_INSTANCE = {
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "dependentSchemas",
}
_VALUES = {"default", "examples", "const", "enum"}
_MAX_UINT32 = (1 << 32) - 1


class ManifestValidationError(ValueError):
    """Report invalid Manifest data without exposing rejected values."""


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


def bounded_json(  # noqa: PLR0912
    value: object,
    path: str,
    *,
    depth_limit: int = contract.MAX_EMBEDDED_JSON_DEPTH,
    limits: ManifestValidationLimits = DEFAULT_VALIDATION_LIMITS,
) -> None:
    """Reject excessive or non-JSON content before schema processing."""
    pending = [(value, 0)]
    nodes = 0
    size = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > limits.max_json_nodes:
            raise ManifestValidationError(
                f"{path}: JSON resource limit exceeded"
            )
        if isinstance(item, (dict, list)):
            depth += 1
            if depth > depth_limit:
                raise ManifestValidationError(
                    f"{path}: JSON nesting limit exceeded"
                )
            if len(item) > limits.max_json_nodes:
                raise ManifestValidationError(
                    f"{path}: JSON resource limit exceeded"
                )
            size += len(item) + 2
            if isinstance(item, dict):
                for key, child in item.items():
                    if not isinstance(key, str):
                        raise ManifestValidationError(
                            f"{path}: JSON keys must be strings"
                        )
                    pending.append((key, depth))
                    pending.append((child, depth))
            else:
                pending.extend((child, depth) for child in item)
        elif isinstance(item, str):
            if len(item) > contract.MAX_CANONICAL_REVISION_PREIMAGE_BYTES:
                raise ManifestValidationError(
                    f"{path}: JSON resource limit exceeded"
                )
            try:
                size += len(item.encode("utf-8")) + 2
            except UnicodeError:
                raise ManifestValidationError(
                    f"{path}: invalid Unicode"
                ) from None
        elif item is None or isinstance(item, (bool, int, float)):
            size += 1
        else:
            raise ManifestValidationError(f"{path}: non-JSON value")
        if size > contract.MAX_CANONICAL_REVISION_PREIMAGE_BYTES:
            raise ManifestValidationError(
                f"{path}: JSON resource limit exceeded"
            )


class _BoundedBuffer(io.BytesIO):
    """Stop canonical output before it exceeds the v1 contract."""

    def write(self, data: bytes, /) -> int:  # type: ignore[override]
        if (
            self.tell() + len(data)
            > contract.MAX_CANONICAL_REVISION_PREIMAGE_BYTES
        ):
            raise ManifestValidationError(
                "manifest: canonical preimage limit exceeded"
            )
        return super().write(data)


def canonical_bytes(value: dict[str, Any]) -> bytes:
    """Return bounded RFC 8785 bytes for a JSON-compatible object."""
    stream = _BoundedBuffer()
    try:
        rfc8785.dump(value, stream)
    except rfc8785.CanonicalizationError:
        raise ManifestValidationError(
            "manifest: non-interoperable JSON value"
        ) from None
    return stream.getvalue()


@lru_cache(maxsize=16)
def contract_validator(definition: str) -> Draft202012Validator:
    """Load a validation projection from the installed Protocol package."""
    document = json.loads(
        files("stateforge_protocol.sfp.manifest.v1")
        .joinpath("manifest.schema.json")
        .read_text(encoding="utf-8")
    )
    return Draft202012Validator(
        {"$ref": f"#/$defs/{definition}", "$defs": document["$defs"]}
    )


def validate_structure(value: object, definition: str, path: str) -> None:
    """Validate one packaged ProtoJSON projection without leaking values."""
    error = next(contract_validator(definition).iter_errors(value), None)
    if error is not None:
        raise ManifestValidationError(
            f"{path}: violates P1 {error.validator} constraint"
        )


def validate_schema(  # noqa: PLR0912, PLR0915
    document: dict[str, Any],
    path: str,
    *,
    limits: ManifestValidationLimits = DEFAULT_VALIDATION_LIMITS,
) -> None:
    """Resolve local schema references and reject indirect secret values."""
    bounded_json(document, path, limits=limits)
    canonical_bytes(document)
    validate_structure(document, "schemaDocument", path)
    nodes: dict[int, dict[str, Any]] = {}
    children: dict[int, set[int]] = {}
    same: dict[int, set[int]] = {}
    pending = [document]
    while pending:
        node = pending.pop()
        key = id(node)
        if key in nodes:
            continue
        if (
            node.get("$schema", JSON_SCHEMA_DRAFT_2020_12_URI)
            != JSON_SCHEMA_DRAFT_2020_12_URI
        ):
            raise ManifestValidationError(
                f"{path}: unsupported nested schema dialect"
            )
        nodes[key] = node
        if len(nodes) > limits.max_schema_nodes:
            raise ManifestValidationError(
                f"{path}: schema node limit exceeded"
            )
        children.setdefault(key, set())
        same.setdefault(key, set())
        for keyword, value in node.items():
            candidates: list[object] = []
            if keyword in _SCHEMA_MAPS and isinstance(value, dict):
                candidates = list(value.values())
            elif keyword in _SCHEMA_LISTS and isinstance(value, list):
                candidates = value
            elif keyword in _SCHEMA_SINGLE:
                candidates = [value]
            for child in candidates:
                if isinstance(child, dict):
                    pending.append(child)
                    if keyword not in {"$defs", "definitions"}:
                        children[key].add(id(child))
                    if keyword in _SAME_INSTANCE:
                        same[key].add(id(child))
                        same.setdefault(id(child), set()).add(key)

    resource = DRAFT202012.create_resource(document)
    registry: Registry[Any] = Registry().with_resource("", resource)
    resolver = registry.resolver("")
    for key, node in nodes.items():
        for keyword in ("$ref", "$dynamicRef"):
            if keyword not in node:
                continue
            try:
                target = resolver.lookup(node[keyword]).contents
            except Unresolvable:
                raise ManifestValidationError(
                    f"{path}: unresolved local reference"
                ) from None
            if isinstance(target, bool):
                continue
            if not isinstance(target, dict) or id(target) not in nodes:
                raise ManifestValidationError(
                    f"{path}: reference does not name a schema"
                )
            children[key].add(id(target))
            same[key].add(id(target))
            same[id(target)].add(key)

    secrets = {
        key for key, node in nodes.items() if node.get("writeOnly") is True
    }
    effective = _reachable(secrets, same)
    below = _reachable(effective, children)
    parents: dict[int, set[int]] = {key: set() for key in nodes}
    for key, links in children.items():
        for child in links:
            parents[child].add(key)
    protected = below | _reachable(effective, parents)
    for key in protected:
        if _VALUES.intersection(nodes[key]):
            raise ManifestValidationError(
                f"{path}: secret schema contains value annotations"
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
    projected = MessageToDict(
        response,
        always_print_fields_with_no_presence=True,
    )
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
    if not contract_validator("instanceId").is_valid(provider_instance_id):
        raise ManifestValidationError(
            "response: provider identity must be a canonical UUIDv4"
        )
    _validate_schema_version(manifest_schema_version)
    if not contract_validator("revision").is_valid(manifest_revision):
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
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= _MAX_UINT32
    ):
        raise ManifestValidationError(
            "response: manifest schema version is invalid"
        )


def _reachable(roots: set[int], edges: dict[int, set[int]]) -> set[int]:
    """Return every schema node reachable from the supplied roots."""
    visited = set(roots)
    pending = deque(roots)
    while pending:
        for child in edges[pending.popleft()]:
            if child not in visited:
                visited.add(child)
                pending.append(child)
    return visited
