"""Verify shared transport ceilings remain derived from per-RPC contracts."""

from stateforge_protocol.sfp.capability_assessment.v1 import (
    contract as capability_assessment,
)
from stateforge_protocol.sfp.manifest.v1 import contract as manifest
from stateforge_protocol.sfp.operation_admission.v1 import (
    contract as operation_admission,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    contract as operation_lifecycle,
)
from stateforge_protocol.sfp.trigger_publication.v1 import (
    contract as trigger_publication,
)

_PROCEDURES = (
    manifest,
    capability_assessment,
    operation_admission,
    operation_lifecycle,
    trigger_publication,
)


def test_shared_provider_endpoint_ceiling_is_derived_from_procedures() -> None:
    receive_ceiling = max(
        contract.MAX_REQUEST_BYTES for contract in _PROCEDURES
    )
    send_ceiling = max(contract.MAX_RESPONSE_BYTES for contract in _PROCEDURES)

    assert receive_ceiling == 8 * 1024 * 1024
    assert send_ceiling == 16 * 1024 * 1024


def test_shared_ceiling_does_not_replace_per_rpc_limits() -> None:
    request_limits = {contract.MAX_REQUEST_BYTES for contract in _PROCEDURES}
    response_limits = {contract.MAX_RESPONSE_BYTES for contract in _PROCEDURES}

    assert len(request_limits) > 1
    assert len(response_limits) > 1
