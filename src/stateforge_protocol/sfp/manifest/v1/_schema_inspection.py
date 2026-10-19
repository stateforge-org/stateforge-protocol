"""Inspect embedded Manifest JSON Schemas without external retrieval."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, TypeVar

from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

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
_ValidationError = TypeVar("_ValidationError", bound=ValueError)


@dataclass(frozen=True, slots=True)
class _SchemaGraph:
    """Retain relationships needed for Manifest secret-safety checks."""

    nodes: dict[int, dict[str, Any]]
    children: dict[int, set[int]]
    same_instance: dict[int, set[int]]


def inspect_schema(
    document: dict[str, Any],
    path: str,
    *,
    maximum_nodes: int,
    error_type: type[_ValidationError],
) -> None:
    """Resolve local references and reject indirect secret values."""
    graph = _collect_schema_graph(
        document,
        path,
        maximum_nodes=maximum_nodes,
        error_type=error_type,
    )
    _resolve_local_references(
        document,
        graph,
        path,
        error_type=error_type,
    )
    _reject_secret_value_annotations(graph, path, error_type=error_type)


def _collect_schema_graph(
    document: dict[str, Any],
    path: str,
    *,
    maximum_nodes: int,
    error_type: type[_ValidationError],
) -> _SchemaGraph:
    """Collect nested schema relationships without following references."""
    nodes: dict[int, dict[str, Any]] = {}
    children: dict[int, set[int]] = {}
    same_instance: dict[int, set[int]] = {}
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
            raise error_type(f"{path}: unsupported nested schema dialect")
        nodes[key] = node
        if len(nodes) > maximum_nodes:
            raise error_type(f"{path}: schema node limit exceeded")
        children.setdefault(key, set())
        same_instance.setdefault(key, set())
        for keyword, value in node.items():
            for child in _schema_candidates(keyword, value):
                if isinstance(child, dict):
                    pending.append(child)
                    if keyword not in {"$defs", "definitions"}:
                        children[key].add(id(child))
                    if keyword in _SAME_INSTANCE:
                        same_instance[key].add(id(child))
                        same_instance.setdefault(id(child), set()).add(key)
    return _SchemaGraph(
        nodes=nodes,
        children=children,
        same_instance=same_instance,
    )


def _schema_candidates(keyword: str, value: object) -> list[object]:
    """Return nested schemas selected by one JSON Schema keyword."""
    if keyword in _SCHEMA_MAPS and isinstance(value, dict):
        return list(value.values())
    if keyword in _SCHEMA_LISTS and isinstance(value, list):
        return value
    if keyword in _SCHEMA_SINGLE:
        return [value]
    return []


def _resolve_local_references(
    document: dict[str, Any],
    graph: _SchemaGraph,
    path: str,
    *,
    error_type: type[_ValidationError],
) -> None:
    """Attach local reference edges and reject external retrieval."""
    nodes = graph.nodes
    children = graph.children
    same_instance = graph.same_instance

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
                raise error_type(
                    f"{path}: unresolved local reference"
                ) from None
            if isinstance(target, bool):
                continue
            if not isinstance(target, dict) or id(target) not in nodes:
                raise error_type(f"{path}: reference does not name a schema")
            children[key].add(id(target))
            same_instance[key].add(id(target))
            same_instance[id(target)].add(key)


def _reject_secret_value_annotations(
    graph: _SchemaGraph,
    path: str,
    *,
    error_type: type[_ValidationError],
) -> None:
    """Reject values that could disclose a write-only schema instance."""
    nodes = graph.nodes
    secrets = {
        key for key, node in nodes.items() if node.get("writeOnly") is True
    }
    effective_secrets = _reachable(secrets, graph.same_instance)
    descendants = _reachable(effective_secrets, graph.children)
    parents: dict[int, set[int]] = {key: set() for key in nodes}
    for key, links in graph.children.items():
        for child in links:
            parents[child].add(key)
    protected = descendants | _reachable(effective_secrets, parents)
    for key in protected:
        if _VALUES.intersection(nodes[key]):
            raise error_type(
                f"{path}: secret schema contains value annotations"
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
