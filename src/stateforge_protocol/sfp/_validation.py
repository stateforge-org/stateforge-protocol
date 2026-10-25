"""Shared mechanics for versioned SFP semantic validators.

Procedure modules own their public validation APIs, error types, and domain
rules. This private module only centralizes context-independent mechanics that
would otherwise be repeated across those procedure validators.
"""

from __future__ import annotations

import io
import json
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any, Generic, TypeVar, cast
from uuid import UUID

import rfc8785
from google.protobuf.json_format import Error as ProtoJsonError
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from google.protobuf.struct_pb2 import ListValue, Struct, Value
from jsonschema import Draft202012Validator

from stateforge_protocol.sfp import primitives

__all__ = ["PackagedSchema", "ValidationContext"]

_ValidationError = TypeVar("_ValidationError", bound=ValueError)
_Value = TypeVar("_Value")


@dataclass(frozen=True, slots=True)
class PackagedSchema:
    """Address reusable definitions in one packaged JSON Schema resource."""

    package: str
    resource: str
    contract_name: str

    def validator(self, definition: str) -> Draft202012Validator:
        """Return the cached validator for one schema definition."""
        return _definition_validator(self.package, self.resource, definition)

    def is_valid(self, value: object, definition: str) -> bool:
        """Return whether one value satisfies a packaged definition."""
        return self.validator(definition).is_valid(value)


