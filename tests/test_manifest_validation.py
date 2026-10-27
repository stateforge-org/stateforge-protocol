"""Executable semantic-validation evidence for Provider Manifest v1."""

import copy
import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest
from google.protobuf.json_format import MessageToDict, ParseDict

from stateforge_protocol.sfp.manifest.v1 import contract, manifest_pb2
from stateforge_protocol.sfp.manifest.v1.validation import (
    ManifestValidationError,
    ManifestValidationLimits,
    PresentationValidationStatus,
    bounded_json,
    canonical_bytes,
    canonical_presentation_bytes,
    compute_manifest_revision,
    compute_presentation_revision,
    contract_validator,
    validate_manifest_exchange,
    validate_manifest_key,
    validate_manifest_response,
    validate_presentation_document,
    validate_presentation_key,
    validate_schema,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "manifest"
_GOLDEN_REVISION = (
    "sha256:6bfdf3aedc2d4e45d77d4787cc0e744a488208b2510d81788291f51d24a623e8"
)


def _response() -> manifest_pb2.GetManifestResponse:
    document = json.loads((_FIXTURES / "response.json").read_text())
    return ParseDict(document, manifest_pb2.GetManifestResponse())


def _presentation_response() -> manifest_pb2.GetManifestResponse:
    document = json.loads(
        (_FIXTURES / "presentation-response.json").read_text()
    )
    return ParseDict(document, manifest_pb2.GetManifestResponse())


def _project(message) -> dict[str, object]:
    return MessageToDict(
        message,
        always_print_fields_with_no_presence=True,
    )


def _refresh_presentation_revision(
    response: manifest_pb2.GetManifestResponse,
) -> None:
    response.presentation_revision = compute_presentation_revision(
        _project(response.presentation),
        response.manifest_revision,
        response.provider_instance_id,
    )


def _refresh_manifest_revision(
    response: manifest_pb2.GetManifestResponse,
) -> None:
    response.manifest_revision = compute_manifest_revision(
        _project(response.manifest),
        response.manifest_schema_version,
        response.provider_instance_id,
    )


def _validate_presentation(
    response: manifest_pb2.GetManifestResponse,
) -> bytes:
    return validate_presentation_document(
        response.presentation,
        _project(response.manifest),
    )


def _png_chunk(kind: bytes, content: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(content, checksum) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(content))
        + kind
        + content
        + struct.pack(">I", checksum)
    )


def _png(width: int = 1, height: int = 1) -> bytes:

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    pixels = b"".join(
        b"\x00" + (b"\x00\x00\x00\x00" * width) for _ in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(pixels))
        + _png_chunk(b"IEND", b"")
    )


def _replace_provider_icon(
    response: manifest_pb2.GetManifestResponse,
    *,
    content: bytes,
    media_type: str,
    width: int,
    height: int,
) -> str:
    old_digest = response.presentation.provider.icon_asset_digest
    del response.presentation.assets[old_digest]
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    response.presentation.assets[digest].CopyFrom(
        manifest_pb2.PresentationAsset(
            media_type=media_type,
            content=content,
            width=width,
            height=height,
            alt_text="Provider icon",
        )
    )
    response.presentation.provider.icon_asset_digest = digest
    return digest


def _schema(**overrides):
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        **overrides,
    }


def test_validates_and_canonicalizes_the_cross_language_vector() -> None:
    response = _response()

    document = validate_manifest_response(response)

    projected = json.loads((_FIXTURES / "response.json").read_text())
    assert json.loads(document) == projected["manifest"]
    assert response.manifest_revision == _GOLDEN_REVISION
    assert (
        compute_manifest_revision(
            projected["manifest"],
            projected["manifestSchemaVersion"],
            projected["providerInstanceId"],
        )
        == _GOLDEN_REVISION
    )


def test_accepts_complete_provider_presentation_snapshot() -> None:
    response = _presentation_response()

    exchange = validate_manifest_exchange(response)

    expected = json.loads(
        (_FIXTURES / "presentation-response.json").read_text()
    )
    assert (
        exchange.presentation_status is PresentationValidationStatus.ACCEPTED
    )
    assert json.loads(exchange.manifest_document) == expected["manifest"]
    assert (
        json.loads(exchange.presentation_document or b"")
        == expected["presentation"]
    )
    assert exchange.presentation_key is not None
    assert exchange.presentation_key.revision == response.presentation_revision
    assert (
        exchange.presentation_key.manifest_revision
        == response.manifest_revision
    )


