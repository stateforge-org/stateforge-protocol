"""Verify standard gRPC Health and Agent eligibility semantics."""

import json
from pathlib import Path

from grpc_health.v1 import health_pb2, health_pb2_grpc

from stateforge_protocol.sfp import health_contract as contract
from stateforge_protocol.sfp.bootstrap.v1 import bootstrap_pb2
from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2,
)
from stateforge_protocol.sfp.manifest.v1 import manifest_pb2
from stateforge_protocol.sfp.operation_admission.v1 import (
    operation_admission_pb2,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    operation_lifecycle_pb2,
)
from stateforge_protocol.sfp.trigger_publication.v1 import (
    trigger_publication_pb2,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "health"
_ROOT = Path(__file__).resolve().parents[1]
_ELIGIBILITY_FACTORS = (
    "transportCurrent",
    "sessionCurrent",
    "generationCurrent",
    "manifestAccepted",
    "watchCurrent",
)


def _read(name: str) -> dict[str, object]:
    value = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _cases(document: dict[str, object], name: str) -> list[dict[str, object]]:
    value = document[name]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def _by_id(cases: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(case["id"]): case for case in cases}


def test_registry_uses_standard_health_and_real_sfp_service_names() -> None:
    registry = _read("registry.json")
    descriptors = (
        bootstrap_pb2.DESCRIPTOR.services_by_name["BootstrapService"],
        manifest_pb2.DESCRIPTOR.services_by_name["ManifestService"],
        capability_assessment_pb2.DESCRIPTOR.services_by_name[
            "CapabilityAssessmentService"
        ],
        operation_admission_pb2.DESCRIPTOR.services_by_name[
            "OperationAdmissionService"
        ],
        operation_lifecycle_pb2.DESCRIPTOR.services_by_name[
            "OperationLifecycleService"
        ],
        trigger_publication_pb2.DESCRIPTOR.services_by_name[
            "TriggerPublicationService"
        ],
    )
    assert registry["wireService"] == contract.STANDARD_HEALTH_SERVICE
    assert (
        registry["providerHealthService"]
        == contract.PROVIDER_HEALTH_SERVICE
        == ""
    )
    assert (
        registry["authoritativeWatchService"]
        == contract.AUTHORITATIVE_WATCH_SERVICE
        == ""
    )
    assert registry["registeredServices"] == [
        descriptor.full_name for descriptor in descriptors
    ] == list(contract.SFP_SERVICE_NAMES)
    assert registry["statuses"] == list(contract.HEALTH_STATUS_NAMES)
    assert registry["channel"] == "existing-multiplexed-sfp"


def test_contract_uses_official_grpc_health_descriptors() -> None:
    service = health_pb2.DESCRIPTOR.services_by_name["Health"]
    request = health_pb2.HealthCheckRequest.DESCRIPTOR
    response = health_pb2.HealthCheckResponse.DESCRIPTOR
    statuses = response.enum_types_by_name["ServingStatus"]

    assert service.full_name == contract.STANDARD_HEALTH_SERVICE
    assert {"Check", "Watch"} <= set(service.methods_by_name)
    for method_name in ("Check", "Watch"):
        method = service.methods_by_name[method_name]
        assert method.input_type is request
        assert method.output_type is response
    assert request.fields_by_name["service"].number == 1
    assert tuple(statuses.values_by_name) == contract.HEALTH_STATUS_NAMES
    assert health_pb2_grpc.HealthStub is not None
    assert health_pb2_grpc.HealthServicer is not None


def test_no_custom_health_protobuf_is_introduced() -> None:
    assert not list((_ROOT / "proto").rglob("*health*.proto"))
    assert not list((_ROOT / "src").rglob("health_pb2*.py"))


def test_named_empty_unknown_and_wildcard_lookups() -> None:
    lookups = _by_id(_cases(_read("registry.json"), "lookups"))
    assert lookups["known-named-check"] == {
        "id": "known-named-check",
        "rpc": "Check",
        "service": contract.OPERATION_ADMISSION_SERVICE,
        "result": "CURRENT_STATUS",
        "diagnosticOnly": True,
    }
    assert lookups["provider-health-check"] == {
        "id": "provider-health-check",
        "rpc": "Check",
        "service": contract.PROVIDER_HEALTH_SERVICE,
        "result": "CURRENT_STATUS",
        "diagnosticOnly": True,
    }
    assert lookups["provider-health-watch"] == {
        "id": "provider-health-watch",
        "rpc": "Watch",
        "service": contract.AUTHORITATIVE_WATCH_SERVICE,
        "result": "CURRENT_AND_ORDERED_UPDATES",
        "authoritativeForProviderHealth": True,
    }
    assert lookups["unknown-check"]["grpcCode"] == "NOT_FOUND"
    assert lookups["wildcard-check"]["grpcCode"] == "NOT_FOUND"
    assert lookups["unknown-watch"]["firstStatus"] == "SERVICE_UNKNOWN"
    assert lookups["unknown-watch"]["streamRemainsOpen"] is True


def test_provider_lifecycle_fails_closed_before_readiness_and_teardown(
) -> None:
    lifecycle = _by_id(_cases(_read("scenarios.json"), "lifecycle"))
    assert lifecycle["startup"]["to"] == "NOT_SERVING"
    assert lifecycle["startup"]["newAdmissionAllowed"] is False
    assert lifecycle["validated-readiness"]["to"] == "SERVING"
    assert lifecycle["degraded-or-maintenance"]["to"] == "NOT_SERVING"
    assert lifecycle["recovery"]["to"] == "SERVING"
    assert lifecycle["bounded-shutdown"]["beforeTeardown"] is True
    assert lifecycle["bounded-shutdown"]["newAdmissionAllowed"] is False


def test_operational_eligibility_requires_every_current_prerequisite() -> None:
    cases = _cases(_read("scenarios.json"), "eligibility")
    required = {
        "all-current-and-serving",
        "serving-with-invalid-manifest",
        "not-serving",
        "unknown-initial-state",
        "unknown-service",
        "stale-session-serving",
        "stale-generation-serving",
        "watch-lost",
    }
    assert {str(case["id"]) for case in cases} == required
    for case in cases:
        derived = all(case[name] is True for name in _ELIGIBILITY_FACTORS)
        derived = derived and case["healthStatus"] == "SERVING"
        assert case["expectedEligible"] is derived


def test_watch_is_ordered_authority_and_stale_events_are_fenced() -> None:
    cases = _by_id(_cases(_read("scenarios.json"), "watch"))
    assert all(
        case["service"] == contract.AUTHORITATIVE_WATCH_SERVICE
        for case in cases.values()
    )
    assert cases["initial-replay"]["statuses"] == ["SERVING"]
    assert cases["ordered-state-changes"]["statuses"] == [
        "SERVING",
        "NOT_SERVING",
        "SERVING",
    ]
    assert cases["ordered-state-changes"]["acceptedEvents"] == len(
        cases["ordered-state-changes"]["statuses"]
    )
    assert cases["stale-session-event"]["watchBindingCurrent"] is False
    assert cases["stale-session-event"]["acceptedEvents"] == 0
    assert cases["stale-session-event"]["eligibilityAfter"] is False


def test_watch_loss_backpressure_and_unimplemented_fail_closed() -> None:
    cases = _by_id(_cases(_read("scenarios.json"), "watch"))
    assert cases["channel-failure"]["terminalCode"] == "UNAVAILABLE"
    assert cases["channel-failure"]["retry"] is True
    assert cases["slow-observer"]["terminalCode"] == "RESOURCE_EXHAUSTED"
    assert cases["slow-observer"]["retry"] is True
    assert cases["watch-unimplemented"]["terminalCode"] == "UNIMPLEMENTED"
    assert cases["watch-unimplemented"]["retry"] is False
    for name in ("channel-failure", "slow-observer", "watch-unimplemented"):
        assert cases[name]["eligibilityAfter"] is False


def test_health_loss_does_not_mutate_admitted_work() -> None:
    cases = _cases(_read("scenarios.json"), "admittedWork")
    assert cases == [
        {
            "id": "health-loss-after-admission",
            "healthStatus": "NOT_SERVING",
            "newAdmissionAllowed": False,
            "existingOperationStateMutated": False,
            "existingTerminalResultReplaced": False,
            "cancellationRequested": False,
        }
    ]


def test_sanitized_diagnostic_boundary_is_portable() -> None:
    boundaries = _cases(_read("scenarios.json"), "diagnosticBoundaries")
    assert boundaries == [
        {
            "codePoints": contract.MAX_DIAGNOSTIC_CODE_POINTS,
            "accepted": True,
        },
        {
            "codePoints": contract.MAX_DIAGNOSTIC_CODE_POINTS + 1,
            "accepted": False,
        },
    ]
