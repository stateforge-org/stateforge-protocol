"""Verify Protocol's shared documentation-system contract."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

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
