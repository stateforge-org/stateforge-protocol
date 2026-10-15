"""Verify the installed StateForge Protocol wheel outside its checkout."""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import sys
from importlib import metadata
from pathlib import Path

from grpc_health.v1 import health_pb2, health_pb2_grpc

from stateforge_protocol.sfp import health_contract, shared_endpoint
from stateforge_protocol.sfp.bootstrap.v1 import contract as bootstrap_contract

_DISTRIBUTION = "stateforge-protocol"
_EXPECTED_HEALTH_RESPONSE_BYTES = 64


def _verify_wire_contracts() -> int:
    """Verify installed Bootstrap, Health, and endpoint limit contracts."""
    expected_bootstrap = {
        "service": "stateforge.sfp.bootstrap.v1.BootstrapService",
        "method": "Handshake",
        "path": ("/stateforge.sfp.bootstrap.v1.BootstrapService/Handshake"),
        "request": 64 * 1024,
        "response": 8 * 1024,
        "session": 255,
    }
    actual_bootstrap = {
        "service": bootstrap_contract.SERVICE_NAME,
        "method": bootstrap_contract.HANDSHAKE_METHOD_NAME,
        "path": bootstrap_contract.HANDSHAKE_METHOD_PATH,
        "request": bootstrap_contract.MAX_REQUEST_BYTES,
        "response": bootstrap_contract.MAX_RESPONSE_BYTES,
        "session": bootstrap_contract.MAX_SESSION_ID_CODE_POINTS,
    }
    if actual_bootstrap != expected_bootstrap:
        raise ValueError("Installed Bootstrap contract limits are invalid")
    if health_contract.MAX_REQUEST_BYTES != 4 * 1024:
        raise ValueError("Installed Health request limit is invalid")
    if health_contract.MAX_RESPONSE_BYTES != _EXPECTED_HEALTH_RESPONSE_BYTES:
        raise ValueError("Installed Health response limit is invalid")

    procedures = shared_endpoint.PROCEDURE_LIMITS
    service_names = [procedure.service_name for procedure in procedures]
    expected_services = {
        health_contract.STANDARD_HEALTH_SERVICE,
        *health_contract.SFP_SERVICE_NAMES,
    }
    if len(service_names) != len(expected_services):
        raise ValueError(
            "Installed endpoint procedure inventory is incomplete"
        )
    if set(service_names) != expected_services:
        raise ValueError("Installed endpoint procedure inventory is invalid")
    if shared_endpoint.MAX_PROVIDER_RECEIVE_BYTES != 8 * 1024 * 1024:
        raise ValueError("Installed Provider receive ceiling is invalid")
    if shared_endpoint.MAX_PROVIDER_SEND_BYTES != 16 * 1024 * 1024:
        raise ValueError("Installed Provider send ceiling is invalid")
    return len(procedures)


