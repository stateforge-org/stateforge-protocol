"""Validate Provider presentation overlays and embedded visual assets."""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from typing import Any, Final, Never, cast
from xml.etree import ElementTree

import rfc8785

from stateforge_protocol.sfp.manifest.v1 import contract, manifest_pb2

_LOCAL_ASSET_REFERENCE: Final = re.compile(
    r"url\(#[A-Za-z_][A-Za-z0-9_.:-]*\)"
)
_SVG_NAMESPACE: Final = "http://www.w3.org/2000/svg"
_SAFE_SVG_TAGS: Final = frozenset(
    {
        "circle",
        "clipPath",
        "defs",
        "desc",
        "ellipse",
        "g",
        "line",
        "linearGradient",
        "mask",
        "path",
        "polygon",
        "polyline",
        "radialGradient",
        "rect",
        "stop",
        "svg",
        "symbol",
        "title",
    }
)
_SAFE_SVG_ATTRIBUTES: Final = frozenset(
    {
        "aria-hidden",
        "aria-label",
        "clip-path",
        "cx",
        "cy",
        "d",
        "fill",
        "fill-opacity",
        "gradientTransform",
        "gradientUnits",
        "height",
        "id",
        "mask",
        "offset",
        "opacity",
        "points",
        "preserveAspectRatio",
        "r",
        "role",
        "rx",
        "ry",
        "stop-color",
        "stop-opacity",
        "stroke",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-opacity",
        "stroke-width",
        "transform",
        "viewBox",
        "width",
        "x",
        "x1",
        "x2",
        "y",
        "y1",
        "y2",
    }
)
_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_PNG_CHUNK_OVERHEAD: Final = 12
_PNG_IHDR_BYTES: Final = 13
_SAFE_PNG_CHUNKS: Final = frozenset(
    {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}
)


def validate_presentation_semantics(
    presentation: dict[str, Any],
    manifest: dict[str, Any],
    message: manifest_pb2.ProviderPresentation,
    *,
    error_type: type[ValueError],
) -> None:
    """Validate a bounded component tree and all of its references."""
    operations = cast(dict[str, dict[str, Any]], manifest["operations"])
    triggers = cast(dict[str, dict[str, Any]], manifest["triggers"])
    operation_targets = cast(
        dict[str, dict[str, Any]], presentation["operations"]
    )
    trigger_targets = cast(dict[str, dict[str, Any]], presentation["triggers"])
    requirements = cast(
        dict[str, dict[str, Any]], presentation["rendererRequirements"]
    )

    if not operation_targets.keys() <= operations.keys():
        raise error_type(
            "presentation: operation target does not name a declared operation"
        )
    if not trigger_targets.keys() <= triggers.keys():
        raise error_type(
            "presentation: trigger target does not name a declared trigger"
        )
    if contract.CORE_COMPONENT_NAMESPACE in requirements:
        raise error_type(
            "presentation: core components cannot require an extension"
        )

    state = _PresentationState()
    provider = presentation.get("provider")
    if isinstance(provider, dict):
        _validate_target(
            provider,
            target_kind="provider",
            permitted_surfaces=contract.PROVIDER_SURFACES,
            state=state,
            requirements=requirements,
            error_type=error_type,
        )
    for target in operation_targets.values():
        _validate_target(
            target,
            target_kind="operation",
            permitted_surfaces=contract.OPERATION_SURFACES,
            state=state,
            requirements=requirements,
            error_type=error_type,
        )
    for target in trigger_targets.values():
        _validate_target(
            target,
            target_kind="trigger",
            permitted_surfaces=contract.TRIGGER_SURFACES,
            state=state,
            requirements=requirements,
            error_type=error_type,
        )

    if requirements.keys() != state.custom_namespaces:
        raise error_type(
            "presentation: renderer requirements must exactly match custom "
            "component namespaces"
        )
    for namespace, requirement in requirements.items():
        if (
            _namespace(cast(str, requirement["extensionIdentifier"]))
            != namespace
        ):
            raise error_type(
                "presentation: renderer extension namespace must match its "
                "component namespace"
            )

    _validate_assets(message, state.asset_references, error_type)


class _PresentationState:
    """Track document-wide component and reference budgets."""

    def __init__(self) -> None:
        self.component_count = 0
        self.custom_namespaces: set[str] = set()
        self.asset_references: set[str] = set()