def test_absent_presentation_uses_schema_derived_rendering() -> None:
    exchange = validate_manifest_exchange(_response())

    assert exchange.presentation_status is PresentationValidationStatus.ABSENT
    assert exchange.presentation_key is None
    assert exchange.presentation_document is None


def test_empty_presentation_overlay_is_valid() -> None:
    response = _presentation_response()
    response.presentation.ClearField("provider")
    response.presentation.ClearField("operations")
    response.presentation.ClearField("triggers")
    response.presentation.ClearField("assets")
    _refresh_presentation_revision(response)

    exchange = validate_manifest_exchange(response)

    assert (
        exchange.presentation_status is PresentationValidationStatus.ACCEPTED
    )
    assert json.loads(exchange.presentation_document or b"") == {
        "assets": {},
        "operations": {},
        "presentationSchemaVersion": 1,
        "triggers": {},
    }


def test_invalid_presentation_falls_back_without_rejecting_manifest() -> None:
    response = _presentation_response()
    operation = response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ]
    operation.input.field_order[0] = "/properties/not-declared"
    _refresh_presentation_revision(response)

    exchange = validate_manifest_exchange(response)

    assert exchange.presentation_status is PresentationValidationStatus.INVALID
    assert exchange.presentation_document is None
    assert exchange.presentation_key is None
    assert exchange.manifest_document == validate_manifest_response(response)


@pytest.mark.parametrize(
    ("schema_version", "status"),
    [
        (0, PresentationValidationStatus.INVALID),
        (2, PresentationValidationStatus.UNSUPPORTED),
    ],
)
def test_unknown_or_invalid_presentation_versions_fall_back(
    schema_version: int,
    status: PresentationValidationStatus,
) -> None:
    response = _presentation_response()
    response.presentation.presentation_schema_version = schema_version

    exchange = validate_manifest_exchange(response)

    assert exchange.presentation_status is status
    assert exchange.presentation_document is None


def test_presentation_and_revision_presence_must_agree() -> None:
    absent = _response()
    absent.presentation_revision = "sha256:" + ("a" * 64)
    explicitly_empty = _response()
    explicitly_empty.presentation_revision = ""
    present = _presentation_response()
    present.ClearField("presentation_revision")

    assert (
        validate_manifest_exchange(absent).presentation_status
        is PresentationValidationStatus.INVALID
    )
    assert (
        validate_manifest_exchange(explicitly_empty).presentation_status
        is PresentationValidationStatus.INVALID
    )
    assert (
        validate_manifest_exchange(present).presentation_status
        is PresentationValidationStatus.INVALID
    )


def test_presentation_revision_mismatch_falls_back() -> None:
    response = _presentation_response()
    response.presentation_revision = "sha256:" + ("0" * 64)

    exchange = validate_manifest_exchange(response)

    assert exchange.presentation_status is PresentationValidationStatus.INVALID


def test_presentation_revision_is_isolated_and_bound_to_manifest() -> None:
    response = _presentation_response()
    original_manifest_revision = response.manifest_revision
    original_presentation_revision = response.presentation_revision

    response.presentation.provider.summary = "A different summary."
    _refresh_presentation_revision(response)

    assert response.manifest_revision == original_manifest_revision
    assert response.presentation_revision != original_presentation_revision
    assert (
        validate_manifest_exchange(response).presentation_status
        is PresentationValidationStatus.ACCEPTED
    )

    presentation_revision = response.presentation_revision
    response.manifest.display_name = "Renamed Git Provider"
    _refresh_manifest_revision(response)
    _refresh_presentation_revision(response)

    assert response.manifest_revision != original_manifest_revision
    assert response.presentation_revision != presentation_revision
    assert (
        validate_manifest_exchange(response).presentation_status
        is PresentationValidationStatus.ACCEPTED
    )


