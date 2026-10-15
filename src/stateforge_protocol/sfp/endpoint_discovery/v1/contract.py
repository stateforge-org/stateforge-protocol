"""Expose the normative SFP endpoint-discovery v1 contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final, TypeGuard
from uuid import UUID

from stateforge_protocol.sfp import primitives

SCHEMA_VERSION: Final = "1"
DESCRIPTOR_SUFFIX: Final = ".sfp.json"
TRANSPORT_TYPE: Final = "unix"

# Shared filesystem permissions enforced by the publishing and consuming
# runtimes. Directory ownership and trust validation remain runtime concerns.
DESCRIPTOR_MODE: Final = 0o640
SOCKET_MODE: Final = 0o660

# The descriptor is a small discovery record, not an extensible payload.
MAX_DESCRIPTOR_BYTES: Final = 4 * 1024
MIN_ENDPOINT_GENERATION: Final = 1
MAX_ENDPOINT_GENERATION: Final = (2**63) - 1
PROVIDER_INSTANCE_UUID_VERSION: Final = primitives.CANONICAL_UUID_VERSION

_ROOT_FIELDS: Final = frozenset(
    {
        "schema_version",
        "provider_instance_id",
        "endpoint_generation",
        "transport",
    }
)
_TRANSPORT_FIELDS: Final = frozenset({"type", "socket_path"})


class EndpointDescriptorContractError(ValueError):
    """Report endpoint descriptor data outside the versioned contract."""


@dataclass(frozen=True, slots=True)
class EndpointDescriptor:
    """Validated data published for one Provider endpoint generation."""

    provider_instance_id: UUID
    endpoint_generation: int
    socket_path: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Reject values that cannot be represented by descriptor v1."""
        if (
            not isinstance(self.schema_version, str)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise EndpointDescriptorContractError(
                "Unsupported Provider descriptor schema_version: "
                f"{self.schema_version}"
            )
        if (
            not isinstance(self.provider_instance_id, UUID)
            or self.provider_instance_id.version
            != PROVIDER_INSTANCE_UUID_VERSION
        ):
            raise EndpointDescriptorContractError(
                "provider_instance_id must be a canonical UUIDv4"
            )
        if not is_allocated_endpoint_generation(self.endpoint_generation):
            raise EndpointDescriptorContractError(
                "endpoint_generation must be an integer from "
                f"{MIN_ENDPOINT_GENERATION} through {MAX_ENDPOINT_GENERATION}"
            )
        if (
            not isinstance(self.socket_path, str)
            or not self.socket_path
            or "\x00" in self.socket_path
            or not PurePosixPath(self.socket_path).is_absolute()
        ):
            raise EndpointDescriptorContractError(
                "Provider descriptor field socket_path must be a non-empty "
                "absolute Unix path"
            )

    def as_document(self) -> dict[str, object]:
        """Return the exact JSON object defined by descriptor v1."""
        return {
            "schema_version": self.schema_version,
            "provider_instance_id": str(self.provider_instance_id),
            "endpoint_generation": self.endpoint_generation,
            "transport": {
                "type": TRANSPORT_TYPE,
                "socket_path": self.socket_path,
            },
        }

    def to_json_bytes(self) -> bytes:
        """Serialize one bounded, deterministic descriptor document."""
        content = (
            json.dumps(self.as_document(), indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        if len(content) > MAX_DESCRIPTOR_BYTES:
            raise EndpointDescriptorContractError(
                f"Provider descriptor exceeds {MAX_DESCRIPTOR_BYTES} bytes"
            )
        return content


def is_allocated_endpoint_generation(value: object) -> TypeGuard[int]:
    """Return whether a value is a descriptor v1 endpoint generation."""
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and MIN_ENDPOINT_GENERATION <= value <= MAX_ENDPOINT_GENERATION
    )


def descriptor_filename(provider_instance_id: UUID) -> str:
    """Return the stable descriptor name for one Provider installation."""
    _validate_provider_instance_id(provider_instance_id)
    return f"{provider_instance_id}{DESCRIPTOR_SUFFIX}"


def socket_filename(
    provider_instance_id: UUID,
    endpoint_generation: int,
) -> str:
    """Return the Unix-socket name for one Provider endpoint generation."""
    _validate_provider_instance_id(provider_instance_id)
    if not is_allocated_endpoint_generation(endpoint_generation):
        raise EndpointDescriptorContractError(
            "endpoint_generation must be an integer from "
            f"{MIN_ENDPOINT_GENERATION} through {MAX_ENDPOINT_GENERATION}"
        )
    return f"{provider_instance_id}.{endpoint_generation}.sock"


def provider_instance_id_from_descriptor_filename(filename: str) -> UUID:
    """Parse the Provider identity from a canonical descriptor name."""
    if not filename.endswith(DESCRIPTOR_SUFFIX):
        raise EndpointDescriptorContractError(
            "Provider descriptor filename has the wrong suffix"
        )
    value = filename.removesuffix(DESCRIPTOR_SUFFIX)
    return _parse_provider_instance_id(value)


def parse_descriptor(content: bytes) -> EndpointDescriptor:
    """Parse and validate one complete descriptor v1 JSON document."""
    if not content:
        raise EndpointDescriptorContractError("Provider descriptor is empty")
    if len(content) > MAX_DESCRIPTOR_BYTES:
        raise EndpointDescriptorContractError(
            f"Provider descriptor exceeds {MAX_DESCRIPTOR_BYTES} bytes"
        )
    try:
        document = json.loads(
            content,
            object_pairs_hook=_reject_duplicate_fields,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EndpointDescriptorContractError(
            f"Cannot parse Provider descriptor: {error}"
        ) from error
    if not isinstance(document, dict):
        raise EndpointDescriptorContractError(
            "Provider descriptor root must be a JSON object"
        )

    _require_exact_fields(document, _ROOT_FIELDS, "Provider descriptor")
    schema_version = document["schema_version"]
    if not isinstance(schema_version, str) or not schema_version:
        raise EndpointDescriptorContractError(
            "Provider descriptor field schema_version must be a non-empty "
            "string"
        )
    if schema_version != SCHEMA_VERSION:
        raise EndpointDescriptorContractError(
            f"Unsupported Provider descriptor schema_version: {schema_version}"
        )

    provider_instance_value = document["provider_instance_id"]
    if not isinstance(provider_instance_value, str):
        raise EndpointDescriptorContractError(
            "provider_instance_id must be a canonical UUIDv4"
        )
    provider_instance_id = _parse_provider_instance_id(provider_instance_value)

    endpoint_generation = document["endpoint_generation"]
    if not is_allocated_endpoint_generation(endpoint_generation):
        raise EndpointDescriptorContractError(
            "endpoint_generation must be an integer from "
            f"{MIN_ENDPOINT_GENERATION} through {MAX_ENDPOINT_GENERATION}"
        )

    transport = document["transport"]
    if not isinstance(transport, dict):
        raise EndpointDescriptorContractError(
            "Provider descriptor field transport must be an object"
        )
    _require_exact_fields(transport, _TRANSPORT_FIELDS, "Provider transport")
    transport_type = transport["type"]
    if transport_type != TRANSPORT_TYPE:
        raise EndpointDescriptorContractError(
            f"Unsupported Provider endpoint transport: {transport_type}"
        )
    socket_path = transport["socket_path"]
    if not isinstance(socket_path, str):
        raise EndpointDescriptorContractError(
            "Provider descriptor field socket_path must be a non-empty "
            "absolute Unix path"
        )

    return EndpointDescriptor(
        schema_version=schema_version,
        provider_instance_id=provider_instance_id,
        endpoint_generation=endpoint_generation,
        socket_path=socket_path,
    )


def _validate_provider_instance_id(provider_instance_id: UUID) -> None:
    """Reject Provider identities outside descriptor v1."""
    if (
        not isinstance(provider_instance_id, UUID)
        or provider_instance_id.version != PROVIDER_INSTANCE_UUID_VERSION
    ):
        raise EndpointDescriptorContractError(
            "provider_instance_id must be a canonical UUIDv4"
        )


def _parse_provider_instance_id(value: str) -> UUID:
    """Parse one canonical lowercase Provider UUIDv4."""
    try:
        return primitives.parse_canonical_uuid4(value)
    except primitives.ProtocolScalarError as error:
        raise EndpointDescriptorContractError(
            "provider_instance_id must be a canonical UUIDv4"
        ) from error


def _require_exact_fields(
    document: dict[str, object],
    expected: frozenset[str],
    resource: str,
) -> None:
    """Reject missing and unknown JSON object fields."""
    fields = set(document)
    missing = sorted(expected - fields)
    unknown = sorted(fields - expected)
    if missing:
        raise EndpointDescriptorContractError(
            f"{resource} is missing fields: {', '.join(missing)}"
        )
    if unknown:
        raise EndpointDescriptorContractError(
            f"{resource} contains unknown fields: {', '.join(unknown)}"
        )


def _reject_duplicate_fields(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """Build a JSON object while rejecting duplicate field names."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EndpointDescriptorContractError(
                f"Provider descriptor contains duplicate field: {key}"
            )
        result[key] = value
    return result