def _validate_target(
    target: dict[str, Any],
    *,
    target_kind: str,
    permitted_surfaces: frozenset[str],
    state: _PresentationState,
    requirements: dict[str, dict[str, Any]],
    error_type: type[ValueError],
) -> None:
    surfaces = cast(dict[str, dict[str, Any]], target["surfaces"])
    unsupported = surfaces.keys() - permitted_surfaces
    if unsupported:
        raise error_type(
            f"presentation: surface is not valid for {target_kind} targets"
        )
    for surface_identifier, surface in surfaces.items():
        _validate_component(
            cast(dict[str, Any], surface["root"]),
            surface_identifier=surface_identifier,
            target_kind=target_kind,
            scopes=frozenset(),
            depth=1,
            core_only=False,
            state=state,
            requirements=requirements,
            error_type=error_type,
        )


def _validate_component(
    node: dict[str, Any],
    *,
    surface_identifier: str,
    target_kind: str,
    scopes: frozenset[str],
    depth: int,
    core_only: bool,
    state: _PresentationState,
    requirements: dict[str, dict[str, Any]],
    error_type: type[ValueError],
) -> None:
    if depth > contract.MAX_PRESENTATION_COMPONENT_DEPTH:
        raise error_type("presentation: component depth limit exceeded")
    state.component_count += 1
    if state.component_count > contract.MAX_PRESENTATION_COMPONENTS:
        raise error_type("presentation: component count limit exceeded")

    _validate_component_identity(
        node,
        core_only=core_only,
        state=state,
        requirements=requirements,
        error_type=error_type,
    )

    properties = cast(dict[str, Any], node["properties"])
    if (
        len(rfc8785.dumps(properties))
        > contract.MAX_COMPONENT_PROPERTIES_BYTES
    ):
        raise error_type("presentation: component properties limit exceeded")

    current_scopes = _extend_repetition_scopes(
        node,
        surface_identifier=surface_identifier,
        target_kind=target_kind,
        scopes=scopes,
        error_type=error_type,
    )

    for binding in cast(dict[str, dict[str, Any]], node["bindings"]).values():
        _validate_binding(
            binding,
            surface_identifier=surface_identifier,
            target_kind=target_kind,
            scopes=current_scopes,
            error_type=error_type,
        )
    _validate_optional_condition(
        node,
        surface_identifier=surface_identifier,
        target_kind=target_kind,
        scopes=current_scopes,
        error_type=error_type,
    )
    state.asset_references.update(
        cast(dict[str, str], node["assetBindings"]).values()
    )

    _validate_optional_fallback(
        node,
        surface_identifier=surface_identifier,
        target_kind=target_kind,
        scopes=current_scopes,
        depth=depth,
        state=state,
        requirements=requirements,
        error_type=error_type,
    )
    for child in cast(list[dict[str, Any]], node["children"]):
        _validate_component(
            child,
            surface_identifier=surface_identifier,
            target_kind=target_kind,
            scopes=current_scopes,
            depth=depth + 1,
            core_only=core_only,
            state=state,
            requirements=requirements,
            error_type=error_type,
        )


def _validate_component_identity(
    node: dict[str, Any],
    *,
    core_only: bool,
    state: _PresentationState,
    requirements: dict[str, dict[str, Any]],
    error_type: type[ValueError],
) -> None:
    identifier = cast(str, node["componentIdentifier"])
    namespace = _namespace(identifier)
    is_core = namespace == contract.CORE_COMPONENT_NAMESPACE
    if is_core and identifier not in contract.CORE_COMPONENT_IDENTIFIERS:
        raise error_type("presentation: unknown core component identifier")
    if core_only and not is_core:
        raise error_type(
            "presentation: custom component fallback must use core components"
        )
    if not is_core:
        if namespace not in requirements:
            raise error_type(
                "presentation: custom component has no renderer requirement"
            )
        if "fallback" not in node:
            raise error_type(
                "presentation: custom component requires a core fallback"
            )
        state.custom_namespaces.add(namespace)


def _extend_repetition_scopes(
    node: dict[str, Any],
    *,
    surface_identifier: str,
    target_kind: str,
    scopes: frozenset[str],
    error_type: type[ValueError],
) -> frozenset[str]:
    repeat = node.get("repeat")
    if not isinstance(repeat, dict):
        return scopes
    _validate_binding(
        cast(dict[str, Any], repeat["collection"]),
        surface_identifier=surface_identifier,
        target_kind=target_kind,
        scopes=scopes,
        error_type=error_type,
    )
    item_scope = cast(str, repeat["itemScope"])
    if item_scope in scopes:
        raise error_type("presentation: repetition scopes must be unique")
    return scopes | {item_scope}