def test_presentation_key_validates_the_complete_revision_identity() -> None:
    response = _presentation_response()

    key = validate_presentation_key(
        response.provider_instance_id,
        response.manifest_revision,
        response.presentation.presentation_schema_version,
        response.presentation_revision,
    )

    assert str(key.provider_instance_id) == response.provider_instance_id
    assert key.manifest_revision == response.manifest_revision
    assert key.schema_version == contract.PRESENTATION_SCHEMA_VERSION
    assert key.revision == response.presentation_revision


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("provider", "not-a-uuid", "provider identity"),
        ("manifest", "not-a-revision", "manifest revision"),
        ("schema", 2, "schema version"),
        ("presentation", "not-a-revision", "revision is invalid"),
    ],
)
def test_presentation_key_rejects_invalid_identity_parts(
    field: str,
    value: str | int,
    message: str,
) -> None:
    response = _presentation_response()
    arguments: dict[str, str | int] = {
        "provider": response.provider_instance_id,
        "manifest": response.manifest_revision,
        "schema": response.presentation.presentation_schema_version,
        "presentation": response.presentation_revision,
    }
    arguments[field] = value

    with pytest.raises(ManifestValidationError, match=message):
        validate_presentation_key(
            str(arguments["provider"]),
            str(arguments["manifest"]),
            int(arguments["schema"]),
            str(arguments["presentation"]),
        )


def test_presentation_revision_requires_a_manifest_revision() -> None:
    response = _presentation_response()

    with pytest.raises(ManifestValidationError, match="manifest revision"):
        compute_presentation_revision(
            _project(response.presentation),
            "not-a-revision",
            response.provider_instance_id,
        )


def test_public_presentation_validator_projects_its_own_message() -> None:
    response = _presentation_response()
    manifest = _project(response.manifest)

    document = validate_presentation_document(
        response.presentation,
        manifest,
    )

    assert document == canonical_presentation_bytes(
        _project(response.presentation)
    )


def test_capability_groups_are_optional() -> None:
    response = _presentation_response()
    response.presentation.provider.ClearField("groups")
    for view in response.presentation.operations.values():
        view.group_id = ""
    for view in response.presentation.triggers.values():
        view.group_id = ""
    _refresh_presentation_revision(response)

    exchange = validate_manifest_exchange(response)

    assert (
        exchange.presentation_status is PresentationValidationStatus.ACCEPTED
    )


@pytest.mark.parametrize("collection", ["operations", "triggers"])
def test_views_cannot_name_undeclared_capabilities(collection: str) -> None:
    response = _presentation_response()
    views = getattr(response.presentation, collection)
    declared_identifier = next(iter(views))
    views["example.invalid/not_declared@1"].CopyFrom(
        views[declared_identifier]
    )

    with pytest.raises(
        ManifestValidationError,
        match=f"{collection[:-1]} view does not name a declared",
    ):
        _validate_presentation(response)


def test_view_group_reference_must_resolve() -> None:
    response = _presentation_response()
    response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ].group_id = "missing"

    with pytest.raises(ManifestValidationError, match="group reference"):
        _validate_presentation(response)


def test_capability_group_ids_must_be_unique() -> None:
    response = _presentation_response()
    duplicate = response.presentation.provider.groups.add()
    duplicate.CopyFrom(response.presentation.provider.groups[0])

    with pytest.raises(ManifestValidationError, match="group IDs"):
        _validate_presentation(response)


def test_schema_view_pointer_must_resolve_in_its_own_schema() -> None:
    response = _presentation_response()
    operation = response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ]
    operation.input.field_order[0] = "/properties/commit"

    with pytest.raises(ManifestValidationError, match="does not resolve"):
        _validate_presentation(response)


def test_schema_view_pointer_must_name_a_field() -> None:
    response = _presentation_response()
    operation = response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ]
    operation.input.field_order[0] = "/properties"

    with pytest.raises(ManifestValidationError, match="schema field"):
        _validate_presentation(response)


def test_field_may_belong_to_only_one_visual_group() -> None:
    response = _presentation_response()
    groups = response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ].input.groups
    duplicate = groups.add(
        id="more-credentials",
        label="More credentials",
        description="Duplicate placement.",
    )
    duplicate.fields.append("/properties/token")

    with pytest.raises(ManifestValidationError, match="at most one"):
        _validate_presentation(response)


def test_field_group_ids_must_be_unique() -> None:
    response = _presentation_response()
    groups = response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ].input.groups
    duplicate = groups.add(
        id="credentials",
        label="More credentials",
        description="Duplicate identifier.",
    )
    duplicate.fields.append("/properties/repository")

    with pytest.raises(ManifestValidationError, match="group IDs"):
        _validate_presentation(response)


