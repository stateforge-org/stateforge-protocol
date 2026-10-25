"""Classify cross-procedure SFP reconnection identity transitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from stateforge_protocol.sfp import primitives
from stateforge_protocol.sfp.bootstrap.v1 import contract as bootstrap_contract
from stateforge_protocol.sfp.endpoint_discovery.v1 import (
    contract as discovery_contract,
)

__all__ = [
    "EndpointSessionIdentity",
    "RecoveryContractError",
    "RecoveryKind",
    "classify_recovery",
]


class RecoveryContractError(ValueError):
    """Report an impossible or stale recovery identity transition."""


class RecoveryKind(StrEnum):
    """Describe continuity across two independently validated sessions."""

    SAME_PROCESS_RECONNECT = "same_process_reconnect"
    ENDPOINT_REPLACED = "endpoint_replaced"
    PROCESS_RESTARTED = "process_restarted"
    INSTALLATION_REPLACED = "installation_replaced"

    @property
    def may_reconcile_previous_state(self) -> bool:
        """Return whether the new endpoint may prove retained prior state."""
        return self is not RecoveryKind.INSTALLATION_REPLACED

    @property
    def requires_resolve_only(self) -> bool:
        """Return whether uncertain admission crossed a generation boundary."""
        return self in {
            RecoveryKind.ENDPOINT_REPLACED,
            RecoveryKind.PROCESS_RESTARTED,
        }


@dataclass(frozen=True, slots=True)
class EndpointSessionIdentity:
    """Hold the validated identity fields needed to classify reconnects."""

    provider_instance_id: UUID
    endpoint_generation: int
    provider_runtime_id: UUID
    session_id: str

    def __post_init__(self) -> None:
        """Reject identity values outside their owning Protocol contracts."""
        for name in ("provider_instance_id", "provider_runtime_id"):
            value = getattr(self, name)
            if (
                not isinstance(value, UUID)
                or value.version != primitives.CANONICAL_UUID_VERSION
            ):
                raise RecoveryContractError(
                    f"{name} must be a canonical UUIDv4"
                )
        if not discovery_contract.is_allocated_endpoint_generation(
            self.endpoint_generation
        ):
            raise RecoveryContractError(
                "endpoint_generation must be allocated"
            )
        if not (
            isinstance(self.session_id, str)
            and 1
            <= len(self.session_id)
            <= bootstrap_contract.MAX_SESSION_ID_CODE_POINTS
        ):
            raise RecoveryContractError(
                "session_id is outside the SFP v1 contract"
            )


def classify_recovery(
    previous: EndpointSessionIdentity,
    current: EndpointSessionIdentity,
) -> RecoveryKind:
    """Classify one new session without treating stale identity as recovery."""
    if current.provider_instance_id != previous.provider_instance_id:
        return RecoveryKind.INSTALLATION_REPLACED
    if current.session_id == previous.session_id:
        raise RecoveryContractError(
            "a recovered channel must negotiate a new session identity"
        )
    if current.endpoint_generation < previous.endpoint_generation:
        raise RecoveryContractError(
            "a recovered endpoint generation cannot move backward"
        )
    if current.endpoint_generation == previous.endpoint_generation:
        if current.provider_runtime_id != previous.provider_runtime_id:
            raise RecoveryContractError(
                "one endpoint generation cannot identify two runtimes"
            )
        return RecoveryKind.SAME_PROCESS_RECONNECT
    return (
        RecoveryKind.ENDPOINT_REPLACED
        if current.provider_runtime_id == previous.provider_runtime_id
        else RecoveryKind.PROCESS_RESTARTED
    )
