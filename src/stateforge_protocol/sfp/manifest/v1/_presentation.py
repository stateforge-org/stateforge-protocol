"""Validate Provider presentation overlays and embedded visual assets."""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from collections.abc import Iterable
from typing import Any, Final, Never, cast
from urllib.parse import unquote
from xml.etree import ElementTree

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
_SCALAR_TYPES: Final = frozenset({"boolean", "integer", "number", "string"})
_NUMBER_TYPES: Final = frozenset({"integer", "number"})
_JSON_TYPES: Final = frozenset({"array", "object"})
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
    """Validate references, schema overlays and assets for presentation v1."""
    operations = cast(dict[str, dict[str, Any]], manifest["operations"])
    triggers = cast(dict[str, dict[str, Any]], manifest["triggers"])
    operation_views = cast(
        dict[str, dict[str, Any]], presentation["operations"]
    )
    trigger_views = cast(dict[str, dict[str, Any]], presentation["triggers"])

    if not operation_views.keys() <= operations.keys():
        raise error_type(
            "presentation: operation view does not name a declared operation"
        )
    if not trigger_views.keys() <= triggers.keys():
        raise error_type(
            "presentation: trigger view does not name a declared trigger"
        )

    group_ids = _validate_capability_groups(presentation, error_type)
    for identifier, view in operation_views.items():
        _validate_group_reference(view, group_ids, error_type)
        declaration = operations[identifier]
        if "input" in view:
            _validate_schema_view(
                cast(dict[str, Any], view["input"]),
                cast(dict[str, Any], declaration["inputSchema"]),
                input_scope=True,
                error_type=error_type,
            )
        if "result" in view:
            _validate_schema_view(
                cast(dict[str, Any], view["result"]),
                cast(dict[str, Any], declaration["resultSchema"]),
                input_scope=False,
                error_type=error_type,
            )
    for identifier, view in trigger_views.items():
        _validate_group_reference(view, group_ids, error_type)
        if "payload" in view:
            declaration = triggers[identifier]
            _validate_schema_view(
                cast(dict[str, Any], view["payload"]),
                cast(dict[str, Any], declaration["payloadSchema"]),
                input_scope=False,
                error_type=error_type,
            )

    _validate_assets(presentation, message, error_type)


def _validate_capability_groups(
    presentation: dict[str, Any], error_type: type[ValueError]
) -> frozenset[str]:
    provider = presentation.get("provider")
    if provider is None:
        return frozenset()
    groups = cast(dict[str, Any], provider)["groups"]
    identifiers = [cast(dict[str, Any], group)["id"] for group in groups]
    if len(identifiers) != len(set(identifiers)):
        raise error_type("presentation: capability group IDs must be unique")
    return frozenset(cast(Iterable[str], identifiers))


def _validate_group_reference(
    view: dict[str, Any],
    group_ids: frozenset[str],
    error_type: type[ValueError],
) -> None:
    group_id = view["groupId"]
    if group_id and group_id not in group_ids:
        raise error_type("presentation: capability group reference is missing")


def _validate_schema_view(
    view: dict[str, Any],
    schema: dict[str, Any],
    *,
    input_scope: bool,
    error_type: type[ValueError],
) -> None:
    pointers = list(cast(list[str], view["fieldOrder"]))
    field_views = cast(dict[str, dict[str, Any]], view["fields"])
    pointers.extend(field_views)
    grouped: list[str] = []
    group_ids: list[str] = []
    for group in cast(list[dict[str, Any]], view["groups"]):
        group_ids.append(cast(str, group["id"]))
        grouped.extend(cast(list[str], group["fields"]))
    if len(group_ids) != len(set(group_ids)):
        raise error_type("presentation: field group IDs must be unique")
    if len(grouped) != len(set(grouped)):
        raise error_type(
            "presentation: a field may belong to at most one field group"
        )
    pointers.extend(grouped)

    property_nodes = _property_schema_nodes(schema)
    resolved: dict[str, dict[str, Any]] = {}
    for pointer in set(pointers):
        target = _resolve_json_pointer(schema, pointer, error_type)
        if not isinstance(target, dict) or id(target) not in property_nodes:
            raise error_type(
                "presentation: JSON Pointer must name a schema field"
            )
        resolved[pointer] = target

    for pointer, field_view in field_views.items():
        target = _follow_local_reference(resolved[pointer], schema, error_type)
        _validate_field_preferences(
            field_view,
            target,
            input_scope=input_scope,
            error_type=error_type,
        )


def _property_schema_nodes(schema: dict[str, Any]) -> set[int]:
    nodes: set[int] = set()
    pending: list[object] = [schema]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            properties = current.get("properties")
            if isinstance(properties, dict):
                nodes.update(
                    id(value)
                    for value in properties.values()
                    if isinstance(value, dict)
                )
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return nodes


def _resolve_json_pointer(
    document: object, pointer: str, error_type: type[ValueError]
) -> object:
    current = document
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit():
            index = int(token)
            if index >= len(current):
                raise error_type("presentation: JSON Pointer does not resolve")
            current = current[index]
        else:
            raise error_type("presentation: JSON Pointer does not resolve")
    return current


def _follow_local_reference(
    schema: dict[str, Any],
    root: dict[str, Any],
    error_type: type[ValueError],
) -> dict[str, Any]:
    current = schema
    seen: set[int] = set()
    while "$ref" in current:
        identity = id(current)
        if identity in seen:
            raise error_type("presentation: cyclic field schema reference")
        seen.add(identity)
        reference = current["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#"):
            raise error_type("presentation: field schema reference is invalid")
        fragment = unquote(reference[1:])
        target = (
            root
            if not fragment
            else _resolve_json_pointer(root, fragment, error_type)
        )
        if not isinstance(target, dict):
            raise error_type(
                "presentation: field schema reference must name a schema"
            )
        current = target
    return current


