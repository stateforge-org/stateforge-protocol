"""Verify installed StateForge Protocol distributions outside checkout."""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import pkgutil
import sys
from importlib import metadata
from pathlib import Path
from uuid import UUID

from google.protobuf.json_format import ParseDict
from grpc_health.v1 import health_pb2, health_pb2_grpc

from stateforge_protocol.sfp import health_contract, recovery, shared_endpoint
from stateforge_protocol.sfp.bootstrap.v1 import bootstrap_pb2
from stateforge_protocol.sfp.bootstrap.v1 import contract as bootstrap_contract
from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2,
)
from stateforge_protocol.sfp.capability_assessment.v1 import (
    validation as capability_validation,
)
from stateforge_protocol.sfp.endpoint_discovery.v1 import (
    contract as endpoint_discovery_contract,
)
from stateforge_protocol.sfp.operation_admission.v1 import (
    operation_admission_pb2,
)
from stateforge_protocol.sfp.operation_admission.v1 import (
    validation as admission_validation,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    operation_lifecycle_pb2,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    validation as lifecycle_validation,
)
from stateforge_protocol.sfp.trigger_publication.v1 import (
    trigger_publication_pb2,
)
from stateforge_protocol.sfp.trigger_publication.v1 import (
    validation as trigger_validation,
)

_DISTRIBUTION = "stateforge-protocol"
_EXPECTED_HEALTH_RESPONSE_BYTES = 64
_EXPECTED_DESCRIPTOR_MODE = 0o640
_EXPECTED_SOCKET_MODE = 0o660


def _verify_wire_contracts() -> int:
    """Verify installed Bootstrap, Health, and endpoint limit contracts."""
    bootstrap_service = bootstrap_pb2.DESCRIPTOR.services_by_name[
        "BootstrapService"
    ]
    handshake_method = bootstrap_service.methods_by_name["Handshake"]
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
        "method": handshake_method.name,
        "path": f"/{bootstrap_service.full_name}/{handshake_method.name}",
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

    provider_instance_id = UUID("7f7db7d8-68b4-4f71-9769-065b5c4f941c")
    descriptor = endpoint_discovery_contract.EndpointDescriptor(
        provider_instance_id=provider_instance_id,
        endpoint_generation=4,
        socket_path=(
            f"/run/stateforge-agent/providers/{provider_instance_id}.4.sock"
        ),
    )
    if (
        endpoint_discovery_contract.parse_descriptor(
            descriptor.to_json_bytes()
        )
        != descriptor
    ):
        raise ValueError("Installed endpoint descriptor contract is invalid")
    if endpoint_discovery_contract.MAX_DESCRIPTOR_BYTES != 4 * 1024:
        raise ValueError("Installed endpoint descriptor limit is invalid")
    if (
        endpoint_discovery_contract.DESCRIPTOR_MODE
        != _EXPECTED_DESCRIPTOR_MODE
    ):
        raise ValueError("Installed endpoint descriptor mode is invalid")
    if endpoint_discovery_contract.SOCKET_MODE != _EXPECTED_SOCKET_MODE:
        raise ValueError("Installed endpoint socket mode is invalid")

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


def _verify_capability_assessment_validation(fixture_root: Path) -> int:
    """Exercise canonical assessment validation from the installed package."""
    root = fixture_root / "capability_assessment"
    request = ParseDict(
        _read_json_object(root / "request.json"),
        capability_assessment_pb2.AssessCapabilitiesRequest(),
    )
    response = ParseDict(
        _read_json_object(root / "response-mixed-states.json"),
        capability_assessment_pb2.AssessCapabilitiesResponse(),
    )
    capability_validation.validate_assess_capabilities_request(request)
    capability_validation.validate_assess_capabilities_response(response)
    capability_validation.validate_assessment_exchange(request, response)

    response.session_id = "mismatched-session"
    try:
        capability_validation.validate_assessment_exchange(request, response)
    except capability_validation.CapabilityAssessmentValidationError:
        pass
    else:
        raise ValueError(
            "Installed Capability Assessment exchange validation is inactive"
        )
    return 2


