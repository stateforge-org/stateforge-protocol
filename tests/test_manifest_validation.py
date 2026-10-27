"""Executable semantic-validation evidence for Provider Manifest v1."""

import copy
import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest
from google.protobuf import struct_pb2
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


def _png_with_image_data(
    image_data: bytes,
    *,
    width: int = 1,
    height: int = 1,
    interlace_method: int = 0,
    split_at: int | None = None,
) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    header = header[:-1] + bytes([interlace_method])
    if split_at is None:
        data_chunks = (_png_chunk(b"IDAT", image_data),)
    else:
        data_chunks = (
            _png_chunk(b"IDAT", image_data[:split_at]),
            _png_chunk(b"IDAT", image_data[split_at:]),
        )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + b"".join(data_chunks)
        + _png_chunk(b"IEND", b"")
    )


def _png(width: int = 1, height: int = 1) -> bytes:
    pixels = b"".join(
        b"\x00" + (b"\x00\x00\x00\x00" * width) for _ in range(height)
    )
    return _png_with_image_data(
        zlib.compress(pixels),
        width=width,
        height=height,
    )


def _replace_provider_icon(
    response: manifest_pb2.GetManifestResponse,
    *,
    content: bytes,
    media_type: str,
    width: int,
    height: int,
) -> str:
    image = _provider_image(response)
    old_digest = image.asset_bindings["source"]
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
    image.asset_bindings["source"] = digest
    return digest


def _provider_image(
    response: manifest_pb2.GetManifestResponse,
) -> manifest_pb2.ComponentNode:
    return response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root.children[0]


def _operation_root(
    response: manifest_pb2.GetManifestResponse,
    surface: str,
) -> manifest_pb2.ComponentNode:
    return (
        response.presentation.operations["stateforge.git/reference.resolve@1"]
        .surfaces[surface]
        .root
    )


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
    response.presentation.ClearField("renderer_requirements")
    _refresh_presentation_revision(response)

    exchange = validate_manifest_exchange(response)

    assert (
        exchange.presentation_status is PresentationValidationStatus.ACCEPTED
    )
    assert json.loads(exchange.presentation_document or b"") == {
        "assets": {},
        "operations": {},
        "presentationSchemaVersion": 1,
        "rendererRequirements": {},
        "triggers": {},
    }


def test_invalid_presentation_falls_back_without_rejecting_manifest() -> None:
    response = _presentation_response()
    _operation_root(response, contract.OPERATION_REQUEST_SURFACE).bindings[
        "schema"
    ].source_identifier = contract.PROVIDER_RUNTIME_BINDING
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

    response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root.properties.update({"gap": "compact"})
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


@pytest.mark.parametrize("collection", ["operations", "triggers"])
def test_targets_cannot_name_undeclared_capabilities(collection: str) -> None:
    response = _presentation_response()
    targets = getattr(response.presentation, collection)
    declared_identifier = next(iter(targets))
    targets["example.invalid/not_declared@1"].CopyFrom(
        targets[declared_identifier]
    )

    with pytest.raises(
        ManifestValidationError,
        match=f"{collection[:-1]} target does not name a declared",
    ):
        _validate_presentation(response)


def test_surface_must_belong_to_its_target_kind() -> None:
    response = _presentation_response()
    target = response.presentation.provider
    target.surfaces[contract.OPERATION_REQUEST_SURFACE].CopyFrom(
        target.surfaces[contract.PROVIDER_OVERVIEW_SURFACE]
    )

    with pytest.raises(ManifestValidationError, match="provider targets"):
        _validate_presentation(response)


def test_surface_binding_source_must_be_available() -> None:
    response = _presentation_response()
    _operation_root(response, contract.OPERATION_REQUEST_SURFACE).bindings[
        "schema"
    ].source_identifier = contract.OPERATION_RESULT_VALUE_BINDING

    with pytest.raises(ManifestValidationError, match="unavailable"):
        _validate_presentation(response)


def test_raw_operation_request_values_are_not_presentation_sources() -> None:
    response = _presentation_response()
    result = _operation_root(
        response, contract.OPERATION_RESULT_SURFACE
    ).fallback
    result.bindings[
        "secret"
    ].source_identifier = "stateforge.binding/operation.request.value@1"
    result.bindings["secret"].pointer = "/token"

    with pytest.raises(ManifestValidationError, match="unavailable"):
        _validate_presentation(response)