def test_schema_view_follows_a_local_field_reference() -> None:
    response = _presentation_response()
    schema = response.manifest.operations[
        "stateforge.git/reference.resolve@1"
    ].input_schema
    schema.update(
        {
            "$defs": {"repository": {"type": "string"}},
            "properties": {
                "repository": {"$ref": "#/$defs/repository"},
                "depth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
                "token": {"type": "string", "writeOnly": True},
            },
        }
    )

    _validate_presentation(response)


@pytest.mark.parametrize(
    ("reference", "message"),
    [
        ("https://example.invalid/schema", "reference is invalid"),
        ("#/properties/repository", "cyclic field schema reference"),
        ("#/$defs/not-a-schema", "must name a schema"),
    ],
)
def test_schema_view_rejects_invalid_field_references(
    reference: str,
    message: str,
) -> None:
    response = _presentation_response()
    schema = response.manifest.operations[
        "stateforge.git/reference.resolve@1"
    ].input_schema
    schema.update(
        {
            "$defs": {"not-a-schema": "value"},
            "properties": {
                "repository": {"$ref": reference},
                "depth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
                "token": {"type": "string", "writeOnly": True},
            },
        }
    )

    with pytest.raises(ManifestValidationError, match=message):
        _validate_presentation(response)


def test_schema_view_resolves_fields_nested_in_schema_arrays() -> None:
    response = _presentation_response()
    schema = response.manifest.operations[
        "stateforge.git/reference.resolve@1"
    ].input_schema
    schema.Clear()
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "allOf": [{"properties": {"repository": {"type": "string"}}}],
        }
    )
    view = response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ].input
    field = manifest_pb2.FieldView()
    field.CopyFrom(view.fields["/properties/repository"])
    view.ClearField("field_order")
    view.field_order.append("/allOf/0/properties/repository")
    view.ClearField("groups")
    view.ClearField("fields")
    view.fields["/allOf/0/properties/repository"].CopyFrom(field)

    _validate_presentation(response)


@pytest.mark.parametrize(
    ("field", "widget", "message"),
    [
        ("repository", manifest_pb2.INPUT_WIDGET_NUMBER, "schema type"),
        ("repository", manifest_pb2.INPUT_WIDGET_SECRET, "write-only"),
        ("repository", manifest_pb2.INPUT_WIDGET_SELECT, "schema enum"),
        ("depth", manifest_pb2.INPUT_WIDGET_DATE_TIME, "schema type"),
    ],
)
def test_input_widgets_must_match_authoritative_schema(
    field: str,
    widget: int,
    message: str,
) -> None:
    response = _presentation_response()
    view = response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ].input.fields[f"/properties/{field}"]
    view.widget = widget

    with pytest.raises(ManifestValidationError, match=message):
        _validate_presentation(response)


def test_slider_requires_authoritative_bounds() -> None:
    response = _presentation_response()
    depth = (
        response.manifest.operations["stateforge.git/reference.resolve@1"]
        .input_schema.fields["properties"]
        .struct_value.fields["depth"]
        .struct_value
    )
    del depth.fields["minimum"]

    with pytest.raises(ManifestValidationError, match="minimum and maximum"):
        _validate_presentation(response)


@pytest.mark.parametrize(
    ("schema", "widget", "display"),
    [
        ({"type": "boolean"}, manifest_pb2.INPUT_WIDGET_CHECKBOX, 0),
        (
            {"type": "string", "enum": ["main", "develop"]},
            manifest_pb2.INPUT_WIDGET_SELECT,
            0,
        ),
        (
            {"type": "string", "enum": ["main", "develop"]},
            manifest_pb2.INPUT_WIDGET_RADIO,
            0,
        ),
        (
            {"type": "string", "format": "date-time"},
            manifest_pb2.INPUT_WIDGET_DATE_TIME,
            manifest_pb2.DISPLAY_STYLE_DATE_TIME,
        ),
        (
            {"type": ["object", "null"]},
            manifest_pb2.INPUT_WIDGET_JSON,
            manifest_pb2.DISPLAY_STYLE_JSON,
        ),
    ],
)
def test_supported_field_preferences_follow_the_schema(
    schema: dict[str, object],
    widget: int,
    display: int,
) -> None:
    response = _presentation_response()
    field_schema = (
        response.manifest.operations["stateforge.git/reference.resolve@1"]
        .input_schema.fields["properties"]
        .struct_value.fields["repository"]
        .struct_value
    )
    field_schema.Clear()
    field_schema.update(schema)
    field_view = response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ].input.fields["/properties/repository"]
    field_view.widget = widget
    field_view.display = display

    _validate_presentation(response)