def _validate_optional_condition(
    node: dict[str, Any],
    *,
    surface_identifier: str,
    target_kind: str,
    scopes: frozenset[str],
    error_type: type[ValueError],
) -> None:
    condition = node.get("condition")
    if isinstance(condition, dict):
        _validate_condition(
            condition,
            surface_identifier=surface_identifier,
            target_kind=target_kind,
            scopes=scopes,
            error_type=error_type,
        )


def _validate_optional_fallback(
    node: dict[str, Any],
    *,
    surface_identifier: str,
    target_kind: str,
    scopes: frozenset[str],
    depth: int,
    state: _PresentationState,
    requirements: dict[str, dict[str, Any]],
    error_type: type[ValueError],
) -> None:
    fallback = node.get("fallback")
    if isinstance(fallback, dict):
        _validate_component(
            fallback,
            surface_identifier=surface_identifier,
            target_kind=target_kind,
            scopes=scopes,
            depth=depth + 1,
            core_only=True,
            state=state,
            requirements=requirements,
            error_type=error_type,
        )


def _validate_condition(
    condition: dict[str, Any],
    *,
    surface_identifier: str,
    target_kind: str,
    scopes: frozenset[str],
    error_type: type[ValueError],
) -> None:
    _validate_binding(
        cast(dict[str, Any], condition["binding"]),
        surface_identifier=surface_identifier,
        target_kind=target_kind,
        scopes=scopes,
        error_type=error_type,
    )
    operator = cast(str, condition["operator"])
    has_value = "value" in condition
    if (
        operator
        in {
            "CONDITION_OPERATOR_EXISTS",
            "CONDITION_OPERATOR_NOT_EXISTS",
        }
        and has_value
    ):
        raise error_type(
            "presentation: existence condition cannot declare a value"
        )
    if (
        operator
        in {
            "CONDITION_OPERATOR_EQUALS",
            "CONDITION_OPERATOR_NOT_EQUALS",
        }
        and not has_value
    ):
        raise error_type("presentation: equality condition requires a value")


def _validate_binding(
    binding: dict[str, Any],
    *,
    surface_identifier: str,
    target_kind: str,
    scopes: frozenset[str],
    error_type: type[ValueError],
) -> None:
    source = cast(str, binding["sourceIdentifier"])
    scope = cast(str, binding["scope"])
    if source == contract.REPETITION_ITEM_BINDING:
        if not scope or scope not in scopes:
            raise error_type(
                "presentation: repetition item binding has no active scope"
            )
        return
    if scope:
        raise error_type(
            "presentation: only repetition item bindings may name a scope"
        )
    allowed = set(contract.SURFACE_BINDING_SOURCES[surface_identifier])
    if surface_identifier == contract.EVIDENCE_SURFACE:
        if target_kind == "operation":
            allowed.discard(contract.TRIGGER_PAYLOAD_VALUE_BINDING)
        elif target_kind == "trigger":
            allowed.discard(contract.OPERATION_EVIDENCE_BINDING)
    if source not in allowed:
        raise error_type(
            "presentation: binding source is unavailable on this surface"
        )


def _namespace(identifier: str) -> str:
    return identifier.split("/", 1)[0]


def _validate_assets(
    message: manifest_pb2.ProviderPresentation,
    references: set[str],
    error_type: type[ValueError],
) -> None:
    assets = message.assets
    total_bytes = sum(len(asset.content) for asset in assets.values())
    if total_bytes > contract.MAX_PRESENTATION_ASSET_TOTAL_BYTES:
        raise error_type("presentation: aggregate asset limit exceeded")
    for digest, asset in assets.items():
        if (
            not asset.content
            or len(asset.content) > contract.MAX_PRESENTATION_ASSET_BYTES
        ):
            raise error_type("presentation: asset byte limit exceeded")
        expected = "sha256:" + hashlib.sha256(asset.content).hexdigest()
        if digest != expected:
            raise error_type("presentation: asset digest mismatch")
        _validate_asset_content(asset, error_type)

    if not references <= assets.keys():
        raise error_type("presentation: asset reference is missing")
    if assets.keys() - references:
        raise error_type("presentation: unreferenced asset is not permitted")


