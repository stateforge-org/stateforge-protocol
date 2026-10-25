"""Cross-procedure conformance for SFP disconnection and recovery."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest
from google.protobuf.json_format import ParseDict

from stateforge_protocol.sfp import recovery
from stateforge_protocol.sfp.operation_admission.v1 import (
    operation_admission_pb2 as admission_pb,
)
from stateforge_protocol.sfp.operation_admission.v1 import (
    validation as admission_validation,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    operation_lifecycle_pb2 as lifecycle_pb,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    validation as lifecycle_validation,
)
from stateforge_protocol.sfp.trigger_publication.v1 import (
    trigger_publication_pb2 as trigger_pb,
)
from stateforge_protocol.sfp.trigger_publication.v1 import (
    validation as trigger_validation,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_RECOVERY = _FIXTURES / "disconnection_recovery" / "scenarios.json"
_PREVIOUS_IDENTITY = recovery.EndpointSessionIdentity(
    provider_instance_id=UUID("11111111-1111-4111-8111-111111111111"),
    endpoint_generation=42,
    provider_runtime_id=UUID("33333333-3333-4333-8333-333333333333"),
    session_id="session-admission-42",
)


def _read(path: str) -> object:
    return json.loads((_FIXTURES / path).read_text(encoding="utf-8"))


def _document() -> dict[str, object]:
    value = json.loads(_RECOVERY.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _cases(name: str) -> list[dict[str, object]]:
    value = _document()[name]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def _identity(value: object) -> recovery.EndpointSessionIdentity:
    assert isinstance(value, dict)
    return recovery.EndpointSessionIdentity(
        provider_instance_id=UUID(str(value["providerInstanceId"])),
        endpoint_generation=int(str(value["endpointGeneration"])),
        provider_runtime_id=UUID(str(value["providerRuntimeId"])),
        session_id=str(value["sessionId"]),
    )


@pytest.mark.parametrize("case", _cases("identityTransitions"))
def test_identity_transitions_have_one_canonical_classification(
    case: dict[str, object],
) -> None:
    kind = recovery.classify_recovery(
        _PREVIOUS_IDENTITY, _identity(case["current"])
    )

    assert kind.value == case["expectedKind"]
    assert (
        kind.may_reconcile_previous_state is case["mayReconcilePreviousState"]
    )
    assert kind.requires_resolve_only is case["requiresResolveOnly"]


@pytest.mark.parametrize("case", _cases("invalidIdentityTransitions"))
def test_stale_or_impossible_identity_is_not_recovery(
    case: dict[str, object],
) -> None:
    with pytest.raises(recovery.RecoveryContractError):
        recovery.classify_recovery(
            _PREVIOUS_IDENTITY, _identity(case["current"])
        )


def test_trigger_replay_preserves_content_and_creates_no_second_event() -> (
    None
):
    publication_envelope = ParseDict(
        _read("trigger_publication/publication.json"),
        trigger_pb.StreamTriggersResponse(),
    )
    acknowledgement_envelope = ParseDict(
        _read("trigger_publication/acknowledgement-accepted-duplicate.json"),
        trigger_pb.StreamTriggersRequest(),
    )
    vector = _read("trigger_publication/content-fingerprint-vector.json")
    assert isinstance(vector, dict)

    trigger_validation.validate_stream_response(publication_envelope)
    trigger_validation.validate_stream_request(acknowledgement_envelope)
    trigger_validation.validate_publication_acknowledgement(
        publication_envelope.publication,
        acknowledgement_envelope.acknowledgement,
    )
    assert (
        trigger_validation.compute_publication_content_fingerprint(
            publication_envelope.publication
        )
        == vector["fingerprint"]
    )

    altered = copy.deepcopy(publication_envelope.publication)
    altered.payload.fields["ref"].string_value = "refs/heads/other"
    assert (
        trigger_validation.compute_publication_content_fingerprint(altered)
        != vector["fingerprint"]
    )


def test_recovered_trigger_stream_is_bound_to_the_new_session() -> None:
    open_envelope = ParseDict(
        _read("trigger_publication/open.json"),
        trigger_pb.StreamTriggersRequest(),
    )
    ready_envelope = ParseDict(
        _read("trigger_publication/ready.json"),
        trigger_pb.StreamTriggersResponse(),
    )

    trigger_validation.validate_stream_request(open_envelope)
    trigger_validation.validate_stream_response(ready_envelope)
    trigger_validation.validate_stream_open_exchange(
        open_envelope.open, ready_envelope.ready
    )

    ready_envelope.ready.session_id = "stale-session"
    with pytest.raises(trigger_validation.TriggerPublicationValidationError):
        trigger_validation.validate_stream_open_exchange(
            open_envelope.open, ready_envelope.ready
        )


def test_uncertain_admission_resolves_without_changing_invocation() -> None:
    request_document = _read("operation_admission/request.json")
    response_document = _read(
        "operation_admission/response-resolved-existing.json"
    )
    vector = _read("operation_admission/fingerprint-vector.json")
    assert isinstance(request_document, dict)
    assert isinstance(response_document, dict)
    assert isinstance(vector, dict)

    request_document["sessionBinding"]["expectedSessionId"] = (
        "session-reconnected-42"
    )
    request_document["admissionMode"] = "ADMISSION_MODE_RESOLVE_ONLY"
    request = ParseDict(request_document, admission_pb.StartOperationRequest())
    response = ParseDict(
        response_document, admission_pb.StartOperationResponse()
    )

    admission_validation.validate_admission_exchange(request, response)
    assert (
        admission_validation.compute_request_fingerprint(request.invocation)
        == vector["fingerprint"]
        == response.record.request_fingerprint
    )
    assert (
        response.disposition
        == admission_pb.ADMISSION_DISPOSITION_RESOLVED_EXISTING
    )


def test_resolve_only_response_cannot_claim_new_admission() -> None:
    request_document = _read("operation_admission/request.json")
    assert isinstance(request_document, dict)
    request_document["admissionMode"] = "ADMISSION_MODE_RESOLVE_ONLY"
    request = ParseDict(request_document, admission_pb.StartOperationRequest())
    response = ParseDict(
        _read("operation_admission/response-accepted-new.json"),
        admission_pb.StartOperationResponse(),
    )

    with pytest.raises(admission_validation.OperationAdmissionValidationError):
        admission_validation.validate_admission_exchange(request, response)


def test_lost_cancel_reply_can_resolve_the_same_atomic_decision() -> None:
    request = ParseDict(
        _read("operation_lifecycle/cancel-request.json"),
        lifecycle_pb.CancelOperationRequest(),
    )
    response = ParseDict(
        _read("operation_lifecycle/cancel-requested.json"),
        lifecycle_pb.CancelOperationResponse(),
    )

    lifecycle_validation.validate_cancel_exchange(request, response)

    stale = copy.deepcopy(response)
    stale.session_id = "stale-session"
    with pytest.raises(lifecycle_validation.OperationLifecycleValidationError):
        lifecycle_validation.validate_cancel_exchange(request, stale)


def test_cancelled_snapshot_requires_an_intervening_state() -> None:
    snapshots = _read("operation_lifecycle/snapshots.json")
    assert isinstance(snapshots, dict)
    cancelled = copy.deepcopy(snapshots["cancelled"])
    assert isinstance(cancelled, dict)
    cancelled["sequence"] = "2"
    cancelled.pop("progress", None)
    snapshot = ParseDict(cancelled, lifecycle_pb.OperationSnapshot())

    with pytest.raises(lifecycle_validation.OperationLifecycleValidationError):
        lifecycle_validation.validate_operation_snapshot(snapshot)


def test_running_cannot_transition_directly_to_cancelled() -> None:
    snapshots = _read("operation_lifecycle/snapshots.json")
    assert isinstance(snapshots, dict)
    running = ParseDict(snapshots["running"], lifecycle_pb.OperationSnapshot())
    cancelled_document = copy.deepcopy(snapshots["cancelled"])
    assert isinstance(cancelled_document, dict)
    cancelled_document["sequence"] = "3"
    cancelled_document["updatedAt"] = "2026-09-19T12:00:02Z"
    cancelled_document.pop("progress", None)
    cancelled = ParseDict(cancelled_document, lifecycle_pb.OperationSnapshot())

    with pytest.raises(lifecycle_validation.OperationLifecycleValidationError):
        lifecycle_validation.validate_snapshot_transition(running, cancelled)


def test_state_transition_cannot_add_progress() -> None:
    snapshots = _read("operation_lifecycle/snapshots.json")
    assert isinstance(snapshots, dict)
    running = ParseDict(snapshots["running"], lifecycle_pb.OperationSnapshot())
    requested_document = copy.deepcopy(snapshots["requested"])
    assert isinstance(requested_document, dict)
    requested_document["sequence"] = "3"
    requested_document["updatedAt"] = "2026-09-19T12:00:02Z"
    progress = requested_document["progress"]
    assert isinstance(progress, dict)
    progress["sequence"] = "3"
    progress["updatedAt"] = "2026-09-19T12:00:02Z"
    requested = ParseDict(requested_document, lifecycle_pb.OperationSnapshot())

    with pytest.raises(lifecycle_validation.OperationLifecycleValidationError):
        lifecycle_validation.validate_snapshot_transition(running, requested)


@pytest.mark.parametrize(
    "case",
    [
        value
        for value in _cases("watchRecovery")
        if "responseSequence" in value
    ],
)
def test_watch_recovery_uses_last_validated_cursor(
    case: dict[str, object],
) -> None:
    request_document = _read("operation_lifecycle/watch-request.json")
    response_document = _read("operation_lifecycle/watch-terminal.json")
    assert isinstance(request_document, dict)
    assert isinstance(response_document, dict)
    request_document["sessionBinding"]["expectedSessionId"] = (
        "session-reconnected-42"
    )
    request_document["afterSequence"] = str(case["afterSequence"])
    response_document["sessionId"] = "session-reconnected-42"
    response_document["snapshot"]["sequence"] = str(case["responseSequence"])
    response_document["updatesSkipped"] = case.get("updatesSkipped", False)
    request = ParseDict(request_document, lifecycle_pb.WatchOperationRequest())
    response = ParseDict(
        response_document, lifecycle_pb.WatchOperationResponse()
    )

    if case["id"] == "cursor-ahead":
        with pytest.raises(
            lifecycle_validation.OperationLifecycleValidationError
        ):
            lifecycle_validation.validate_watch_exchange(request, response)
    else:
        lifecycle_validation.validate_watch_exchange(request, response)


def test_later_watch_response_uses_the_previous_delivered_sequence() -> None:
    request = ParseDict(
        _read("operation_lifecycle/watch-request.json"),
        lifecycle_pb.WatchOperationRequest(),
    )
    response_document = _read("operation_lifecycle/watch-terminal.json")
    snapshots = _read("operation_lifecycle/snapshots.json")
    assert isinstance(response_document, dict)
    assert isinstance(snapshots, dict)
    response_document["snapshot"] = snapshots["progress-100"]
    response_document["updatesSkipped"] = True
    response = ParseDict(
        response_document, lifecycle_pb.WatchOperationResponse()
    )

    lifecycle_validation.validate_watch_exchange(
        request,
        response,
        previous_sequence=2,
    )

    response.updates_skipped = False
    with pytest.raises(lifecycle_validation.OperationLifecycleValidationError):
        lifecycle_validation.validate_watch_exchange(
            request,
            response,
            previous_sequence=2,
        )

    lifecycle_validation.validate_watch_exchange(
        request,
        response,
        previous_sequence=3,
    )

    with pytest.raises(lifecycle_validation.OperationLifecycleValidationError):
        lifecycle_validation.validate_watch_exchange(
            request,
            response,
            previous_sequence=response.snapshot.sequence,
        )


def test_recovery_matrix_never_turns_uncertainty_into_failure_or_retry() -> (
    None
):
    admission = _cases("admissionRecovery")
    unavailable = {
        "ADMISSION_ERROR_REASON_OPERATION_RECORD_UNAVAILABLE",
        "ADMISSION_ERROR_REASON_OPERATION_RECORD_EXPIRED",
    }
    uncertain = [case for case in admission if not case["retainedRecord"]]

    assert {case["expectedReason"] for case in uncertain} == unavailable
    assert all(case["outcome"] == "indeterminate" for case in uncertain)
    assert all(case["mayDispatchAbsentWork"] is False for case in uncertain)


def test_availability_requires_fresh_session_manifest_and_health() -> None:
    prerequisites = _document()["availabilityPrerequisites"]

    assert prerequisites == [
        "transportCurrent",
        "sessionCurrent",
        "generationCurrent",
        "manifestAccepted",
        "healthWatchCurrent",
        "healthServing",
    ]