@pytest.mark.parametrize("preference", ["widget", "placeholder"])
def test_output_fields_cannot_declare_input_preferences(
    preference: str,
) -> None:
    response = _presentation_response()
    view = response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ].result.fields["/properties/commit"]
    if preference == "widget":
        view.widget = manifest_pb2.INPUT_WIDGET_TEXT
    else:
        view.placeholder = "not permitted"

    with pytest.raises(ManifestValidationError, match="output fields"):
        _validate_presentation(response)


@pytest.mark.parametrize(
    ("field", "display"),
    [
        ("commit", manifest_pb2.DISPLAY_STYLE_METRIC),
        ("changed", manifest_pb2.DISPLAY_STYLE_CODE),
        ("changed", manifest_pb2.DISPLAY_STYLE_TABLE),
    ],
)
def test_display_preferences_must_match_authoritative_schema(
    field: str,
    display: int,
) -> None:
    response = _presentation_response()
    view = response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ].result.fields[f"/properties/{field}"]
    view.display = display

    with pytest.raises(ManifestValidationError, match="schema type"):
        _validate_presentation(response)


def test_bounded_static_png_asset_is_accepted() -> None:
    response = _presentation_response()
    _replace_provider_icon(
        response,
        content=_png(2, 3),
        media_type="image/png",
        width=2,
        height=3,
    )
    _refresh_presentation_revision(response)

    exchange = validate_manifest_exchange(response)

    assert (
        exchange.presentation_status is PresentationValidationStatus.ACCEPTED
    )


def test_asset_reference_must_resolve() -> None:
    response = _presentation_response()
    del response.presentation.assets[
        response.presentation.provider.icon_asset_digest
    ]

    with pytest.raises(ManifestValidationError, match="reference is missing"):
        _validate_presentation(response)


def test_unreferenced_assets_are_rejected() -> None:
    response = _presentation_response()
    response.presentation.provider.icon_asset_digest = ""

    with pytest.raises(ManifestValidationError, match="unreferenced asset"):
        _validate_presentation(response)


def test_asset_digest_must_match_exact_bytes() -> None:
    response = _presentation_response()
    digest = response.presentation.provider.icon_asset_digest
    response.presentation.assets[digest].content += b"changed"

    with pytest.raises(ManifestValidationError, match="digest mismatch"):
        _validate_presentation(response)


def test_asset_size_limit_is_enforced() -> None:
    response = _presentation_response()
    _replace_provider_icon(
        response,
        content=b"x" * (contract.MAX_PRESENTATION_ASSET_BYTES + 1),
        media_type="image/png",
        width=1,
        height=1,
    )

    with pytest.raises(ManifestValidationError, match="byte limit"):
        _validate_presentation(response)


def test_aggregate_asset_size_limit_is_enforced() -> None:
    response = _presentation_response()
    response.presentation.ClearField("assets")
    references: list[str] = []
    for index in range(5):
        content = bytes([index]) + (
            b"x" * (contract.MAX_PRESENTATION_ASSET_BYTES - 1)
        )
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        response.presentation.assets[digest].CopyFrom(
            manifest_pb2.PresentationAsset(
                media_type="image/svg+xml",
                content=content,
                width=1,
                height=1,
                alt_text="Visual",
            )
        )
        references.append(digest)
    response.presentation.provider.icon_asset_digest = references[0]
    response.presentation.provider.banner_asset_digest = references[1]
    response.presentation.provider.groups[0].icon_asset_digest = references[2]
    response.presentation.operations[
        "stateforge.git/reference.resolve@1"
    ].icon_asset_digest = references[3]
    response.presentation.triggers[
        "stateforge.git/reference.changed@1"
    ].icon_asset_digest = references[4]

    with pytest.raises(ManifestValidationError, match="aggregate asset"):
        _validate_presentation(response)


