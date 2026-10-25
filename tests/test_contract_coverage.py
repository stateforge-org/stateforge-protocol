"""Release-gate tests for complete SFP conformance coverage."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

from grpc_health.v1 import health_pb2

from stateforge_protocol.sfp import health_contract, shared_endpoint

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_PACKAGE = _ROOT / "src" / "stateforge_protocol"
_INVENTORY = _ROOT / "tests" / "fixtures" / "conformance" / "coverage.json"
_PROCEDURE_KEYS = {
    "id",
    "kind",
    "serviceName",
    "contractModule",
    "validationModule",
    "validationException",
    "schemaResources",
    "fixtureRoots",
    "sourceTests",
    "installedResultKey",
}


def _inventory() -> dict[str, object]:
    value = json.loads(_INVENTORY.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _procedures() -> list[dict[str, object]]:
    value = _inventory()["procedures"]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def _protobuf_service_names() -> set[str]:
    names: set[str] = set()
    for path in sorted(
        (_ROOT / "proto" / "stateforge_protocol" / "sfp").rglob("*.proto")
    ):
        content = path.read_text(encoding="utf-8")
        package = re.search(r"^package\s+([^;]+);", content, re.MULTILINE)
        assert package is not None, path
        services = re.findall(r"^service\s+(\w+)\s*\{", content, re.MULTILINE)
        names.update(f"{package.group(1)}.{service}" for service in services)
    return names


def _package_source_path(resource: str) -> Path:
    prefix = "stateforge_protocol/"
    assert resource.startswith(prefix), resource
    return _SOURCE_PACKAGE / resource.removeprefix(prefix)


def test_coverage_inventory_has_one_entry_per_contract_surface() -> None:
    inventory = _inventory()
    assert inventory["schemaVersion"] == 1
    procedures = _procedures()
    assert procedures
    assert all(set(procedure) == _PROCEDURE_KEYS for procedure in procedures)

    identifiers = [str(procedure["id"]) for procedure in procedures]
    result_keys = [
        str(procedure["installedResultKey"]) for procedure in procedures
    ]
    assert len(identifiers) == len(set(identifiers))
    assert len(result_keys) == len(set(result_keys))

    inventory_services = {
        str(procedure["serviceName"])
        for procedure in procedures
        if procedure["serviceName"] is not None
    }
    protobuf_services = _protobuf_service_names()
    health_service = health_pb2.DESCRIPTOR.services_by_name["Health"].full_name
    assert health_service == health_contract.STANDARD_HEALTH_SERVICE
    assert inventory_services == protobuf_services | {health_service}

    endpoint_services = {
        procedure.service_name
        for procedure in shared_endpoint.PROCEDURE_LIMITS
    }
    assert endpoint_services == inventory_services


def test_inventory_resources_and_public_modules_exist() -> None:
    for procedure in _procedures():
        contract_module = importlib.import_module(
            str(procedure["contractModule"])
        )
        assert contract_module.__file__

        validation_name = procedure["validationModule"]
        if validation_name is None:
            assert procedure["validationException"]
        else:
            validation = importlib.import_module(str(validation_name))
            exports = getattr(validation, "__all__", None)
            assert exports, validation_name
            assert all(hasattr(validation, name) for name in exports)
            assert procedure["validationException"] is None

        for resource in procedure["schemaResources"]:
            assert _package_source_path(str(resource)).is_file(), resource
        for resource in procedure["fixtureRoots"]:
            source = _ROOT / str(resource).replace(
                "stateforge_protocol/fixtures", "tests/fixtures", 1
            )
            assert source.is_dir(), resource
            assert any(path.is_file() for path in source.rglob("*")), resource
        for test in procedure["sourceTests"]:
            assert (_ROOT / str(test)).is_file(), test


def test_inventory_is_registered_in_every_standard_ci_path() -> None:
    entry_points = _inventory()["ciEntryPoints"]
    assert isinstance(entry_points, dict)
    assert set(entry_points) == {
        "sourceAction",
        "installedAction",
        "standardWorkflow",
    }
    content = {
        name: (_ROOT / str(path)).read_text(encoding="utf-8")
        for name, path in entry_points.items()
    }
    assert "python -m pytest" in content["sourceAction"]
    assert "verify_installed.py" in content["installedAction"]
    assert "protocol-source-verify.yml" in content["standardWorkflow"]
    assert "protocol-installed-test.yml" in content["standardWorkflow"]


def test_inventory_itself_is_packaged_as_conformance_evidence() -> None:
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"tests/fixtures" = "stateforge_protocol/fixtures"' in pyproject


def test_documented_coverage_matches_inventory() -> None:
    documentation = (
        _ROOT / "docs" / "v0.1.0" / "reference" / "conformance-coverage.md"
    ).read_text(encoding="utf-8")
    for procedure in _procedures():
        assert f"`{procedure['id']}`" in documentation
