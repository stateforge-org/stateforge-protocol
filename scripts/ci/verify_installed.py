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
from stateforge_protocol.sfp.bootstrap.v1 import (
    validation as bootstrap_validation,
)
from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2,
)
from stateforge_protocol.sfp.capability_assessment.v1 import (
    validation as capability_validation,
)
from stateforge_protocol.sfp.endpoint_discovery.v1 import (
    contract as endpoint_discovery_contract,
)
from stateforge_protocol.sfp.manifest.v1 import manifest_pb2
from stateforge_protocol.sfp.manifest.v1 import (
    validation as manifest_validation,
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


def _verify_endpoint_discovery_fixtures(fixture_root: Path) -> int:
    """Exercise endpoint discovery from the installed package and fixtures."""
    path = fixture_root / "endpoint_discovery" / "descriptor.json"
    content = path.read_bytes()
    descriptor = endpoint_discovery_contract.parse_descriptor(content)
    if descriptor.to_json_bytes() != content:
        raise ValueError("Installed endpoint descriptor is not canonical")
    if (
        endpoint_discovery_contract.descriptor_filename(
            descriptor.provider_instance_id
        )
        != f"{descriptor.provider_instance_id}.sfp.json"
    ):
        raise ValueError("Installed endpoint descriptor filename is invalid")
    return 1


def _verify_bootstrap_validation(fixture_root: Path) -> int:
    """Exercise Bootstrap validation from the installed package."""
    handshake = _read_json_object(
        fixture_root / "bootstrap" / "handshake.json"
    )
    request = ParseDict(
        handshake["request"],
        bootstrap_pb2.HandshakeRequest(),
    )
    response = ParseDict(
        handshake["response"],
        bootstrap_pb2.HandshakeResponse(),
    )
    validated_request = bootstrap_validation.validate_handshake_request(
        request
    )
    validated_response = bootstrap_validation.validate_handshake_response(
        response
    )
    if (
        validated_response.provider_instance_id
        != validated_request.expected_provider_instance_id
    ):
        raise ValueError("Installed Bootstrap fixture identities differ")
    if response.endpoint_generation != request.expected_endpoint_generation:
        raise ValueError("Installed Bootstrap fixture generations differ")
    return 2


def _verify_manifest_validation(fixture_root: Path) -> int:
    """Exercise Manifest validation from the installed package."""
    response = ParseDict(
        _read_json_object(fixture_root / "manifest" / "response.json"),
        manifest_pb2.GetManifestResponse(),
    )
    manifest_validation.validate_manifest_response(response)
    key = manifest_validation.validate_manifest_key(
        response.provider_instance_id,
        response.manifest_schema_version,
        response.manifest_revision,
    )
    if key.revision != response.manifest_revision:
        raise ValueError("Installed Manifest key validation is invalid")
    return 2


def _verify_trigger_publication_validation(fixture_root: Path) -> int:
    """Exercise ordinary Trigger Publication validation."""
    root = fixture_root / "trigger_publication"
    open_request = ParseDict(
        _read_json_object(root / "open.json"),
        trigger_publication_pb2.StreamTriggersRequest(),
    )
    ready_response = ParseDict(
        _read_json_object(root / "ready.json"),
        trigger_publication_pb2.StreamTriggersResponse(),
    )
    publication_response = ParseDict(
        _read_json_object(root / "publication.json"),
        trigger_publication_pb2.StreamTriggersResponse(),
    )
    acknowledgement_request = ParseDict(
        _read_json_object(root / "acknowledgement-accepted-new.json"),
        trigger_publication_pb2.StreamTriggersRequest(),
    )
    trigger_validation.validate_stream_request(open_request)
    trigger_validation.validate_stream_response(ready_response)
    trigger_validation.validate_stream_open_exchange(
        open_request.open,
        ready_response.ready,
    )
    trigger_validation.validate_stream_response(publication_response)
    trigger_validation.validate_stream_request(acknowledgement_request)
    trigger_validation.validate_publication_acknowledgement(
        publication_response.publication,
        acknowledgement_request.acknowledgement,
    )
    return 4


def _verify_operation_admission_validation(fixture_root: Path) -> int:
    """Exercise ordinary Operation Admission validation."""
    root = fixture_root / "operation_admission"
    request = ParseDict(
        _read_json_object(root / "request.json"),
        operation_admission_pb2.StartOperationRequest(),
    )
    response = ParseDict(
        _read_json_object(root / "response-accepted-new.json"),
        operation_admission_pb2.StartOperationResponse(),
    )
    admission_validation.validate_start_operation_request(request)
    admission_validation.validate_start_operation_response(response)
    admission_validation.validate_admission_exchange(request, response)
    return 2


def _verify_operation_lifecycle_validation(fixture_root: Path) -> int:
    """Exercise ordinary Operation Lifecycle validation."""
    root = fixture_root / "operation_lifecycle"
    watch_request = ParseDict(
        _read_json_object(root / "watch-request.json"),
        operation_lifecycle_pb2.WatchOperationRequest(),
    )
    watch_response = ParseDict(
        _read_json_object(root / "watch-terminal.json"),
        operation_lifecycle_pb2.WatchOperationResponse(),
    )
    watch_response.updates_skipped = False
    cancel_request = ParseDict(
        _read_json_object(root / "cancel-request.json"),
        operation_lifecycle_pb2.CancelOperationRequest(),
    )
    cancel_response = ParseDict(
        _read_json_object(root / "cancel-requested.json"),
        operation_lifecycle_pb2.CancelOperationResponse(),
    )
    lifecycle_validation.validate_watch_exchange(
        watch_request,
        watch_response,
    )
    lifecycle_validation.validate_cancel_exchange(
        cancel_request,
        cancel_response,
    )
    return 2


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


def _verify_recovery_identities(scenarios: dict[str, object]) -> int:
    """Exercise installed recovery identity classification."""
    verified = 0
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
        verified += 1

    invalid_identities = _object_cases(scenarios, "invalidIdentityTransitions")
    for case in invalid_identities:
        try:
            recovery.classify_recovery(
                previous, _recovery_identity(case["current"])
            )
        except recovery.RecoveryContractError:
            verified += 1
        else:
            raise ValueError(
                f"Invalid recovery identity was accepted: {case.get('id')}"
            )
    return verified


def _recovery_admission_request(
    template: dict[str, object],
    case: dict[str, object],
) -> operation_admission_pb2.StartOperationRequest:
    """Build the admission request described by one recovery scenario."""
    request_data = copy.deepcopy(template)
    binding = request_data["sessionBinding"]
    if not isinstance(binding, dict):
        raise ValueError("Admission recovery session binding is invalid")
    generation = 43 if case.get("generationBoundary") is True else 42
    binding["expectedEndpointGeneration"] = str(generation)
    binding["expectedSessionId"] = "session-reconnected-42"
    request_data["admissionMode"] = str(case.get("requiredMode"))
    request = ParseDict(
        request_data,
        operation_admission_pb2.StartOperationRequest(),
    )
    admission_validation.validate_start_operation_request(request)
    may_dispatch = (
        request.admission_mode
        == operation_admission_pb2.ADMISSION_MODE_ADMIT_OR_RESOLVE
    )
    if may_dispatch is not case.get("mayDispatchAbsentWork"):
        raise ValueError(
            f"Recovery admission mode is inconsistent: {case.get('id')}"
        )
    return request


def _verify_retained_admission(
    request: operation_admission_pb2.StartOperationRequest,
    response_template: dict[str, object],
    case: dict[str, object],
) -> None:
    """Verify one recovery scenario with a retained operation record."""
    response_data = copy.deepcopy(response_template)
    response_data["endpointGeneration"] = str(
        request.session_binding.expected_endpoint_generation
    )
    response_data["sessionId"] = request.session_binding.expected_session_id
    response_data["disposition"] = str(case.get("expectedDisposition"))
    response = ParseDict(
        response_data,
        operation_admission_pb2.StartOperationResponse(),
    )
    admission_validation.validate_admission_exchange(request, response)
    actual_disposition = operation_admission_pb2.AdmissionDisposition.Name(
        response.disposition
    )
    if actual_disposition != case.get("expectedDisposition"):
        raise ValueError(
            f"Recovery admission disposition mismatch: {case.get('id')}"
        )
    if case.get("outcome") != "resolved":
        raise ValueError(
            f"Retained recovery is not resolved: {case.get('id')}"
        )


def _verify_lost_admission(
    request: operation_admission_pb2.StartOperationRequest,
    case: dict[str, object],
) -> None:
    """Verify one recovery scenario whose operation record was lost."""
    expected_reason = str(case.get("expectedReason"))
    detail = operation_admission_pb2.OperationAdmissionErrorDetail(
        operation_id=request.invocation.operation_id,
        reason=operation_admission_pb2.AdmissionErrorReason.Value(
            expected_reason
        ),
        retryable=False,
        explanation="Recovery could not prove a retained record.",
    )
    admission_validation.validate_admission_error_detail(detail)
    actual_reason = operation_admission_pb2.AdmissionErrorReason.Name(
        detail.reason
    )
    if actual_reason != expected_reason:
        raise ValueError(
            f"Recovery admission reason mismatch: {case.get('id')}"
        )
    if case.get("outcome") != "indeterminate":
        raise ValueError(
            f"Lost recovery state is not indeterminate: {case.get('id')}"
        )


def _verify_recovery_admission(
    fixture_root: Path,
    scenarios: dict[str, object],
) -> int:
    """Exercise every installed recovery admission scenario."""
    request_template = _read_json_object(
        fixture_root / "operation_admission" / "request.json"
    )
    response_template = _read_json_object(
        fixture_root
        / "operation_admission"
        / "response-resolved-existing.json"
    )
    verified = 0
    resolve_only_request: (
        operation_admission_pb2.StartOperationRequest | None
    ) = None
    for case in _object_cases(scenarios, "admissionRecovery"):
        request = _recovery_admission_request(request_template, case)
        if case.get("retainedRecord") is True:
            _verify_retained_admission(request, response_template, case)
        else:
            _verify_lost_admission(request, case)
        if (
            request.admission_mode
            == operation_admission_pb2.ADMISSION_MODE_RESOLVE_ONLY
        ):
            resolve_only_request = request
        verified += 1

    if resolve_only_request is None:
        raise ValueError("Recovery fixtures contain no resolve-only admission")
    accepted_response = ParseDict(
        _read_json_object(
            fixture_root / "operation_admission" / "response-accepted-new.json"
        ),
        operation_admission_pb2.StartOperationResponse(),
    )
    accepted_response.session_id = (
        resolve_only_request.session_binding.expected_session_id
    )
    accepted_response.endpoint_generation = (
        resolve_only_request.session_binding.expected_endpoint_generation
    )
    accepted_response.record.admitted_endpoint_generation = (
        accepted_response.endpoint_generation
    )
    try:
        admission_validation.validate_admission_exchange(
            resolve_only_request, accepted_response
        )
    except admission_validation.OperationAdmissionValidationError:
        pass
    else:
        raise ValueError("Installed validator allowed resolve-only admission")
    return verified


def _verify_recovery_trigger(
    fixture_root: Path,
    scenarios: dict[str, object],
) -> int:
    """Exercise installed trigger replay identity validation."""
    publication_template = ParseDict(
        _read_json_object(
            fixture_root / "trigger_publication" / "publication.json"
        ),
        trigger_publication_pb2.StreamTriggersResponse(),
    ).publication
    expected_fingerprint = _read_json_object(
        fixture_root
        / "trigger_publication"
        / "content-fingerprint-vector.json"
    )["fingerprint"]
    if (
        trigger_validation.compute_publication_content_fingerprint(
            publication_template
        )
        != expected_fingerprint
    ):
        raise ValueError(
            "Installed Trigger Publication fingerprint is invalid"
        )
    verified = 0
    for case in _object_cases(scenarios, "triggerRecovery"):
        publication = copy.deepcopy(publication_template)
        if case.get("samePublicationId") is not True:
            publication.publication_id = "77777777-7777-4777-8777-777777777777"
        if case.get("sameCanonicalContent") is not True:
            publication.payload.fields[
                "ref"
            ].string_value = "refs/heads/recovery-conflict"
        trigger_validation.validate_trigger_publication(publication)
        actual_same_content = (
            trigger_validation.compute_publication_content_fingerprint(
                publication
            )
            == expected_fingerprint
        )
        if actual_same_content is not case.get("sameCanonicalContent"):
            raise ValueError(
                f"Recovery trigger content mismatch: {case.get('id')}"
            )

        expected_disposition = case.get("expectedDisposition")
        if expected_disposition is not None:
            acknowledgement = trigger_publication_pb2.TriggerAcknowledgement(
                publication_id=publication.publication_id,
                disposition=(
                    trigger_publication_pb2.TriggerAcknowledgementDisposition.Value(
                        str(expected_disposition)
                    )
                ),
            )
            trigger_validation.validate_publication_acknowledgement(
                publication, acknowledgement
            )
            accepted_new = "TRIGGER_ACKNOWLEDGEMENT_DISPOSITION_ACCEPTED_NEW"
            creates_logical_trigger = (
                trigger_publication_pb2.TriggerAcknowledgementDisposition.Name(
                    acknowledgement.disposition
                )
                == accepted_new
            )
        else:
            expected_reason = str(case.get("expectedReason"))
            acknowledgement = trigger_publication_pb2.TriggerAcknowledgement(
                publication_id=publication.publication_id,
                disposition=(
                    trigger_publication_pb2.TRIGGER_ACKNOWLEDGEMENT_DISPOSITION_REJECTED
                ),
                rejection=trigger_publication_pb2.TriggerRejection(
                    reason=trigger_publication_pb2.TriggerRejectionReason.Value(
                        expected_reason
                    ),
                    retryable=False,
                    explanation=(
                        "The publication identity has conflicting content."
                    ),
                ),
            )
            trigger_validation.validate_publication_acknowledgement(
                publication, acknowledgement
            )
            if (
                trigger_publication_pb2.TriggerRejectionReason.Name(
                    acknowledgement.rejection.reason
                )
                != expected_reason
            ):
                raise ValueError(
                    f"Recovery trigger reason mismatch: {case.get('id')}"
                )
            creates_logical_trigger = False

        if creates_logical_trigger is not case.get("createsLogicalTrigger"):
            raise ValueError(
                f"Recovery trigger delivery mismatch: {case.get('id')}"
            )
        same_installation = case.get("sameInstallation") is True
        expected_new = not same_installation and actual_same_content
        if expected_new is not creates_logical_trigger:
            raise ValueError(
                f"Recovery trigger namespace mismatch: {case.get('id')}"
            )
        verified += 1
    return verified


def _verify_recovery_watch_response(
    request_template: dict[str, object],
    response_template: dict[str, object],
    case: dict[str, object],
) -> None:
    """Verify the Watch exchange represented by one recovery scenario."""
    request_data = copy.deepcopy(request_template)
    binding = request_data["sessionBinding"]
    if not isinstance(binding, dict):
        raise ValueError("Watch recovery session binding is invalid")
    binding["expectedSessionId"] = "session-reconnected-42"
    request_data["afterSequence"] = str(case.get("afterSequence"))
    request = ParseDict(
        request_data,
        operation_lifecycle_pb2.WatchOperationRequest(),
    )
    lifecycle_validation.validate_watch_operation_request(request)
    if "responseSequence" not in case:
        return
    response_data = copy.deepcopy(response_template)
    response_data["sessionId"] = binding["expectedSessionId"]
    snapshot = response_data["snapshot"]
    if not isinstance(snapshot, dict):
        raise ValueError("Watch recovery snapshot is invalid")
    snapshot["sequence"] = str(case.get("responseSequence"))
    response_data["updatesSkipped"] = case.get("updatesSkipped", False)
    response = ParseDict(
        response_data,
        operation_lifecycle_pb2.WatchOperationResponse(),
    )
    if case.get("expectedReason") is None:
        lifecycle_validation.validate_watch_exchange(request, response)
        return
    try:
        lifecycle_validation.validate_watch_exchange(request, response)
    except lifecycle_validation.OperationLifecycleValidationError:
        return
    raise ValueError(f"Invalid recovery cursor was accepted: {case.get('id')}")


def _verify_recovery_lifecycle_error(case: dict[str, object]) -> None:
    """Verify the structured error represented by a recovery scenario."""
    expected_reason = case.get("expectedReason")
    if expected_reason is None:
        return
    detail = operation_lifecycle_pb2.OperationLifecycleErrorDetail(
        operation_id="22222222-2222-4222-8222-222222222222",
        reason=operation_lifecycle_pb2.LifecycleErrorReason.Value(
            str(expected_reason)
        ),
        explanation="Recovery cannot provide the requested state.",
    )
    lifecycle_validation.validate_lifecycle_error_detail(detail)
    actual_reason = operation_lifecycle_pb2.LifecycleErrorReason.Name(
        detail.reason
    )
    if actual_reason != expected_reason:
        raise ValueError(
            f"Recovery lifecycle reason mismatch: {case.get('id')}"
        )


def _verify_recovery_lifecycle(
    fixture_root: Path,
    scenarios: dict[str, object],
) -> int:
    """Exercise every installed lifecycle recovery scenario."""
    request_template = _read_json_object(
        fixture_root / "operation_lifecycle" / "watch-request.json"
    )
    response_template = _read_json_object(
        fixture_root / "operation_lifecycle" / "watch-terminal.json"
    )
    verified = 0
    for case in _object_cases(scenarios, "watchRecovery"):
        _verify_recovery_watch_response(
            request_template, response_template, case
        )
        _verify_recovery_lifecycle_error(case)
        if case.get("outcome") not in {"current", "indeterminate"}:
            raise ValueError(
                f"Recovery lifecycle outcome is invalid: {case.get('id')}"
            )
        verified += 1

    later_request_data = copy.deepcopy(request_template)
    later_response_data = copy.deepcopy(response_template)
    later_response_data["updatesSkipped"] = True
    lifecycle_validation.validate_watch_exchange(
        ParseDict(
            later_request_data,
            operation_lifecycle_pb2.WatchOperationRequest(),
        ),
        ParseDict(
            later_response_data,
            operation_lifecycle_pb2.WatchOperationResponse(),
        ),
        previous_sequence=2,
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
    return verified


def _verify_recovery_contracts(fixture_root: Path) -> int:
    """Exercise installed recovery classifiers and procedure validators."""
    scenarios = _read_json_object(
        fixture_root / "disconnection_recovery" / "scenarios.json"
    )
    return sum(
        (
            _verify_recovery_identities(scenarios),
            _verify_recovery_admission(fixture_root, scenarios),
            _verify_recovery_trigger(fixture_root, scenarios),
            _verify_recovery_lifecycle(fixture_root, scenarios),
        )
    )


def _coverage_resources(
    procedure: dict[str, object], member: str
) -> list[str]:
    """Return one string-list field from a coverage entry."""
    resources = procedure.get(member)
    if not isinstance(resources, list) or not all(
        isinstance(resource, str) for resource in resources
    ):
        raise ValueError(f"Installed {member} entry is invalid")
    return resources


def _verify_coverage_entry(
    package_root: Path,
    procedure: dict[str, object],
) -> str | None:
    """Verify the modules and resources declared by one coverage entry."""
    contract_module = procedure.get("contractModule")
    if not isinstance(contract_module, str):
        raise ValueError("Installed contract module entry is invalid")
    module = importlib.import_module(contract_module)
    if not _is_within(Path(module.__file__ or "").resolve(), package_root):
        raise ValueError("Contract module loaded outside the installation")

    validation_module = procedure.get("validationModule")
    if validation_module is None:
        if not isinstance(procedure.get("validationException"), str):
            raise ValueError("Validation exception is not documented")
    elif isinstance(validation_module, str):
        validation = importlib.import_module(validation_module)
        if not getattr(validation, "__all__", None):
            raise ValueError("Public validation API is not explicit")
    else:
        raise ValueError("Installed validation module entry is invalid")

    for member in ("schemaResources", "fixtureRoots"):
        for resource in _coverage_resources(procedure, member):
            if not (package_root.parent / resource).exists():
                raise ValueError(
                    f"Installed conformance resource is missing: {resource}"
                )

    service_name = procedure.get("serviceName")
    if service_name is not None and not isinstance(service_name, str):
        raise ValueError("Installed service identity is invalid")
    return service_name


def _verify_coverage_inventory(
    package_root: Path,
    fixture_root: Path,
    results: dict[str, int],
) -> int:
    """Prove every declared contract ships and executed successfully."""
    inventory = _read_json_object(
        fixture_root / "conformance" / "coverage.json"
    )
    if inventory.get("schemaVersion") != 1:
        raise ValueError("Installed conformance inventory version is invalid")
    procedures = _object_cases(inventory, "procedures")
    result_keys = {
        str(procedure.get("installedResultKey")) for procedure in procedures
    }
    if result_keys != set(results):
        raise ValueError("Installed conformance execution is incomplete")
    if any(count <= 0 for count in results.values()):
        raise ValueError(
            "Installed conformance execution produced no evidence"
        )

    services = {
        service_name
        for procedure in procedures
        if (service_name := _verify_coverage_entry(package_root, procedure))
        is not None
    }

    expected_services = {
        procedure.service_name
        for procedure in shared_endpoint.PROCEDURE_LIMITS
    }
    if services != expected_services:
        raise ValueError(
            "Installed conformance service coverage is incomplete"
        )
    return len(procedures)


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
    endpoint_discovery_vector_count = _verify_endpoint_discovery_fixtures(
        fixture_root
    )
    bootstrap_vector_count = _verify_bootstrap_validation(fixture_root)
    health_scenario_count = _verify_health_fixtures(fixture_root)
    manifest_vector_count = _verify_manifest_validation(fixture_root)
    capability_assessment_vector_count = (
        _verify_capability_assessment_validation(fixture_root)
    )
    trigger_publication_vector_count = _verify_trigger_publication_validation(
        fixture_root
    )
    operation_admission_vector_count = _verify_operation_admission_validation(
        fixture_root
    )
    operation_lifecycle_vector_count = _verify_operation_lifecycle_validation(
        fixture_root
    )
    recovery_scenario_count = _verify_recovery_contracts(fixture_root)
    conformance_results = {
        "endpoint-discovery": endpoint_discovery_vector_count,
        "bootstrap": bootstrap_vector_count,
        "health": health_scenario_count,
        "manifest": manifest_vector_count,
        "capability-assessment": capability_assessment_vector_count,
        "trigger-publication": trigger_publication_vector_count,
        "operation-admission": operation_admission_vector_count,
        "operation-lifecycle": operation_lifecycle_vector_count,
        "disconnection-recovery": recovery_scenario_count,
        "shared-endpoint": procedure_contract_count,
    }
    coverage_inventory_count = _verify_coverage_inventory(
        package_root,
        fixture_root,
        conformance_results,
    )

    return {
        "distribution": _DISTRIBUTION,
        "version": distribution.version,
        "package_root": str(package_root),
        "generated_module_count": len(module_names),
        "schema_count": len(schemas),
        "fixture_count": len(fixture_files),
        "procedure_contract_count": procedure_contract_count,
        "coverage_inventory_count": coverage_inventory_count,
        "conformance_results": conformance_results,
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
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        result = verify(arguments.expected_version, arguments.workspace)
    except (ImportError, OSError, ValueError, json.JSONDecodeError) as error:
        sys.stderr.write(f"Installed-package verification failed: {error}\n")
        return 1
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