def test_raster_media_type_and_dimensions_must_match_content() -> None:
    response = _presentation_response()
    _replace_provider_icon(
        response,
        content=_png(),
        media_type="image/png",
        width=2,
        height=1,
    )

    with pytest.raises(ManifestValidationError, match="dimensions"):
        _validate_presentation(response)

    response = _presentation_response()
    _replace_provider_icon(
        response,
        content=b"not a PNG",
        media_type="image/png",
        width=1,
        height=1,
    )
    with pytest.raises(ManifestValidationError, match="invalid PNG"):
        _validate_presentation(response)


def test_png_crc_and_chunk_allowlist_are_enforced() -> None:
    response = _presentation_response()
    invalid_crc = bytearray(_png())
    invalid_crc[-1] ^= 0xFF
    _replace_provider_icon(
        response,
        content=bytes(invalid_crc),
        media_type="image/png",
        width=1,
        height=1,
    )
    with pytest.raises(ManifestValidationError, match="invalid PNG"):
        _validate_presentation(response)


@pytest.mark.parametrize(
    "content",
    [
        _png(0, 1),
        _png()[:33] + _png()[8:33] + _png()[33:],
        _png()[:33] + _png_chunk(b"IEND", b""),
        _png()[:-12],
    ],
)
def test_png_structure_is_enforced(content: bytes) -> None:
    response = _presentation_response()
    _replace_provider_icon(
        response,
        content=content,
        media_type="image/png",
        width=1,
        height=1,
    )

    with pytest.raises(ManifestValidationError, match="invalid PNG"):
        _validate_presentation(response)

    response = _presentation_response()
    png = _png()
    unsafe_chunk = b"\x00\x00\x00\x00tEXt" + struct.pack(
        ">I", zlib.crc32(b"tEXt") & 0xFFFFFFFF
    )
    content = png[:-12] + unsafe_chunk + png[-12:]
    _replace_provider_icon(
        response,
        content=content,
        media_type="image/png",
        width=1,
        height=1,
    )
    with pytest.raises(ManifestValidationError, match="invalid PNG"):
        _validate_presentation(response)


@pytest.mark.parametrize(
    "content",
    [
        b"<svg",
        b"<svg></svg>",
        b'<svg viewBox="0 0 1 1"><script>alert(1)</script></svg>',
        b'<svg viewBox="0 0 1 1"><image href="https://example.invalid/x"/></svg>',
        b'<svg viewBox="0 0 1 1" onload="alert(1)"></svg>',
        b'<!DOCTYPE svg [<!ENTITY x "secret">]><svg viewBox="0 0 1 1"/>',
        b'<svg viewBox="0 0 1 1"><rect fill="url(https://example.invalid/x)"/></svg>',
        b'<svg viewBox="0 0 1 1"><rect fill="data:image/png;base64,x"/></svg>',
    ],
)
def test_svg_executable_or_external_content_is_rejected_without_echo(
    content: bytes,
) -> None:
    response = _presentation_response()
    _replace_provider_icon(
        response,
        content=content,
        media_type="image/svg+xml",
        width=1,
        height=1,
    )

    with pytest.raises(ManifestValidationError) as error:
        _validate_presentation(response)

    assert content.decode() not in str(error.value)


def test_media_allowlist_is_enforced() -> None:
    response = _presentation_response()
    digest = response.presentation.provider.icon_asset_digest
    response.presentation.assets[digest].media_type = "text/html"

    with pytest.raises(ManifestValidationError, match="enum constraint"):
        _validate_presentation(response)


def test_public_contract_validator_uses_the_packaged_schema() -> None:
    validator = contract_validator("schemaDocument")

    validator.validate(_schema())
    assert not validator.is_valid({"type": "unknown"})


def test_rejects_revision_mismatch() -> None:
    response = _response()
    response.manifest_revision = "sha256:" + ("0" * 64)

    with pytest.raises(ManifestValidationError, match="revision mismatch"):
        validate_manifest_response(response)


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef"])
def test_rejects_remote_schema_references_without_echoing_them(
    keyword: str,
) -> None:
    reference = "https://sensitive.invalid/schema"
    document = _schema(properties={"value": {keyword: reference}})

    with pytest.raises(ManifestValidationError) as error:
        validate_schema(document, "manifest.configurationSchema")

    assert reference not in str(error.value)


