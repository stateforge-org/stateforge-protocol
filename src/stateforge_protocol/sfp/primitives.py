"""Validate scalar values shared by versioned SFP procedures."""

from __future__ import annotations

from typing import Final, TypeGuard
from uuid import UUID

PROTOBUF_UINT32_MAX: Final = (1 << 32) - 1
CANONICAL_UUID_VERSION: Final = 4


class ProtocolScalarError(ValueError):
    """Report a scalar value outside the shared SFP contract."""


def is_uint32(value: object) -> TypeGuard[int]:
    """Return whether a value is representable by protobuf ``uint32``."""
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= PROTOBUF_UINT32_MAX
    )


def parse_canonical_uuid4(value: object) -> UUID:
    """Parse a canonical lowercase UUIDv4 without echoing rejected data."""
    if not isinstance(value, str):
        raise ProtocolScalarError("value must be a canonical UUIDv4")
    try:
        identifier = UUID(value)
    except ValueError as error:
        raise ProtocolScalarError(
            "value must be a canonical UUIDv4"
        ) from error
    if (
        identifier.version != CANONICAL_UUID_VERSION
        or str(identifier) != value
    ):
        raise ProtocolScalarError("value must be a canonical UUIDv4")
    return identifier


def is_canonical_uuid4(value: object) -> TypeGuard[str]:
    """Return whether a value is a canonical lowercase UUIDv4 string."""
    try:
        parse_canonical_uuid4(value)
    except ProtocolScalarError:
        return False
    return True