def _recovery_identity(value: object) -> recovery.EndpointSessionIdentity:
    """Build one identity from a packaged recovery scenario."""
    if not isinstance(value, dict):
        raise ValueError("Recovery identity must be an object")
    return recovery.EndpointSessionIdentity(
        provider_instance_id=UUID(str(value["providerInstanceId"])),
        endpoint_generation=int(str(value["endpointGeneration"])),
        provider_runtime_id=UUID(str(value["providerRuntimeId"])),
        session_id=str(value["sessionId"]),
    )


def _verify_recovery_identities(scenarios: dict[str, object]) -> None:
    """Exercise installed recovery identity classification."""
    previous = recovery.EndpointSessionIdentity(
        provider_instance_id=UUID("11111111-1111-4111-8111-111111111111"),
        endpoint_generation=42,
        provider_runtime_id=UUID("33333333-3333-4333-8333-333333333333"),
        session_id="session-admission-42",
    )
    identities = _object_cases(scenarios, "identityTransitions")
    for case in identities:
        kind = recovery.classify_recovery(
            previous, _recovery_identity(case["current"])
        )
        if kind.value != case.get("expectedKind"):
            raise ValueError(
                f"Recovery identity classification failed: {case.get('id')}"
            )
        if kind.may_reconcile_previous_state is not case.get(
            "mayReconcilePreviousState"
        ):
            raise ValueError(
                f"Recovery ownership classification failed: {case.get('id')}"
            )
        if kind.requires_resolve_only is not case.get("requiresResolveOnly"):
            raise ValueError(
                f"Recovery admission classification failed: {case.get('id')}"
            )

    invalid_identities = _object_cases(scenarios, "invalidIdentityTransitions")
    for case in invalid_identities:
        try:
            recovery.classify_recovery(
                previous, _recovery_identity(case["current"])
            )
        except recovery.RecoveryContractError:
            pass
        else:
            raise ValueError(
                f"Invalid recovery identity was accepted: {case.get('id')}"
            )


def _verify_recovery_admission(fixture_root: Path) -> None:
    """Exercise installed resolve-only admission validation."""
    admission_request_data = _read_json_object(
        fixture_root / "operation_admission" / "request.json"
    )
    admission_response_data = _read_json_object(
        fixture_root
        / "operation_admission"
        / "response-resolved-existing.json"
    )
    admission_request_data["sessionBinding"]["expectedSessionId"] = (
        "session-reconnected-42"
    )
    admission_request_data["admissionMode"] = "ADMISSION_MODE_RESOLVE_ONLY"
    admission_request = ParseDict(
        admission_request_data,
        operation_admission_pb2.StartOperationRequest(),
    )
    admission_response = ParseDict(
        admission_response_data,
        operation_admission_pb2.StartOperationResponse(),
    )
    admission_validation.validate_admission_exchange(
        admission_request, admission_response
    )
    accepted_response = ParseDict(
        _read_json_object(
            fixture_root / "operation_admission" / "response-accepted-new.json"
        ),
        operation_admission_pb2.StartOperationResponse(),
    )
    accepted_response.session_id = (
        admission_request.session_binding.expected_session_id
    )
    try:
        admission_validation.validate_admission_exchange(
            admission_request, accepted_response
        )
    except admission_validation.OperationAdmissionValidationError:
        pass
    else:
        raise ValueError("Installed validator allowed resolve-only admission")