def test_public_request_projection_is_available_across_lifecycle() -> None:
    expected = contract.OPERATION_REQUEST_PUBLIC_VALUE_BINDING

    for surface in (
        contract.OPERATION_REQUEST_SURFACE,
        contract.OPERATION_RUN_SURFACE,
        contract.OPERATION_RESULT_SURFACE,
    ):
        assert expected in contract.SURFACE_BINDING_SOURCES[surface]

    assert all(
        "stateforge.binding/operation.request.value@1" not in sources
        for sources in contract.SURFACE_BINDING_SOURCES.values()
    )


def test_core_component_catalog_is_explicit() -> None:
    response = _presentation_response()
    response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root.component_identifier = "stateforge.ui/layout.unknown@1"

    with pytest.raises(ManifestValidationError, match="unknown core"):
        _validate_presentation(response)


def test_core_action_is_rejected_outside_its_operation_surface() -> None:
    response = _presentation_response()
    root = response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root
    root.component_identifier = "stateforge.ui/action.operation_submit@1"

    with pytest.raises(ManifestValidationError, match="unavailable"):
        _validate_presentation(response)


def test_core_leaf_component_rejects_children() -> None:
    response = _presentation_response()
    image = _provider_image(response)
    child = image.children.add(
        component_identifier="stateforge.ui/content.text@1"
    )
    child.properties.CopyFrom(struct_pb2.Struct())

    with pytest.raises(ManifestValidationError, match="child contract"):
        _validate_presentation(response)


def test_core_component_requires_its_binding_slots() -> None:
    response = _presentation_response()
    event = next(iter(response.presentation.triggers.values()))
    event.surfaces[contract.TRIGGER_EVENT_SURFACE].root.ClearField("bindings")

    with pytest.raises(ManifestValidationError, match="required binding"):
        _validate_presentation(response)


def test_core_component_rejects_unknown_binding_slots() -> None:
    response = _presentation_response()
    image = _provider_image(response)
    image.bindings[
        "value"
    ].source_identifier = contract.PROVIDER_MANIFEST_BINDING

    with pytest.raises(ManifestValidationError, match="binding slot"):
        _validate_presentation(response)


def test_core_input_schema_slot_rejects_value_sources() -> None:
    response = _presentation_response()
    request = _operation_root(response, contract.OPERATION_REQUEST_SURFACE)
    request.bindings[
        "schema"
    ].source_identifier = contract.OPERATION_REQUEST_PUBLIC_VALUE_BINDING

    with pytest.raises(ManifestValidationError, match="component slot"):
        _validate_presentation(response)


def test_core_media_component_requires_its_asset_slot() -> None:
    response = _presentation_response()
    _provider_image(response).ClearField("asset_bindings")

    with pytest.raises(ManifestValidationError, match="required asset"):
        _validate_presentation(response)


def test_core_component_cannot_declare_a_fallback() -> None:
    response = _presentation_response()
    root = response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root
    root.fallback.component_identifier = "stateforge.ui/content.text@1"
    root.fallback.properties.CopyFrom(struct_pb2.Struct())

    with pytest.raises(ManifestValidationError, match="cannot declare"):
        _validate_presentation(response)


def test_secret_input_is_part_of_the_portable_core_catalog() -> None:
    secret = contract.CORE_COMPONENT_CONTRACTS["stateforge.ui/input.secret@1"]

    assert secret.required_bindings == frozenset({"schema"})
    assert "value" not in secret.optional_bindings


@pytest.mark.parametrize(
    ("identifier", "required_bindings"),
    [
        ("stateforge.ui/data.table@1", {"rows"}),
        ("stateforge.ui/data.diff@1", {"before", "after"}),
        ("stateforge.ui/data.log@1", {"entries"}),
        ("stateforge.ui/status.timeline@1", {"events"}),
        ("stateforge.ui/data.chart@1", {"series"}),
        ("stateforge.ui/data.topology@1", {"nodes", "edges"}),
        ("stateforge.ui/data.artifacts@1", {"items"}),
    ],
)
def test_core_data_components_have_semantic_binding_slots(
    identifier: str,
    required_bindings: set[str],
) -> None:
    component = contract.CORE_COMPONENT_CONTRACTS[identifier]

    assert component.required_bindings == frozenset(required_bindings)


def test_custom_component_requires_renderer_metadata() -> None:
    response = _presentation_response()
    del response.presentation.renderer_requirements["example.git"]

    with pytest.raises(ManifestValidationError, match="renderer requirement"):
        _validate_presentation(response)