@dataclass(frozen=True, slots=True)
class ValidationContext(Generic[_ValidationError]):
    """Apply shared mechanics through one procedure-specific error surface."""

    error_type: type[_ValidationError]

    def require(self, condition: bool, message: str) -> None:
        """Require one predicate without exposing rejected protocol data."""
        if not condition:
            raise self.error_type(message)

    def require_instance(
        self,
        value: object,
        expected_type: type[_Value],
        message: str,
    ) -> _Value:
        """Return a value only when it has the required runtime type."""
        if not isinstance(value, expected_type):
            raise self.error_type(message)
        return value

    def require_equal(
        self,
        actual: object,
        expected: object,
        message: str,
    ) -> None:
        """Require semantic equality without echoing either value."""
        self.require(actual == expected, message)

    def require_canonical_uuid4(
        self,
        value: object,
        message: str,
    ) -> UUID:
        """Parse a canonical UUIDv4 and translate the shared scalar error."""
        try:
            return primitives.parse_canonical_uuid4(value)
        except primitives.ProtocolScalarError as error:
            raise self.error_type(message) from error

    def require_integer_range(
        self,
        value: object,
        *,
        minimum: int,
        maximum: int,
        message: str,
    ) -> int:
        """Return a non-boolean integer within an inclusive range."""
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not minimum <= value <= maximum
        ):
            raise self.error_type(message)
        return value

    def require_code_point_length(
        self,
        value: object,
        *,
        minimum: int,
        maximum: int,
        message: str,
    ) -> str:
        """Return a string whose code-point length is within bounds."""
        if not isinstance(value, str) or not minimum <= len(value) <= maximum:
            raise self.error_type(message)
        return value

    def require_unique(
        self,
        values: Sequence[Hashable],
        message: str,
    ) -> None:
        """Reject duplicate normalized values without echoing them."""
        self.require(len(values) == len(set(values)), message)

    def project_message(
        self,
        message: Message,
        path: str,
    ) -> dict[str, object]:
        """Return a complete ProtoJSON object through the bound error type."""
        try:
            projected = MessageToDict(
                message,
                always_print_fields_with_no_presence=True,
            )
        except (OverflowError, ProtoJsonError, TypeError, ValueError) as error:
            raise self.error_type(
                f"{path}: cannot produce a valid ProtoJSON projection"
            ) from error
        if not isinstance(projected, dict):
            raise self.error_type(
                f"{path}: ProtoJSON projection must be an object"
            )
        return projected

    def require_serialized_size(
        self,
        message: Message,
        *,
        maximum_bytes: int,
        path: str,
    ) -> None:
        """Require one protobuf message to fit its RPC boundary."""
        self.require(
            message.ByteSize() <= maximum_bytes,
            f"{path}: serialized message exceeds the protocol limit",
        )

    def validate_schema_definition(
        self,
        schema: PackagedSchema,
        value: object,
        definition: str,
        path: str,
    ) -> None:
        """Validate one value without echoing rejected protocol data."""
        error = next(schema.validator(definition).iter_errors(value), None)
        if error is not None:
            raise self.error_type(
                f"{path}: violates {schema.contract_name} "
                f"{error.validator} constraint"
            )

    def validate_message_schema(
        self,
        schema: PackagedSchema,
        message: Message,
        definition: str,
        path: str,
    ) -> dict[str, object]:
        """Project and validate one protobuf message against a definition."""
        projected = self.project_message(message, path)
        self.validate_schema_definition(schema, projected, definition, path)
        return projected

    def require_bounded_json(
        self,
        value: object,
        path: str,
        *,
        maximum_depth: int,
        maximum_nodes: int,
        maximum_bytes: int,
    ) -> None:
        """Reject excessive or non-JSON content before schema processing."""
        pending = [(value, 0)]
        nodes = 0
        size = 0
        while pending:
            item, depth = pending.pop()
            nodes += 1
            self.require(
                nodes <= maximum_nodes,
                f"{path}: JSON resource limit exceeded",
            )
            if isinstance(item, (dict, list)):
                depth += 1
                self.require(
                    depth <= maximum_depth,
                    f"{path}: JSON nesting limit exceeded",
                )
                self.require(
                    len(item) <= maximum_nodes,
                    f"{path}: JSON resource limit exceeded",
                )
                size += len(item) + 2
                if isinstance(item, dict):
                    for key, child in item.items():
                        self.require(
                            isinstance(key, str),
                            f"{path}: JSON keys must be strings",
                        )
                        pending.append((key, depth))
                        pending.append((child, depth))
                else:
                    pending.extend((child, depth) for child in item)
            elif isinstance(item, str):
                self.require(
                    len(item) <= maximum_bytes,
                    f"{path}: JSON resource limit exceeded",
                )
                try:
                    size += len(item.encode("utf-8")) + 2
                except UnicodeError:
                    raise self.error_type(f"{path}: invalid Unicode") from None
            elif item is None or isinstance(item, (bool, int, float)):
                size += 1
            else:
                raise self.error_type(f"{path}: non-JSON value")
            self.require(
                size <= maximum_bytes,
                f"{path}: JSON resource limit exceeded",
            )

    def require_bounded_protojson_container(
        self,
        value: Struct | ListValue,
        *,
        maximum_depth: int,
        maximum_entries: int,
        nesting_message: str,
        container_message: str,
    ) -> None:
        """Bound breadth and depth in a protobuf JSON container."""
        pending: list[tuple[Struct | ListValue, int]] = [(value, 1)]
        while pending:
            container, depth = pending.pop()
            self.require(depth <= maximum_depth, nesting_message)
            values = (
                tuple(container.fields.values())
                if isinstance(container, Struct)
                else tuple(container.values)
            )
            self.require(len(values) <= maximum_entries, container_message)
            for child_value in values:
                child = _selected_value_container(child_value)
                if child is not None:
                    pending.append((child, depth + 1))

    def canonicalize_json(
        self,
        value: object,
        *,
        maximum_bytes: int,
        limit_message: str,
        invalid_message: str,
    ) -> bytes:
        """Return bounded RFC 8785 bytes for a JSON-compatible value."""
        stream = _BoundedBuffer(
            maximum_bytes=maximum_bytes,
            error_type=self.error_type,
            message=limit_message,
        )
        try:
            rfc8785.dump(cast(Any, value), stream)
        except rfc8785.CanonicalizationError:
            raise self.error_type(invalid_message) from None
        return stream.getvalue()


class _BoundedBuffer(io.BytesIO, Generic[_ValidationError]):
    """Stop canonical output before it exceeds a caller-owned bound."""

    def __init__(
        self,
        *,
        maximum_bytes: int,
        error_type: type[_ValidationError],
        message: str,
    ) -> None:
        super().__init__()
        self._maximum_bytes = maximum_bytes
        self._error_type = error_type
        self._message = message

    def write(self, data: bytes, /) -> int:  # type: ignore[override]
        if self.tell() + len(data) > self._maximum_bytes:
            raise self._error_type(self._message)
        return super().write(data)


def _selected_value_container(value: Value) -> Struct | ListValue | None:
    """Return the container selected by one protobuf JSON value."""
    kind = value.WhichOneof("kind")
    if kind == "struct_value":
        return value.struct_value
    if kind == "list_value":
        return value.list_value
    return None


@lru_cache(maxsize=64)
def _definition_validator(
    package: str,
    resource: str,
    definition: str,
) -> Draft202012Validator:
    """Load one JSON Schema definition from the installed package."""
    document = json.loads(
        files(package).joinpath(resource).read_text(encoding="utf-8")
    )
    return Draft202012Validator(
        {"$ref": f"#/$defs/{definition}", "$defs": document["$defs"]}
    )