def _read_json_object(path: Path) -> dict[str, object]:
    """Read one JSON object or fail installed-package verification."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _object_cases(
    document: dict[str, object], name: str
) -> list[dict[str, object]]:
    """Return an object-array member from a conformance document."""
    value = document.get(name)
    if not isinstance(value, list) or not all(
        isinstance(item, dict) for item in value
    ):
        raise ValueError(f"Expected an object array named {name}")
    return value


def _verify_health_fixtures(fixture_root: Path) -> int:
    """Verify Health vectors from the exact installed wheel."""
    service = health_pb2.DESCRIPTOR.services_by_name["Health"]
    if service.full_name != health_contract.STANDARD_HEALTH_SERVICE:
        raise ValueError("Installed package has the wrong Health service")
    if not {"Check", "Watch"} <= set(service.methods_by_name):
        raise ValueError("Installed Health service is missing required RPCs")
    if health_pb2_grpc.HealthStub is None:
        raise ValueError("Installed package has no Health client bindings")

    root = fixture_root / "health"
    registry = _read_json_object(root / "registry.json")
    scenarios = _read_json_object(root / "scenarios.json")
    expected_registry = {
        "wireService": health_contract.STANDARD_HEALTH_SERVICE,
        "providerHealthService": health_contract.PROVIDER_HEALTH_SERVICE,
        "authoritativeWatchService": (
            health_contract.AUTHORITATIVE_WATCH_SERVICE
        ),
        "registeredServices": list(health_contract.SFP_SERVICE_NAMES),
        "statuses": list(health_contract.HEALTH_STATUS_NAMES),
        "channel": "existing-multiplexed-sfp",
    }
    for name, expected in expected_registry.items():
        if registry.get(name) != expected:
            raise ValueError(f"Installed Health registry mismatch: {name}")

    eligibility = _object_cases(scenarios, "eligibility")
    factors = (
        "transportCurrent",
        "sessionCurrent",
        "generationCurrent",
        "manifestAccepted",
        "watchCurrent",
    )
    for case in eligibility:
        derived = all(case.get(name) is True for name in factors)
        derived = derived and case.get("healthStatus") == "SERVING"
        if case.get("expectedEligible") is not derived:
            raise ValueError(
                f"Invalid installed Health eligibility case: {case.get('id')}"
            )

    required_watch_cases = {
        "initial-replay",
        "ordered-state-changes",
        "stale-session-event",
        "channel-failure",
        "slow-observer",
        "watch-unimplemented",
    }
    watch = _object_cases(scenarios, "watch")
    if {case.get("id") for case in watch} != required_watch_cases:
        raise ValueError("Installed Health Watch scenarios are incomplete")
    if any(
        case.get("service") != health_contract.AUTHORITATIVE_WATCH_SERVICE
        for case in watch
    ):
        raise ValueError(
            "Installed Health Watch must use Provider-wide status"
        )

    boundaries = _object_cases(scenarios, "diagnosticBoundaries")
    if boundaries != [
        {
            "codePoints": health_contract.MAX_DIAGNOSTIC_CODE_POINTS,
            "accepted": True,
        },
        {
            "codePoints": health_contract.MAX_DIAGNOSTIC_CODE_POINTS + 1,
            "accepted": False,
        },
    ]:
        raise ValueError("Installed Health diagnostic boundaries are invalid")

    return sum(
        len(_object_cases(scenarios, name))
        for name in (
            "lifecycle",
            "eligibility",
            "watch",
            "admittedWork",
            "diagnosticBoundaries",
        )
    )


def _is_within(path: Path, parent: Path) -> bool:
    """Return whether ``path`` is contained below ``parent``."""
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def verify(expected_version: str, workspace: Path | None) -> dict[str, object]:
    """Verify package metadata, imports, schemas, fixtures, and isolation."""
    distribution = metadata.distribution(_DISTRIBUTION)
    if distribution.version != expected_version:
        msg = (
            f"Expected {_DISTRIBUTION} {expected_version}, "
            f"found {distribution.version}"
        )
        raise ValueError(msg)
    package_root = Path(
        str(distribution.locate_file("stateforge_protocol"))
    ).resolve()
    if not package_root.is_dir():
        raise ValueError(
            f"Installed package directory is missing: {package_root}"
        )
    if workspace is not None and _is_within(package_root, workspace.resolve()):
        raise ValueError("Package imported from the repository checkout")
    if not (package_root / "py.typed").is_file():
        raise ValueError("Installed package does not contain py.typed")

    module_names = sorted(
        module.name
        for module in pkgutil.walk_packages(
            [str(package_root)], prefix="stateforge_protocol."
        )
        if module.name.endswith(("_pb2", "_pb2_grpc"))
    )
    if not module_names:
        raise ValueError("Installed package contains no generated modules")
    for module_name in module_names:
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__ or "").resolve()
        if not _is_within(module_path, package_root):
            raise ValueError(
                f"Module did not load from the installed wheel: {module_name}"
            )

    schemas = sorted(package_root.rglob("*.schema.json"))
    if not schemas:
        raise ValueError("Installed package contains no validation schemas")
    for schema in schemas:
        json.loads(schema.read_text(encoding="utf-8"))

    fixture_root = package_root / "fixtures"
    fixture_files = sorted(fixture_root.rglob("*.json"))
    if not fixture_files:
        raise ValueError("Installed package contains no conformance fixtures")
    for fixture in fixture_files:
        json.loads(fixture.read_text(encoding="utf-8"))

    procedure_contract_count = _verify_wire_contracts()
    health_scenario_count = _verify_health_fixtures(fixture_root)

    return {
        "distribution": _DISTRIBUTION,
        "version": distribution.version,
        "package_root": str(package_root),
        "generated_module_count": len(module_names),
        "schema_count": len(schemas),
        "fixture_count": len(fixture_files),
        "procedure_contract_count": procedure_contract_count,
        "health_scenario_count": health_scenario_count,
    }


def main() -> int:
    """Run installed-package verification from command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--workspace", type=Path)
    arguments = parser.parse_args()
    try:
        result = verify(arguments.expected_version, arguments.workspace)
    except (ImportError, OSError, ValueError, json.JSONDecodeError) as error:
        sys.stderr.write(f"Installed-package verification failed: {error}\n")
        return 1
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