def _validate_field_preferences(
    view: dict[str, Any],
    schema: dict[str, Any],
    *,
    input_scope: bool,
    error_type: type[ValueError],
) -> None:
    widget = cast(str, view["widget"])
    display = cast(str, view["display"])
    if not input_scope and (
        widget != "INPUT_WIDGET_UNSPECIFIED" or view["placeholder"]
    ):
        raise error_type(
            "presentation: output fields cannot declare input preferences"
        )
    types = _schema_types(schema)
    _validate_widget(widget, schema, types, error_type)
    _validate_display(display, schema, types, error_type)


def _validate_widget(
    widget: str,
    schema: dict[str, Any],
    types: frozenset[str],
    error_type: type[ValueError],
) -> None:
    """Require one input widget to match its field schema."""
    if widget == "INPUT_WIDGET_UNSPECIFIED":
        return
    elif widget in {"INPUT_WIDGET_TEXT", "INPUT_WIDGET_MULTILINE"}:
        _require_types(types, {"string"}, "input widget", error_type)
    elif widget == "INPUT_WIDGET_SECRET":
        _require_types(types, {"string"}, "input widget", error_type)
        if schema.get("writeOnly") is not True:
            raise error_type(
                "presentation: secret widget requires a write-only field"
            )
    elif widget == "INPUT_WIDGET_NUMBER":
        _require_types(types, _NUMBER_TYPES, "input widget", error_type)
    elif widget == "INPUT_WIDGET_SLIDER":
        _require_types(types, _NUMBER_TYPES, "input widget", error_type)
        if "minimum" not in schema or "maximum" not in schema:
            raise error_type(
                "presentation: slider requires schema minimum and maximum"
            )
    elif widget == "INPUT_WIDGET_CHECKBOX":
        _require_types(types, {"boolean"}, "input widget", error_type)
    elif widget in {"INPUT_WIDGET_SELECT", "INPUT_WIDGET_RADIO"}:
        if not isinstance(schema.get("enum"), list) or not schema["enum"]:
            raise error_type(
                "presentation: choice widget requires a nonempty schema enum"
            )
    elif widget == "INPUT_WIDGET_DATE_TIME":
        _require_date_time(schema, types, "input widget", error_type)
    elif widget == "INPUT_WIDGET_JSON":
        _require_types(types, _JSON_TYPES, "input widget", error_type)


def _validate_display(
    display: str,
    schema: dict[str, Any],
    types: frozenset[str],
    error_type: type[ValueError],
) -> None:
    """Require one display style to match its field schema."""
    if display == "DISPLAY_STYLE_UNSPECIFIED":
        return
    if display == "DISPLAY_STYLE_TEXT":
        _require_types(types, _SCALAR_TYPES, "display style", error_type)
    elif display == "DISPLAY_STYLE_CODE":
        _require_types(types, {"string"}, "display style", error_type)
    elif display == "DISPLAY_STYLE_JSON":
        _require_types(types, _JSON_TYPES, "display style", error_type)
    elif display == "DISPLAY_STYLE_TABLE":
        _require_types(types, {"array"}, "display style", error_type)
    elif display == "DISPLAY_STYLE_BADGE":
        _require_types(types, _SCALAR_TYPES, "display style", error_type)
    elif display == "DISPLAY_STYLE_METRIC":
        _require_types(types, _NUMBER_TYPES, "display style", error_type)
    elif display == "DISPLAY_STYLE_DATE_TIME":
        _require_date_time(schema, types, "display style", error_type)


def _schema_types(schema: dict[str, Any]) -> frozenset[str]:
    declared = schema.get("type")
    if isinstance(declared, str):
        return frozenset({declared})
    if isinstance(declared, list) and all(
        isinstance(value, str) for value in declared
    ):
        return frozenset(declared) - {"null"}
    return frozenset()


def _require_types(
    actual: frozenset[str],
    permitted: Iterable[str],
    preference: str,
    error_type: type[ValueError],
) -> None:
    allowed = frozenset(permitted)
    if not actual or not actual <= allowed:
        raise error_type(
            f"presentation: {preference} is incompatible with schema type"
        )


def _require_date_time(
    schema: dict[str, Any],
    types: frozenset[str],
    preference: str,
    error_type: type[ValueError],
) -> None:
    _require_types(types, {"string"}, preference, error_type)
    if schema.get("format") not in {"date", "date-time", "time"}:
        raise error_type(
            f"presentation: {preference} requires a date or time format"
        )


def _validate_assets(
    presentation: dict[str, Any],
    message: manifest_pb2.ProviderPresentation,
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

    references = _asset_references(presentation)
    if not references <= assets.keys():
        raise error_type("presentation: asset reference is missing")
    if assets.keys() - references:
        raise error_type("presentation: unreferenced asset is not permitted")


def _asset_references(presentation: dict[str, Any]) -> set[str]:
    references: set[str] = set()
    provider = presentation.get("provider")
    if isinstance(provider, dict):
        _add_asset_reference(references, provider.get("iconAssetDigest"))
        _add_asset_reference(references, provider.get("bannerAssetDigest"))
        for group in cast(list[dict[str, Any]], provider["groups"]):
            _add_asset_reference(references, group.get("iconAssetDigest"))
    for collection in ("operations", "triggers"):
        views = cast(dict[str, dict[str, Any]], presentation[collection])
        for view in views.values():
            _add_asset_reference(references, view.get("iconAssetDigest"))
    return references


def _add_asset_reference(references: set[str], value: object) -> None:
    if isinstance(value, str) and value:
        references.add(value)


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
