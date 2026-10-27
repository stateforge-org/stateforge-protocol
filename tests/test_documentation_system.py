"""Verify Protocol's shared documentation-system contract."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml
from mkdocs.config import load_config

ROOT = Path(__file__).resolve().parents[1]
THEME_REVISION = "0a1a0048acdc3a6683c6bb2a9bbbe1923b7e99c5"


def test_protocol_uses_the_shared_documentation_presentation() -> None:
    configuration = load_config(
        config_file=str(ROOT / "mkdocs.yml"),
        strict=True,
    )

    assert configuration.theme["name"] == "stateforge"
    assert configuration.repo_name == "stateforge-org/stateforge-protocol"
    assert configuration.repo_url == (
        "https://github.com/stateforge-org/stateforge-protocol"
    )

    plugin = configuration.plugins["stateforge"]
    assert dict(plugin.config) == {
        "component": "protocol",
        "accent": None,
        "documentation_version": "v0.1.0",
        "latest_version": "v0.1.0",
        "versions": [{"label": "v0.1.0", "url": "v0.1.0/"}],
        "historical_warning": True,
        "procedure_players": True,
        "entity_flows": True,
    }

    navigation = configuration.nav[0]["Protocol documentation"]
    assert navigation[0] == {"Home": "index.md"}
    assert "v0.1.0" in navigation[1]

    assert "pymdownx.highlight" in configuration.markdown_extensions
    assert "pymdownx.tabbed" in configuration.markdown_extensions
    assert configuration.extra["annotate"]["json"] == [".s2"]


def test_provider_presentation_guide_maps_components_to_surfaces() -> None:
    page = (
        ROOT / "docs/v0.1.0/procedures/provider-presentation.md"
    ).read_text(encoding="utf-8")
    configuration = load_config(
        config_file=str(ROOT / "mkdocs.yml"),
        strict=True,
    )
    version_navigation = configuration.nav[0]["Protocol documentation"][1][
        "v0.1.0"
    ]
    procedure_navigation = next(
        item["SFP procedures"]
        for item in version_navigation
        if isinstance(item, dict) and "SFP procedures" in item
    )

    assert {
        "Provider manifest exchange": [
            {
                "Contract and exchange": (
                    "v0.1.0/procedures/provider-manifest.md"
                )
            },
            {
                "Provider presentation": (
                    "v0.1.0/procedures/provider-presentation.md"
                )
            },
        ]
    } in procedure_navigation
    for contract_type in (
        "`PresentationTarget`",
        "`PresentationSurface`",
        "`ComponentNode`",
        "`DataBinding`",
        "`RendererRequirement`",
        "`PresentationAsset`",
    ):
        assert contract_type in page
    for surface in (
        "surface.provider.overview@1",
        "surface.operation.request@1",
        "surface.operation.run@1",
        "surface.operation.result@1",
        "surface.trigger.policy@1",
        "surface.trigger.event@1",
        "surface.evidence@1",
    ):
        assert surface in page
    assert "schema-derived interface" in page.lower()
    assert "active Control Plane skin" in page
    assert "No second SFP presentation RPC" in page
    assert "SF-AOP" in page


def test_documentation_home_orients_readers_to_the_protocol() -> None:
    home = (ROOT / "docs/index.md").read_text(encoding="utf-8")

    assert 'class="sf-docs-hero"' in home
    assert "A precise contract for local operations." in home
    assert "01 / DISCOVER" in home
    assert "02 / ESTABLISH" in home
    assert "03 / OPERATE" in home
    assert 'href="v0.1.0/"' in home
    assert "assets/images/stateforge-mark-black.svg" in home
    assert "assets/images/stateforge-mark.svg" in home
    assert "data-sf-lifecycle" in home
    assert "HandshakeRequest" in home
    assert "OperationRequest" in home
    assert "Reconcile" in home


def test_getting_started_routes_readers_to_real_examples() -> None:
    page = (ROOT / "docs/v0.1.0/getting-started.md").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "python -m examples.bootstrap.server" in page
    assert "python -m examples.bootstrap.client" in page
    assert "```stateforge-entity-flow" in page
    assert "source: getting-started-overview.yaml" in page
    for destination in (
        "../bootstrap/",
        "../procedures/",
        "../procedures/endpoint-discovery/",
        "../reference/python-contracts/",
    ):
        assert f'href="{destination}"' in page

    assert "avatars.githubusercontent.com/u/309498710" in readme
    assert "docs/v0.1.0/assets/brand" not in readme


def test_readme_uses_a_theme_neutral_protocol_lifecycle() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "```mermaid" in readme
    assert "sequenceDiagram" in readme
    assert "participant Directory as Discovery directory" in readme
    assert "Bootstrap.Handshake" in readme
    assert "Manifest.GetManifest" in readme
    assert "Health.Watch" in readme
    assert "AssessCapabilities" in readme
    assert "Trigger publications" in readme
    assert "Reconnect creates a new channel and fenced session" in readme
    assert "protocol-flow.svg" not in readme
    assert "docs/v0.1.0/" not in readme
    assert "https://docs.stateforge.net/sfp/latest/" in readme
    for reference in (
        "reference/versioning-compatibility/",
        "reference/status-errors/",
        "reference/security-trust-boundary/",
        "reference/glossary/",
    ):
        assert reference in readme


def test_versioning_guide_keeps_compatibility_boundaries_distinct() -> None:
    page = (
        ROOT / "docs/v0.1.0/reference/versioning-compatibility.md"
    ).read_text(encoding="utf-8")
    normalized_page = " ".join(page.split())
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for version_surface in (
        "Python distribution",
        "SFP wire contract",
        "Protobuf and Python package",
        "Endpoint descriptor schema",
        "Provider manifest schema",
        "Agent software version",
        "Provider implementation",
        "Operation or trigger identifier",
    ):
        assert version_surface in page

    assert "highest common `(major, minor)` pair" in normalized_page
    assert "Patch versions belong to software artifacts" in normalized_page
    assert "Buf's `FILE` compatibility policy" in normalized_page
    assert "reference/versioning-compatibility/" in readme

    declaration = yaml.safe_load(
        (ROOT / "docs/v0.1.0/reference/version-negotiation.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert declaration["schema"] == "stateforge.docs/procedure/v1"
    assert declaration["default_scenario"] == "success"
    assert set(declaration["scenarios"]) == {
        "success",
        "incompatible",
        "response-mismatch",
        "reconnect",
    }
    assert "source: version-negotiation.yaml" in page


def test_status_reference_covers_canonical_error_taxonomy() -> None:
    page = (ROOT / "docs/v0.1.0/reference/status-errors.md").read_text(
        encoding="utf-8"
    )

    for status in (
        "INVALID_ARGUMENT",
        "FAILED_PRECONDITION",
        "RESOURCE_EXHAUSTED",
        "UNIMPLEMENTED",
        "UNAVAILABLE",
        "ALREADY_EXISTS",
        "DEADLINE_EXCEEDED",
        "CANCELLED",
        "OUT_OF_RANGE",
        "NOT_FOUND",
        "INTERNAL",
    ):
        assert f"`{status}`" in page

    fixture_fields = (
        (
            "tests/fixtures/operation_admission/error-cases.json",
            "grpcStatus",
        ),
        (
            "tests/fixtures/operation_lifecycle/error-cases.json",
            "grpcCode",
        ),
    )
    for fixture, status_field in fixture_fields:
        cases = json.loads((ROOT / fixture).read_text(encoding="utf-8"))
        for case in cases:
            assert f"`{case[status_field]}`" in page
            reason = case.get("reason") or case["detail"]["reason"]
            assert f"`{reason}`" in page

    assert "Local protocol failure" in page
    assert "SERVICE_UNKNOWN" in page
    assert "Operation `FAILED`" in page
    assert "reference/status-errors/" in (
        ROOT / "docs/v0.1.0/index.md"
    ).read_text(encoding="utf-8")


def test_security_guide_preserves_the_local_trust_model() -> None:
    page = (
        ROOT / "docs/v0.1.0/reference/security-trust-boundary.md"
    ).read_text(encoding="utf-8")
    normalized_page = " ".join(page.split())

    for boundary in (
        "Local OS boundary",
        "Endpoint observation",
        "Bootstrap session",
        "Accepted declaration",
        "Runtime admission",
    ):
        assert boundary in page

    for non_credential in (
        "`provider_instance_id`",
        "`endpoint_generation`",
        "`provider_runtime_id`",
        "`session_id`",
        "`manifest_revision`",
    ):
        assert non_credential in page

    assert (
        "does not define a TCP listener, TLS, certificates" in normalized_page
    )
    assert "`writeOnly: true`" in page
    assert "Capability Assessment never substitutes" in normalized_page
    assert "Loss of evidence never creates permission" in normalized_page
    assert "reference/security-trust-boundary/" in (
        ROOT / "docs/v0.1.0/index.md"
    ).read_text(encoding="utf-8")


def test_glossary_distinguishes_canonical_protocol_terms() -> None:
    page = (ROOT / "docs/v0.1.0/reference/glossary.md").read_text(
        encoding="utf-8"
    )

    for wire_name in (
        "`provider_identity`",
        "`provider_instance_id`",
        "`provider_runtime_id`",
        "`endpoint_generation`",
        "`session_id`",
        "`manifest_revision`",
        "`operation_identifier`",
        "`operation_id`",
        "`publication_id`",
    ):
        assert wire_name in page

    for distinction in (
        "Provider identity / instance ID / runtime ID",
        "Wire version / manifest schema version / package version",
        "Health / availability / capability / authorization",
        "Operation identifier / operation ID",
        "Trigger identifier / publication ID",
        "gRPC status / domain outcome",
        "Retry / replay / reconnect / redispatch",
    ):
        assert distinction in page

    for recovery_term in (
        "**Retry**",
        "**Replay**",
        "**Reconnect**",
        "**Redispatch**",
        "**Fail closed**",
    ):
        assert recovery_term in page

    assert "reference/glossary/" in (ROOT / "docs/v0.1.0/index.md").read_text(
        encoding="utf-8"
    )


def test_procedure_map_preserves_phases_lanes_and_unique_destinations() -> (
    None
):
    procedure_map = (ROOT / "docs/v0.1.0/procedures/index.md").read_text(
        encoding="utf-8"
    )

    for phase in (
        "01 / Connect",
        "02 / Qualify",
        "03 / Exchange",
        "04 / Recover",
    ):
        assert f"## {phase}" in procedure_map
    assert "Operation path" in procedure_map
    assert "Trigger path" in procedure_map
    assert "Agent initiated" in procedure_map
    assert "Provider initiated" in procedure_map

    expected_procedure_count = 9
    destinations = re.findall(r'href="([^"]+)"', procedure_map)
    assert len(destinations) == expected_procedure_count
    assert len(set(destinations)) == len(destinations)


def test_shared_documentation_dependency_is_immutable() -> None:
    project = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = project["dependency-groups"]["docs"]
    theme = next(
        dependency
        for dependency in dependencies
        if dependency.startswith("stateforge-docs-theme @ ")
    )

    assert theme.endswith(f"@{THEME_REVISION}")
    assert re.fullmatch(
        r"stateforge-docs-theme @ "
        r"git\+https://github\.com/stateforge-org/stateforge-docs\.git@"
        r"[0-9a-f]{40}",
        theme,
    )


def test_protocol_does_not_duplicate_stateforge_brand_assets() -> None:
    brand_assets = [
        path
        for path in (ROOT / "docs").rglob("*")
        if path.is_file() and "brand" in path.parts
    ]
    assert brand_assets == []
