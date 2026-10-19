"""Tests for private mechanics shared by procedure-owned validators."""

import ast
from pathlib import Path

import pytest
from google.protobuf.struct_pb2 import Struct

from stateforge_protocol.sfp import _validation
from stateforge_protocol.sfp.bootstrap.v1 import validation as bootstrap
from stateforge_protocol.sfp.capability_assessment.v1 import (
    validation as capability_assessment,
)
from stateforge_protocol.sfp.manifest.v1 import validation as manifest

_SOURCE_ROOT = (
    Path(__file__).parents[1] / "src" / "stateforge_protocol" / "sfp"
)
_GENERIC_HELPER_NAMES = {
    "_BoundedBuffer",
    "_bounded_json",
    "_definition_validator",
    "_project_message",
    "_validate_generation",
    "_validate_structure",
    "_validate_uuid",
    "_value_container",
}
_PLUMBING_IMPORTS = {
    "google.protobuf.json_format",
    "google.protobuf.struct_pb2",
    "importlib.resources",
    "jsonschema",
    "referencing",
    "rfc8785",
}


class ExampleValidationError(ValueError):
    """Identify failures translated through the shared context."""


class _RuntimeImportVisitor(ast.NodeVisitor):
    """Collect imports while ignoring static type-checking blocks."""

    def __init__(self) -> None:
        self.imports: set[str] = set()

    def visit_If(self, node: ast.If) -> None:
        """Skip imports guarded by ``TYPE_CHECKING``."""
        if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Record direct runtime imports."""
        self.imports.update(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record from-import modules used at runtime."""
        if node.module is not None:
            self.imports.add(node.module)


def test_shared_context_preserves_the_procedure_error_surface() -> None:
    context = _validation.ValidationContext(ExampleValidationError)
    valid_integer = 2

    assert context.require_instance("value", str, "wrong type") == "value"
    assert (
        context.require_integer_range(
            valid_integer,
            minimum=1,
            maximum=3,
            message="outside range",
        )
        == valid_integer
    )

    with pytest.raises(ExampleValidationError, match="required condition"):
        context.require(False, "required condition")
    with pytest.raises(ExampleValidationError, match="wrong type"):
        context.require_instance(object(), str, "wrong type")
    with pytest.raises(ExampleValidationError, match="outside range"):
        context.require_integer_range(
            True,
            minimum=0,
            maximum=1,
            message="outside range",
        )


def test_shared_context_bounds_json_and_protojson_containers() -> None:
    context = _validation.ValidationContext(ExampleValidationError)
    context.require_bounded_json(
        {"value": [1]},
        "document",
        maximum_depth=2,
        maximum_nodes=4,
        maximum_bytes=64,
    )
    with pytest.raises(ExampleValidationError, match="nesting limit"):
        context.require_bounded_json(
            {"value": [[1]]},
            "document",
            maximum_depth=2,
            maximum_nodes=10,
            maximum_bytes=64,
        )

    protojson = Struct()
    protojson.fields["nested"].struct_value.fields[
        "leaf"
    ].string_value = "value"
    with pytest.raises(ExampleValidationError, match="proto nesting"):
        context.require_bounded_protojson_container(
            protojson,
            maximum_depth=1,
            maximum_entries=2,
            nesting_message="proto nesting",
            container_message="proto breadth",
        )


def test_shared_context_bounds_canonical_json() -> None:
    context = _validation.ValidationContext(ExampleValidationError)

    assert (
        context.canonicalize_json(
            {"value": 1},
            maximum_bytes=32,
            limit_message="canonical limit",
            invalid_message="invalid canonical value",
        )
        == b'{"value":1}'
    )
    with pytest.raises(ExampleValidationError, match="canonical limit"):
        context.canonicalize_json(
            {"value": "too large"},
            maximum_bytes=4,
            limit_message="canonical limit",
            invalid_message="invalid canonical value",
        )


def test_procedure_validators_do_not_reimplement_shared_mechanics() -> None:
    validators = sorted(_SOURCE_ROOT.glob("*/v*/validation.py"))
    assert validators

    for path in validators:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        definitions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef))
        }
        assert not definitions.intersection(_GENERIC_HELPER_NAMES), path

        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        assert not {
            imported
            for imported in visitor.imports
            if any(
                imported == plumbing or imported.startswith(f"{plumbing}.")
                for plumbing in _PLUMBING_IMPORTS
            )
        }, path


def test_procedure_validator_public_surfaces_are_explicit() -> None:
    assert bootstrap.__all__
    assert capability_assessment.__all__
    assert manifest.__all__