def test_custom_component_requires_core_fallback() -> None:
    response = _presentation_response()
    _operation_root(response, contract.OPERATION_RESULT_SURFACE).ClearField(
        "fallback"
    )

    with pytest.raises(ManifestValidationError, match="core fallback"):
        _validate_presentation(response)


def test_custom_component_fallback_cannot_require_an_extension() -> None:
    response = _presentation_response()
    _operation_root(
        response, contract.OPERATION_RESULT_SURFACE
    ).fallback.component_identifier = "example.git/data.commit_graph@1"

    with pytest.raises(ManifestValidationError, match="core components"):
        _validate_presentation(response)


def test_renderer_requirements_cannot_be_unreferenced() -> None:
    response = _presentation_response()
    response.presentation.renderer_requirements["example.widget"].CopyFrom(
        response.presentation.renderer_requirements["example.git"]
    )
    requirement = response.presentation.renderer_requirements["example.widget"]
    requirement.extension_identifier = "example.widget/renderer@1"

    with pytest.raises(ManifestValidationError, match="exactly match"):
        _validate_presentation(response)


def test_renderer_extension_must_share_component_namespace() -> None:
    response = _presentation_response()
    response.presentation.renderer_requirements[
        "example.git"
    ].extension_identifier = "example.widget/renderer@1"

    with pytest.raises(ManifestValidationError, match="namespace"):
        _validate_presentation(response)


@pytest.mark.parametrize(
    "identifier",
    [
        "stateforge.git/data.commit_graph@1",
        "stateforge.ui.custom/data.commit_graph@1",
    ],
)
def test_custom_components_cannot_claim_stateforge_namespaces(
    identifier: str,
) -> None:
    response = _presentation_response()
    _operation_root(
        response, contract.OPERATION_RESULT_SURFACE
    ).component_identifier = identifier

    with pytest.raises(ManifestValidationError, match="StateForge-owned"):
        _validate_presentation(response)


def test_renderer_requirements_cannot_claim_stateforge_namespaces() -> None:
    response = _presentation_response()
    reserved = response.presentation.renderer_requirements["stateforge.git"]
    reserved.CopyFrom(
        response.presentation.renderer_requirements["example.git"]
    )
    reserved.extension_identifier = "stateforge.git/renderer@1"
    del response.presentation.renderer_requirements["example.git"]

    with pytest.raises(ManifestValidationError, match="StateForge-owned"):
        _validate_presentation(response)


def test_repetition_scope_is_available_to_component_bindings() -> None:
    response = _presentation_response()
    root = response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root
    repeated = root.children.add(
        component_identifier="stateforge.ui/data.table@1"
    )
    repeated.properties.update({"title": "Runtime items"})
    repeated.repeat.collection.CopyFrom(
        manifest_pb2.DataBinding(
            source_identifier=contract.PROVIDER_RUNTIME_BINDING,
            pointer="/items",
        )
    )
    repeated.repeat.item_scope = "row"
    repeated.repeat.max_items = 100
    repeated.bindings["rows"].CopyFrom(
        manifest_pb2.DataBinding(
            source_identifier=contract.REPETITION_ITEM_BINDING,
            pointer="/name",
            scope="row",
        )
    )

    _validate_presentation(response)


def test_repetition_item_binding_requires_an_active_scope() -> None:
    response = _presentation_response()
    root = response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root
    root.bindings["item"].CopyFrom(
        manifest_pb2.DataBinding(
            source_identifier=contract.REPETITION_ITEM_BINDING,
            scope="missing",
        )
    )

    with pytest.raises(ManifestValidationError, match="active scope"):
        _validate_presentation(response)


def test_non_repetition_binding_cannot_claim_a_scope() -> None:
    response = _presentation_response()
    _operation_root(response, contract.OPERATION_REQUEST_SURFACE).bindings[
        "schema"
    ].scope = "row"

    with pytest.raises(ManifestValidationError, match="may name a scope"):
        _validate_presentation(response)