@pytest.mark.parametrize("keyword", ["default", "examples", "const", "enum"])
def test_rejects_indirect_secret_values_without_echoing_them(
    keyword: str,
) -> None:
    secret = "sensitive-canary-never-in-errors"  # noqa: S105
    annotation = [secret] if keyword in {"examples", "enum"} else secret
    document = _schema(
        properties={"token": {"$ref": "#/$defs/secret"}},
        **{
            "$defs": {
                "secret": {
                    "type": "string",
                    "writeOnly": True,
                    keyword: annotation,
                }
            }
        },
    )

    with pytest.raises(ManifestValidationError) as error:
        validate_schema(document, "manifest.configurationSchema")

    assert secret not in str(error.value)


def test_local_reference_propagates_write_only_secret_semantics() -> None:
    secret = "sensitive-canary-never-in-errors"  # noqa: S105
    document = _schema(
        properties={
            "token": {
                "writeOnly": True,
                "$ref": "#/$defs/tokenValue",
            }
        },
        **{
            "$defs": {
                "tokenValue": {
                    "type": "string",
                    "default": secret,
                }
            }
        },
    )

    with pytest.raises(ManifestValidationError) as error:
        validate_schema(document, "manifest.configurationSchema")

    assert secret not in str(error.value)


def test_rejects_nested_schema_dialect_changes() -> None:
    document = _schema(
        properties={
            "value": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "string",
            }
        }
    )

    with pytest.raises(ManifestValidationError, match="nested schema dialect"):
        validate_schema(document, "manifest.configurationSchema")


def test_enforces_contract_and_tighter_runtime_resource_limits() -> None:
    with pytest.raises(ValueError, match="max_json_nodes"):
        ManifestValidationLimits(max_json_nodes=contract.MAX_JSON_NODES + 1)
    with pytest.raises(ValueError, match="max_schema_nodes"):
        ManifestValidationLimits(
            max_schema_nodes=contract.MAX_SCHEMA_NODES + 1
        )

    limits = ManifestValidationLimits(max_json_nodes=2, max_schema_nodes=1)
    with pytest.raises(ManifestValidationError, match="resource limit"):
        bounded_json(
            {"first": None, "second": None},
            "manifest",
            limits=limits,
        )
    schema_limits = ManifestValidationLimits(
        max_json_nodes=100,
        max_schema_nodes=1,
    )
    with pytest.raises(ManifestValidationError, match="schema node limit"):
        validate_schema(
            _schema(properties={"value": {"type": "string"}}),
            "manifest.configurationSchema",
            limits=schema_limits,
        )


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), 2**53 + 1, "\ud800"],
)
def test_rejects_non_interoperable_canonical_json(value: object) -> None:
    with pytest.raises(ManifestValidationError):
        canonical_bytes({"value": value})


def test_validates_manifest_revision_cache_keys() -> None:
    response = _response()

    key = validate_manifest_key(
        response.provider_instance_id,
        response.manifest_schema_version,
        response.manifest_revision,
    )

    assert str(key.provider_instance_id) == response.provider_instance_id
    assert key.schema_version == response.manifest_schema_version
    assert key.revision == response.manifest_revision

    invalid = copy.deepcopy(response)
    invalid.manifest_revision = "not-a-revision"
    with pytest.raises(ManifestValidationError, match="revision"):
        validate_manifest_key(
            invalid.provider_instance_id,
            invalid.manifest_schema_version,
            invalid.manifest_revision,
        )


@pytest.mark.parametrize(
    ("provider_instance_id", "schema_version", "message"),
    [
        ("not-a-uuid", 1, "identity"),
        ("7F7DB7D8-68B4-4F71-9769-065B5C4F941C", 1, "identity"),
        ("7f7db7d8-68b4-4f71-9769-065b5c4f941c", 0, "schema version"),
        ("7f7db7d8-68b4-4f71-9769-065b5c4f941c", True, "schema version"),
    ],
)
def test_manifest_cache_key_rejects_invalid_identity_or_version(
    provider_instance_id: str,
    schema_version: int,
    message: str,
) -> None:
    with pytest.raises(ManifestValidationError, match=message):
        validate_manifest_key(
            provider_instance_id,
            schema_version,
            "sha256:" + ("a" * 64),
        )
