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
_PNG_DECODE_CHUNK_BYTES: Final = 64 * 1024
_PNG_MAX_FILTER_TYPE: Final = 4
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
    if any(_is_stateforge_owned(namespace) for namespace in requirements):
        raise error_type(
            "presentation: renderer requirements cannot use a "
            "StateForge-owned namespace"
        )

    state = _PresentationState()
    targets = [presentation.get("provider")]
    targets.extend(operation_targets.values())
    targets.extend(trigger_targets.values())
    for target in targets:
        if isinstance(target, dict):
            _validate_target(
                target,
                state=state,
                error_type=error_type,
            )

    _validate_assets(message, state.asset_references, error_type)


class _PresentationState:
    """Track document-wide component and reference budgets."""

    def __init__(self) -> None:
        self.component_count = 0
        self.asset_references: set[str] = set()


def _validate_target(
    target: dict[str, Any],
    *,
    state: _PresentationState,
    error_type: type[ValueError],
) -> None:
    surfaces = cast(dict[str, dict[str, Any]], target["surfaces"])
    for surface in surfaces.values():
        _validate_component(
            cast(dict[str, Any], surface["root"]),
            scopes=frozenset(),
            depth=1,
            state=state,
            error_type=error_type,
        )


def _validate_component(
    node: dict[str, Any],
    *,
    scopes: frozenset[str],
    depth: int,
    state: _PresentationState,
    error_type: type[ValueError],
) -> None:
    if depth > contract.MAX_PRESENTATION_COMPONENT_DEPTH:
        raise error_type("presentation: component depth limit exceeded")
    state.component_count += 1
    if state.component_count > contract.MAX_PRESENTATION_COMPONENTS:
        raise error_type("presentation: component count limit exceeded")

    properties = cast(dict[str, Any], node["properties"])
    if (
        len(rfc8785.dumps(properties))
        > contract.MAX_COMPONENT_PROPERTIES_BYTES
    ):
        raise error_type("presentation: component properties limit exceeded")

    current_scopes = _extend_repetition_scopes(
        node,
        scopes=scopes,
        error_type=error_type,
    )

    for binding in cast(dict[str, dict[str, Any]], node["bindings"]).values():
        _validate_binding(
            binding,
            scopes=current_scopes,
            error_type=error_type,
        )
    _validate_optional_condition(
        node,
        scopes=current_scopes,
        error_type=error_type,
    )
    state.asset_references.update(
        cast(dict[str, str], node["assetBindings"]).values()
    )
    _validate_optional_fallback(
        node,
        scopes=current_scopes,
        depth=depth,
        state=state,
        error_type=error_type,
    )
    for child in cast(list[dict[str, Any]], node["children"]):
        _validate_component(
            child,
            scopes=current_scopes,
            depth=depth + 1,
            state=state,
            error_type=error_type,
        )


def _extend_repetition_scopes(
    node: dict[str, Any],
    *,
    scopes: frozenset[str],
    error_type: type[ValueError],
) -> frozenset[str]:
    repeat = node.get("repeat")
    if not isinstance(repeat, dict):
        return scopes
    _validate_binding(
        cast(dict[str, Any], repeat["collection"]),
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
    scopes: frozenset[str],
    error_type: type[ValueError],
) -> None:
    condition = node.get("condition")
    if isinstance(condition, dict):
        _validate_condition(
            condition,
            scopes=scopes,
            error_type=error_type,
        )


def _validate_optional_fallback(
    node: dict[str, Any],
    *,
    scopes: frozenset[str],
    depth: int,
    state: _PresentationState,
    error_type: type[ValueError],
) -> None:
    fallback = node.get("fallback")
    if isinstance(fallback, dict):
        _validate_component(
            fallback,
            scopes=scopes,
            depth=depth + 1,
            state=state,
            error_type=error_type,
        )


def _validate_condition(
    condition: dict[str, Any],
    *,
    scopes: frozenset[str],
    error_type: type[ValueError],
) -> None:
    _validate_binding(
        cast(dict[str, Any], condition["binding"]),
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
    scopes: frozenset[str],
    error_type: type[ValueError],
) -> None:
    source = cast(str, binding["sourceIdentifier"])
    scope = cast(str, binding["scope"])
    if source == contract.RAW_OPERATION_REQUEST_BINDING:
        raise error_type(
            "presentation: raw operation request values cannot be bound"
        )
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


def _namespace(identifier: str) -> str:
    return identifier.split("/", 1)[0]


