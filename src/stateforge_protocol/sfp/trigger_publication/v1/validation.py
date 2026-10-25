"""Validate the complete SFP Trigger Publication v1 contract."""

from __future__ import annotations

import hashlib
from typing import Final

from stateforge_protocol.sfp import _validation
from stateforge_protocol.sfp.trigger_publication.v1 import (
    contract,
    trigger_publication_pb2,
)

__all__ = [
    "TriggerPublicationValidationError",
    "canonical_publication_content",
    "compute_publication_content_fingerprint",
    "validate_publication_acknowledgement",
    "validate_stream_open",
    "validate_stream_open_exchange",
    "validate_stream_ready",
    "validate_stream_request",
    "validate_stream_response",
    "validate_trigger_acknowledgement",
    "validate_trigger_publication",
]

_SCHEMA: Final = _validation.PackagedSchema(
    package="stateforge_protocol.sfp.trigger_publication.v1",
    resource="trigger_publication.schema.json",
    contract_name="Trigger Publication v1",
)


class TriggerPublicationValidationError(ValueError):
    """Report invalid Trigger Publication data without exposing payloads."""


_VALIDATION: Final = _validation.ValidationContext(
    TriggerPublicationValidationError
)


def validate_stream_request(
    request: trigger_publication_pb2.StreamTriggersRequest,
) -> None:
    """Validate one Agent-to-Provider stream envelope."""
    request = _VALIDATION.require_instance(
        request,
        trigger_publication_pb2.StreamTriggersRequest,
        "request: expected StreamTriggersRequest",
    )
    _VALIDATION.require_serialized_size(
        request,
        maximum_bytes=contract.MAX_REQUEST_BYTES,
        path="request",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, request, "triggerStreamRequest", "request"
    )


def validate_stream_response(
    response: trigger_publication_pb2.StreamTriggersResponse,
) -> None:
    """Validate one Provider-to-Agent stream envelope."""
    response = _VALIDATION.require_instance(
        response,
        trigger_publication_pb2.StreamTriggersResponse,
        "response: expected StreamTriggersResponse",
    )
    _VALIDATION.require_serialized_size(
        response,
        maximum_bytes=contract.MAX_RESPONSE_BYTES,
        path="response",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, response, "triggerStreamResponse", "response"
    )
    selected = response.WhichOneof("message")
    if selected == "ready":
        validate_stream_ready(response.ready)
    elif selected == "publication":
        validate_trigger_publication(response.publication)


def validate_stream_open(
    open_message: trigger_publication_pb2.TriggerStreamOpen,
) -> None:
    """Validate an opening message and its complete session binding."""
    open_message = _VALIDATION.require_instance(
        open_message,
        trigger_publication_pb2.TriggerStreamOpen,
        "open: expected TriggerStreamOpen",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, open_message, "triggerStreamOpen", "open"
    )


def validate_stream_ready(
    ready: trigger_publication_pb2.TriggerStreamReady,
) -> None:
    """Validate a Provider's stream-ready response."""
    ready = _VALIDATION.require_instance(
        ready,
        trigger_publication_pb2.TriggerStreamReady,
        "ready: expected TriggerStreamReady",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, ready, "triggerStreamReady", "ready"
    )


def validate_stream_open_exchange(
    open_message: trigger_publication_pb2.TriggerStreamOpen,
    ready: trigger_publication_pb2.TriggerStreamReady,
) -> None:
    """Validate current-session correlation for the stream handshake."""
    validate_stream_open(open_message)
    validate_stream_ready(ready)
    binding = open_message.session_binding
    for expected, actual, field in (
        (
            binding.expected_provider_instance_id,
            ready.provider_instance_id,
            "Provider instance identity",
        ),
        (
            binding.expected_endpoint_generation,
            ready.endpoint_generation,
            "endpoint generation",
        ),
        (binding.expected_session_id, ready.session_id, "session identity"),
        (
            binding.expected_manifest_revision,
            ready.manifest_revision,
            "manifest revision",
        ),
    ):
        _VALIDATION.require_equal(
            actual, expected, f"stream exchange: {field} mismatch"
        )
    _VALIDATION.require(
        ready.maximum_in_flight_publications
        <= open_message.requested_max_in_flight_publications,
        "stream exchange: Provider selected a larger receive window",
    )


def validate_trigger_publication(
    publication: trigger_publication_pb2.TriggerPublication,
) -> None:
    """Validate one immutable Provider-originated publication."""
    publication = _VALIDATION.require_instance(
        publication,
        trigger_publication_pb2.TriggerPublication,
        "publication: expected TriggerPublication",
    )
    _VALIDATION.require_bounded_protojson_container(
        publication.payload,
        maximum_depth=contract.MAX_PAYLOAD_JSON_DEPTH,
        maximum_entries=contract.MAX_PAYLOAD_CONTAINER_ENTRIES,
        nesting_message="publication: payload nesting limit exceeded",
        container_message="publication: payload container limit exceeded",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA, publication, "triggerPublication", "publication"
    )
    payload = _VALIDATION.project_message(publication, "publication").get(
        "payload"
    )
    _VALIDATION.canonicalize_json(
        payload,
        maximum_bytes=contract.MAX_CANONICAL_PAYLOAD_BYTES,
        limit_message="publication: canonical payload limit exceeded",
        invalid_message="publication: payload is not canonical JSON",
    )
    canonical_publication_content(publication)


def validate_trigger_acknowledgement(
    acknowledgement: trigger_publication_pb2.TriggerAcknowledgement,
) -> None:
    """Validate one terminal acknowledgement decision."""
    acknowledgement = _VALIDATION.require_instance(
        acknowledgement,
        trigger_publication_pb2.TriggerAcknowledgement,
        "acknowledgement: expected TriggerAcknowledgement",
    )
    _VALIDATION.validate_message_schema(
        _SCHEMA,
        acknowledgement,
        "triggerAcknowledgement",
        "acknowledgement",
    )


def validate_publication_acknowledgement(
    publication: trigger_publication_pb2.TriggerPublication,
    acknowledgement: trigger_publication_pb2.TriggerAcknowledgement,
) -> None:
    """Validate publication identity correlation for one acknowledgement."""
    validate_trigger_publication(publication)
    validate_trigger_acknowledgement(acknowledgement)
    _VALIDATION.require_equal(
        acknowledgement.publication_id,
        publication.publication_id,
        "acknowledgement: publication identity mismatch",
    )


def canonical_publication_content(
    publication: trigger_publication_pb2.TriggerPublication,
) -> bytes:
    """Return canonical logical content excluding delivery identity."""
    publication = _VALIDATION.require_instance(
        publication,
        trigger_publication_pb2.TriggerPublication,
        "publication: expected TriggerPublication",
    )
    projected = _VALIDATION.project_message(publication, "publication")
    projected.pop("publicationId", None)
    return _VALIDATION.canonicalize_json(
        projected,
        maximum_bytes=contract.MAX_RESPONSE_BYTES,
        limit_message="publication: canonical content limit exceeded",
        invalid_message="publication: content is not canonical JSON",
    )


def compute_publication_content_fingerprint(
    publication: trigger_publication_pb2.TriggerPublication,
) -> str:
    """Return the stable digest used to detect conflicting ID reuse."""
    digest = hashlib.sha256(canonical_publication_content(publication))
    return f"sha256:{digest.hexdigest()}"
