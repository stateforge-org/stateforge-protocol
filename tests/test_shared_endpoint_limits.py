"""Verify the authoritative shared Provider endpoint transport contract."""

from grpc_health.v1 import health_pb2

from stateforge_protocol.sfp import health_contract, shared_endpoint
from stateforge_protocol.sfp.bootstrap.v1 import bootstrap_pb2, contract
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


def _service_name(descriptor, local_name: str) -> str:
    return descriptor.services_by_name[local_name].full_name


def test_inventory_contains_every_service_registered_on_shared_endpoint() -> (
    None
):
    expected = (
        _service_name(bootstrap_pb2.DESCRIPTOR, "BootstrapService"),
        _service_name(health_pb2.DESCRIPTOR, "Health"),
        _service_name(manifest_pb2.DESCRIPTOR, "ManifestService"),
        _service_name(
            capability_assessment_pb2.DESCRIPTOR,
            "CapabilityAssessmentService",
        ),
        _service_name(
            operation_admission_pb2.DESCRIPTOR,
            "OperationAdmissionService",
        ),
        _service_name(
            operation_lifecycle_pb2.DESCRIPTOR,
            "OperationLifecycleService",
        ),
        _service_name(
            trigger_publication_pb2.DESCRIPTOR,
            "TriggerPublicationService",
        ),
    )
    actual = tuple(
        procedure.service_name
        for procedure in shared_endpoint.PROCEDURE_LIMITS
    )

    assert actual == expected
    assert len(actual) == len(set(actual))
    assert actual[0] == contract.SERVICE_NAME
    assert actual[1] == health_contract.STANDARD_HEALTH_SERVICE
    assert set(actual) == {
        health_contract.STANDARD_HEALTH_SERVICE,
        *health_contract.SFP_SERVICE_NAMES,
    }


def test_shared_provider_endpoint_ceiling_is_derived_from_inventory() -> None:
    receive_ceiling = max(
        procedure.max_request_bytes
        for procedure in shared_endpoint.PROCEDURE_LIMITS
    )
    send_ceiling = max(
        procedure.max_response_bytes
        for procedure in shared_endpoint.PROCEDURE_LIMITS
    )

    assert receive_ceiling == shared_endpoint.MAX_PROVIDER_RECEIVE_BYTES
    assert send_ceiling == shared_endpoint.MAX_PROVIDER_SEND_BYTES
    assert receive_ceiling == 8 * 1024 * 1024
    assert send_ceiling == 16 * 1024 * 1024


def test_shared_ceiling_does_not_replace_per_rpc_limits() -> None:
    request_limits = {
        procedure.max_request_bytes
        for procedure in shared_endpoint.PROCEDURE_LIMITS
    }
    response_limits = {
        procedure.max_response_bytes
        for procedure in shared_endpoint.PROCEDURE_LIMITS
    }

    assert len(request_limits) > 1
    assert len(response_limits) > 1
    for procedure in shared_endpoint.PROCEDURE_LIMITS:
        assert (
            procedure.max_request_bytes
            <= shared_endpoint.MAX_PROVIDER_RECEIVE_BYTES
        )
        assert (
            procedure.max_response_bytes
            <= shared_endpoint.MAX_PROVIDER_SEND_BYTES
        )