def _verify_recovery_trigger(fixture_root: Path) -> None:
    """Exercise installed trigger replay identity validation."""
    publication = ParseDict(
        _read_json_object(
            fixture_root / "trigger_publication" / "publication.json"
        ),
        trigger_publication_pb2.StreamTriggersResponse(),
    ).publication
    acknowledgement = ParseDict(
        _read_json_object(
            fixture_root
            / "trigger_publication"
            / "acknowledgement-accepted-duplicate.json"
        ),
        trigger_publication_pb2.StreamTriggersRequest(),
    ).acknowledgement
    trigger_validation.validate_publication_acknowledgement(
        publication, acknowledgement
    )
    fingerprint = _read_json_object(
        fixture_root
        / "trigger_publication"
        / "content-fingerprint-vector.json"
    )["fingerprint"]
    if (
        trigger_validation.compute_publication_content_fingerprint(publication)
        != fingerprint
    ):
        raise ValueError(
            "Installed Trigger Publication fingerprint is invalid"
        )


def _verify_recovery_lifecycle(fixture_root: Path) -> None:
    """Exercise installed lifecycle cursor and transition validation."""
    watch_request_data = _read_json_object(
        fixture_root / "operation_lifecycle" / "watch-request.json"
    )
    watch_response_data = _read_json_object(
        fixture_root / "operation_lifecycle" / "watch-terminal.json"
    )
    watch_request_data["sessionBinding"]["expectedSessionId"] = (
        "session-reconnected-42"
    )
    watch_request_data["afterSequence"] = "2"
    watch_response_data["sessionId"] = "session-reconnected-42"
    watch_response_data["updatesSkipped"] = True
    lifecycle_validation.validate_watch_exchange(
        ParseDict(
            copy.deepcopy(watch_request_data),
            operation_lifecycle_pb2.WatchOperationRequest(),
        ),
        ParseDict(
            copy.deepcopy(watch_response_data),
            operation_lifecycle_pb2.WatchOperationResponse(),
        ),
    )

    lifecycle_snapshots = _read_json_object(
        fixture_root / "operation_lifecycle" / "snapshots.json"
    )
    running = ParseDict(
        copy.deepcopy(lifecycle_snapshots["running"]),
        operation_lifecycle_pb2.OperationSnapshot(),
    )
    cancelled_data = copy.deepcopy(lifecycle_snapshots["cancelled"])
    cancelled_data["sequence"] = "3"
    cancelled_data["updatedAt"] = "2026-09-19T12:00:02Z"
    cancelled_data.pop("progress", None)
    cancelled = ParseDict(
        cancelled_data,
        operation_lifecycle_pb2.OperationSnapshot(),
    )
    try:
        lifecycle_validation.validate_snapshot_transition(running, cancelled)
    except lifecycle_validation.OperationLifecycleValidationError:
        pass
    else:
        raise ValueError("Installed validator allowed direct cancellation")


def _verify_recovery_contracts(fixture_root: Path) -> int:
    """Exercise installed recovery classifiers and procedure validators."""
    scenarios = _read_json_object(
        fixture_root / "disconnection_recovery" / "scenarios.json"
    )
    _verify_recovery_identities(scenarios)
    _verify_recovery_admission(fixture_root)
    _verify_recovery_trigger(fixture_root)
    _verify_recovery_lifecycle(fixture_root)

    return sum(
        len(_object_cases(scenarios, name))
        for name in (
            "identityTransitions",
            "invalidIdentityTransitions",
            "admissionRecovery",
            "triggerRecovery",
            "watchRecovery",
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
    capability_assessment_vector_count = (
        _verify_capability_assessment_validation(fixture_root)
    )
    recovery_scenario_count = _verify_recovery_contracts(fixture_root)

    return {
        "distribution": _DISTRIBUTION,
        "version": distribution.version,
        "package_root": str(package_root),
        "generated_module_count": len(module_names),
        "schema_count": len(schemas),
        "fixture_count": len(fixture_files),
        "procedure_contract_count": procedure_contract_count,
        "health_scenario_count": health_scenario_count,
        "capability_assessment_vector_count": (
            capability_assessment_vector_count
        ),
        "recovery_scenario_count": recovery_scenario_count,
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