def _is_stateforge_owned(namespace: str) -> bool:
    return (
        namespace == contract.STATEFORGE_NAMESPACE_ROOT
        or namespace.startswith(f"{contract.STATEFORGE_NAMESPACE_ROOT}.")
    )


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
    bit_depth: int | None = None
    color_type: int | None = None
    interlace_method: int | None = None
    image_data: list[bytes] = []
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
            (
                dimensions,
                bit_depth,
                color_type,
                interlace_method,
            ) = _read_png_header(
                chunk_type,
                content[data_start:data_end],
                error_type,
            )
        elif chunk_type == b"IHDR":
            _reject_png(error_type)
        if chunk_type == b"IDAT":
            saw_image_data = True
            image_data.append(content[data_start:data_end])
        elif saw_image_data and chunk_type != b"IEND":
            _reject_png(error_type)
        if chunk_type == b"IEND":
            if length or not saw_image_data or chunk_end != len(content):
                _reject_png(error_type)
            if (
                dimensions is None
                or bit_depth is None
                or color_type is None
                or interlace_method is None
            ):
                _reject_png(error_type)
            _validate_png_image_data(
                b"".join(image_data),
                width=dimensions[0],
                height=dimensions[1],
                bit_depth=bit_depth,
                color_type=color_type,
                interlace_method=interlace_method,
                error_type=error_type,
            )
            return dimensions
        offset = chunk_end
    _reject_png(error_type)


def _read_png_header(
    chunk_type: bytes,
    data: bytes,
    error_type: type[ValueError],
) -> tuple[tuple[int, int], int, int, int]:
    if chunk_type != b"IHDR" or len(data) != _PNG_IHDR_BYTES:
        _reject_png(error_type)
    width, height = struct.unpack(">II", data[:8])
    bit_depth = data[8]
    color_type = data[9]
    interlace_method = data[12]
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
        or data[10:12] != b"\x00\x00"
        or interlace_method not in {0, 1}
    ):
        _reject_png(error_type)
    return (width, height), bit_depth, color_type, interlace_method


def _validate_png_image_data(
    compressed: bytes,
    *,
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
    interlace_method: int,
    error_type: type[ValueError],
) -> None:
    """Decode bounded IDAT data and validate its complete scanline framing."""
    scanline_lengths = _png_scanline_lengths(
        width,
        height,
        bit_depth,
        color_type,
        interlace_method,
    )
    decoded_bytes = sum(length + 1 for length in scanline_lengths)
    if decoded_bytes > contract.MAX_PRESENTATION_PNG_DECODED_BYTES:
        _reject_png(error_type)

    decoder = zlib.decompressobj()
    pending = compressed
    row_index = 0
    row_remaining = 0
    try:
        while True:
            pending_bytes = len(pending)
            decoded = decoder.decompress(pending, _PNG_DECODE_CHUNK_BYTES)
            pending = decoder.unconsumed_tail
            row_index, row_remaining = _consume_png_scanlines(
                decoded,
                scanline_lengths=scanline_lengths,
                row_index=row_index,
                row_remaining=row_remaining,
                error_type=error_type,
            )
            if decoder.eof:
                if pending or decoder.unused_data:
                    _reject_png(error_type)
                break
            if (not pending and not decoded) or (
                not decoded and len(pending) == pending_bytes
            ):
                _reject_png(error_type)
    except zlib.error:
        _reject_png(error_type)

    if row_index != len(scanline_lengths) or row_remaining:
        _reject_png(error_type)


def _consume_png_scanlines(
    decoded: bytes,
    *,
    scanline_lengths: tuple[int, ...],
    row_index: int,
    row_remaining: int,
    error_type: type[ValueError],
) -> tuple[int, int]:
    for value in decoded:
        if not row_remaining:
            if (
                row_index >= len(scanline_lengths)
                or value > _PNG_MAX_FILTER_TYPE
            ):
                _reject_png(error_type)
            row_remaining = scanline_lengths[row_index]
            row_index += 1
        else:
            row_remaining -= 1
    return row_index, row_remaining


def _png_scanline_lengths(
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
    interlace_method: int,
) -> tuple[int, ...]:
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    bits_per_pixel = channels * bit_depth
    if not interlace_method:
        row_bytes = (width * bits_per_pixel + 7) // 8
        return (row_bytes,) * height

    passes = (
        (0, 0, 8, 8),
        (4, 0, 8, 8),
        (0, 4, 4, 8),
        (2, 0, 4, 4),
        (0, 2, 2, 4),
        (1, 0, 2, 2),
        (0, 1, 1, 2),
    )
    rows: list[int] = []
    for x_start, y_start, x_step, y_step in passes:
        if width <= x_start or height <= y_start:
            continue
        pass_width = (width - x_start + x_step - 1) // x_step
        pass_height = (height - y_start + y_step - 1) // y_step
        row_bytes = (pass_width * bits_per_pixel + 7) // 8
        rows.extend((row_bytes,) * pass_height)
    return tuple(rows)


def _reject_png(error_type: type[ValueError]) -> Never:
    raise error_type("presentation: invalid PNG content")