def _validate_asset_content(
    asset: manifest_pb2.PresentationAsset,
    error_type: type[ValueError],
) -> None:
    if asset.media_type not in contract.ALLOWED_PRESENTATION_MEDIA_TYPES:
        raise error_type("presentation: asset media type is not permitted")
    if asset.media_type == "image/svg+xml":
        _validate_svg(asset.content, error_type)
        return
    dimensions = _png_dimensions(asset.content, error_type)
    if dimensions != (asset.width, asset.height):
        raise error_type("presentation: asset dimensions do not match content")


def _validate_svg(content: bytes, error_type: type[ValueError]) -> None:
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise error_type("presentation: unsafe SVG construct")
    try:
        # DTDs and entities are rejected above; every parsed tag and attribute
        # is then checked against a closed SVG allowlist below.
        root = ElementTree.fromstring(content)  # noqa: S314
    except (ElementTree.ParseError, UnicodeError):
        raise error_type("presentation: invalid SVG content") from None
    if _local_name(root.tag) != "svg" or "viewBox" not in root.attrib:
        raise error_type("presentation: SVG requires a root viewBox")
    for nodes, element in enumerate(root.iter(), start=1):
        if nodes > contract.MAX_SCHEMA_NODES:
            raise error_type("presentation: SVG node limit exceeded")
        namespace, tag = _split_name(element.tag)
        if namespace not in {"", _SVG_NAMESPACE} or tag not in _SAFE_SVG_TAGS:
            raise error_type("presentation: unsafe SVG element")
        for attribute, value in element.attrib.items():
            attribute_namespace, name = _split_name(attribute)
            if attribute_namespace or name not in _SAFE_SVG_ATTRIBUTES:
                raise error_type("presentation: unsafe SVG attribute")
            lowered = value.lower()
            if "javascript:" in lowered or "data:" in lowered:
                raise error_type("presentation: unsafe SVG reference")
            if "url(" in lowered and not _LOCAL_ASSET_REFERENCE.fullmatch(
                value
            ):
                raise error_type("presentation: unsafe SVG reference")


def _split_name(value: str) -> tuple[str, str]:
    if value.startswith("{") and "}" in value:
        namespace, name = value[1:].split("}", 1)
        return namespace, name
    return "", value


def _local_name(value: str) -> str:
    return _split_name(value)[1]


def _png_dimensions(
    content: bytes,
    error_type: type[ValueError],
) -> tuple[int, int]:
    """Validate a bounded, static PNG and return its declared dimensions."""
    if not content.startswith(_PNG_SIGNATURE):
        _reject_png(error_type)
    offset = len(_PNG_SIGNATURE)
    dimensions: tuple[int, int] | None = None
    saw_image_data = False
    while offset + _PNG_CHUNK_OVERHEAD <= len(content):
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        chunk_type = content[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        chunk_end = data_end + 4
        if chunk_end > len(content) or chunk_type not in _SAFE_PNG_CHUNKS:
            _reject_png(error_type)
        expected_crc = struct.unpack(">I", content[data_end:chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(content[data_start:data_end], actual_crc)
        if expected_crc != actual_crc & 0xFFFFFFFF:
            _reject_png(error_type)
        if dimensions is None:
            if chunk_type != b"IHDR" or length != _PNG_IHDR_BYTES:
                _reject_png(error_type)
            width, height = struct.unpack(
                ">II", content[data_start : data_start + 8]
            )
            bit_depth = content[data_start + 8]
            color_type = content[data_start + 9]
            valid_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if (
                not width
                or not height
                or width > contract.MAX_PRESENTATION_ASSET_DIMENSION
                or height > contract.MAX_PRESENTATION_ASSET_DIMENSION
                or bit_depth not in valid_depths.get(color_type, set())
                or content[data_start + 10 : data_start + 12] != b"\x00\x00"
                or content[data_start + 12] not in {0, 1}
            ):
                _reject_png(error_type)
            dimensions = (width, height)
        elif chunk_type == b"IHDR":
            _reject_png(error_type)
        if chunk_type == b"IDAT":
            saw_image_data = True
        if chunk_type == b"IEND":
            if length or not saw_image_data or chunk_end != len(content):
                _reject_png(error_type)
            if dimensions is None:
                _reject_png(error_type)
            return dimensions
        offset = chunk_end
    _reject_png(error_type)


def _reject_png(error_type: type[ValueError]) -> Never:
    raise error_type("presentation: invalid PNG content")