@pytest.mark.parametrize(
    ("operator", "with_value", "message"),
    [
        (
            manifest_pb2.CONDITION_OPERATOR_EXISTS,
            True,
            "cannot declare a value",
        ),
        (
            manifest_pb2.CONDITION_OPERATOR_EQUALS,
            False,
            "requires a value",
        ),
    ],
)
def test_condition_value_presence_matches_operator(
    operator: int,
    with_value: bool,
    message: str,
) -> None:
    response = _presentation_response()
    root = response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root
    root.condition.binding.CopyFrom(
        manifest_pb2.DataBinding(
            source_identifier=contract.PROVIDER_RUNTIME_BINDING,
            pointer="/available",
        )
    )
    root.condition.operator = operator
    if with_value:
        root.condition.value.bool_value = True

    with pytest.raises(ManifestValidationError, match=message):
        _validate_presentation(response)


def test_component_properties_have_an_independent_byte_limit() -> None:
    response = _presentation_response()
    response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root.properties.update(
        {"content": "x" * contract.MAX_COMPONENT_PROPERTIES_BYTES}
    )

    with pytest.raises(ManifestValidationError, match="properties limit"):
        _validate_presentation(response)


def test_component_tree_depth_is_bounded() -> None:
    response = _presentation_response()
    node = response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root
    for depth in range(contract.MAX_PRESENTATION_COMPONENT_DEPTH):
        node = node.children.add(
            component_identifier="stateforge.ui/layout.section@1"
        )
        node.properties.update({"depth": depth})

    with pytest.raises(ManifestValidationError, match="depth limit"):
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
        _provider_image(response).asset_bindings["source"]
    ]

    with pytest.raises(ManifestValidationError, match="reference is missing"):
        _validate_presentation(response)


def test_unreferenced_assets_are_rejected() -> None:
    response = _presentation_response()
    content = _png()
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    response.presentation.assets[digest].CopyFrom(
        manifest_pb2.PresentationAsset(
            media_type="image/png",
            content=content,
            width=1,
            height=1,
            alt_text="Unreferenced image",
        )
    )

    with pytest.raises(ManifestValidationError, match="unreferenced asset"):
        _validate_presentation(response)


def test_asset_digest_must_match_exact_bytes() -> None:
    response = _presentation_response()
    digest = _provider_image(response).asset_bindings["source"]
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
    root = response.presentation.provider.surfaces[
        contract.PROVIDER_OVERVIEW_SURFACE
    ].root
    root.ClearField("children")
    for index, digest in enumerate(references):
        image = root.children.add(
            component_identifier="stateforge.ui/media.image@1"
        )
        image.properties.update({"index": index})
        image.asset_bindings["source"] = digest

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
    "image_data",
    [
        b"not a zlib stream",
        zlib.compress(b"\x00\x00\x00\x00\x00")[:-1],
        zlib.compress(b"\x00\x00\x00\x00\x00") + b"trailing",
        zlib.compress(b"\x00\x00\x00\x00\x00\x00"),
        zlib.compress(b"\x05\x00\x00\x00\x00"),
    ],
)
def test_png_image_data_must_decode_to_exact_scanlines(
    image_data: bytes,
) -> None:
    response = _presentation_response()
    _replace_provider_icon(
        response,
        content=_png_with_image_data(image_data),
        media_type="image/png",
        width=1,
        height=1,
    )

    with pytest.raises(ManifestValidationError, match="invalid PNG"):
        _validate_presentation(response)


def test_png_consecutive_idat_chunks_form_one_valid_stream() -> None:
    response = _presentation_response()
    image_data = zlib.compress(b"\x00\x00\x00\x00\x00")
    _replace_provider_icon(
        response,
        content=_png_with_image_data(
            image_data,
            split_at=len(image_data) // 2,
        ),
        media_type="image/png",
        width=1,
        height=1,
    )

    _validate_presentation(response)


def test_png_adam7_scanline_layout_is_accepted() -> None:
    response = _presentation_response()
    _replace_provider_icon(
        response,
        content=_png_with_image_data(
            zlib.compress(b"\x00\x00\x00\x00\x00"),
            interlace_method=1,
        ),
        media_type="image/png",
        width=1,
        height=1,
    )

    _validate_presentation(response)


def test_png_decoded_size_is_bounded_before_decompression() -> None:
    response = _presentation_response()
    _replace_provider_icon(
        response,
        content=_png_with_image_data(
            zlib.compress(b""),
            width=contract.MAX_PRESENTATION_ASSET_DIMENSION,
            height=contract.MAX_PRESENTATION_ASSET_DIMENSION,
        ),
        media_type="image/png",
        width=contract.MAX_PRESENTATION_ASSET_DIMENSION,
        height=contract.MAX_PRESENTATION_ASSET_DIMENSION,
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
    digest = _provider_image(response).asset_bindings["source"]
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
