# Trigger publication and acknowledgement

Trigger Publication carries Provider-observed events to the Agent over one
long-lived bidirectional stream. The Provider publishes events declared by its
accepted manifest, and the Agent returns one terminal acknowledgement for each
publication it receives.

The acknowledgement is a delivery boundary. `ACCEPTED_NEW` means the Agent
has durably assumed responsibility for the trigger; it does not mean that a
policy, operation, or business workflow has completed.

## Trigger publication at a glance

The example uses a systemd Provider observing `nginx.service`. It shows which
component owns the relevant state at each step and the exact point where
durable delivery responsibility moves from the Provider to the Agent.

```stateforge-entity-flow
source: trigger-publication-overview.yaml
```

## Interactive walkthrough

```stateforge-procedure
source: triggers.yaml
scenario: success
```

??? info "Trigger publication sequence"

    ```mermaid
    sequenceDiagram
        participant Agent as StateForge Agent
        participant AgentStore as Agent durable store
        participant Provider as Provider runtime
        participant Queue as Provider pending queue

        Agent->>Provider: TriggerStreamOpen<br/>session + manifest + receive window
        Provider->>Provider: Validate active binding
        Provider-->>Agent: TriggerStreamReady<br/>confirmed binding + selected window

        loop While the selected window has capacity
            Queue->>Provider: Pending publication
            Provider-->>Agent: TriggerPublication
            Agent->>Agent: Validate envelope and manifest schema
            alt New publication identity
                Agent->>AgentStore: Atomically accept publication
                Agent-->>Provider: ACCEPTED_NEW
                Provider->>Queue: Remove acknowledged publication
            else Identical accepted publication
                Agent-->>Provider: ACCEPTED_DUPLICATE
                Provider->>Queue: Remove acknowledged replay
            else Invalid or conflicting publication
                Agent-->>Provider: REJECTED + reason
                Provider->>Provider: Apply retry guidance
            end
        end

        opt Connection closes before acknowledgement
            Provider->>Queue: Retain unacknowledged publication
            Agent->>Provider: Open a new current stream
            Queue->>Provider: Replay same ID and content
            Provider-->>Agent: TriggerPublication replay
            Agent-->>Provider: ACCEPTED_DUPLICATE
        end
    ```

## Who implements Trigger Publication

The StateForge Agent is the gRPC client. It opens the stream, validates the
Provider's responses against the current session and manifest, controls the
receive window, records accepted publications, and sends acknowledgements.

The Provider runtime is the gRPC server. It validates the opening request,
confirms the stream binding, retains unacknowledged publications, respects the
selected receive window, and interprets acknowledgement outcomes. A Provider
integration supplies the normalized event payload described by its manifest;
it should not reimplement stream framing or acknowledgement correlation.

The `stateforge-protocol` package supplies the wire types, stable constants,
schema, and context-independent validators. It does not open the stream,
persist publications, evaluate policy, or decide how either runtime schedules
retries.

## Using the Python contract

Install the generated contracts and gRPC runtime:

```console
python -m pip install stateforge-protocol grpcio
```

### Contract sources

| Source | Responsibility |
| --- | --- |
| [`trigger_publication.proto`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/proto/stateforge_protocol/sfp/trigger_publication/v1/trigger_publication.proto) | Defines the bidirectional service, stream envelopes, publication, acknowledgement, rejection, and enum wire values. |
| [`contract.py`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/trigger_publication/v1/contract.py) | Owns the canonical service identity and every procedure-specific message, payload, identifier, retry, and flow-control limit. |
| [`validation.py`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/trigger_publication/v1/validation.py) | Validates messages and opening exchanges, correlates acknowledgements, and computes canonical publication content and fingerprints. |
| [`trigger_publication.schema.json`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/trigger_publication/v1/trigger_publication.schema.json) | Defines the complete lowerCamelCase ProtoJSON projection used for structural validation and conformance tooling. |

### Python API surface

| Purpose | Python API |
| --- | --- |
| Messages and enums | `trigger_publication_pb2` |
| Asynchronous client stub | `trigger_publication_pb2_grpc.TriggerPublicationServiceStub` constructed with a `grpc.aio.Channel` |
| Server interface | `trigger_publication_pb2_grpc.TriggerPublicationServiceServicer` |
| Server registration | `trigger_publication_pb2_grpc.add_TriggerPublicationServiceServicer_to_server` |
| Service identity and limits | `stateforge_protocol.sfp.trigger_publication.v1.contract` |
| Context-independent validation and fingerprints | `stateforge_protocol.sfp.trigger_publication.v1.validation` |

Import the public contract through the versioned package:

```python
from stateforge_protocol.sfp.trigger_publication.v1 import (
    contract,
    trigger_publication_pb2,
    trigger_publication_pb2_grpc,
    validation,
)
```

Use the validator that matches the boundary being processed:

| Boundary | Validator |
| --- | --- |
| Agent-to-Provider envelope | `validate_stream_request` |
| Provider-to-Agent envelope | `validate_stream_response` |
| Opening `open` / `ready` pair | `validate_stream_open_exchange` |
| Publication / acknowledgement pair | `validate_publication_acknowledgement` |
| Duplicate-content comparison | `canonical_publication_content` or `compute_publication_content_fingerprint` |

Generated protobuf classes enforce wire types, not the complete StateForge
contract. Both peers must enforce the byte limits from `contract.py`, call the
public validators, and then apply the live stream, session, manifest, and
persistence checks owned by their runtime.

## Stream directions and opening handshake

SFP exposes one bidirectional method:

```text
/stateforge.sfp.trigger_publication.v1.TriggerPublicationService/StreamTriggers
```

The Agent sends `StreamTriggersRequest` messages. The Provider sends
`StreamTriggersResponse` messages.

| Direction | First message | Later messages |
| --- | --- | --- |
| Agent → Provider | `TriggerStreamOpen` | `TriggerAcknowledgement` |
| Provider → Agent | `TriggerStreamReady` | `TriggerPublication` |

No publication is valid before the Agent's `open` and the matching Provider
`ready` have established the stream.

=== "Field reference"

    | Message | Field | Meaning |
    | --- | --- | --- |
    | Open | `session_binding.expected_provider_instance_id` | Provider installation from the active Bootstrap session. |
    | Open | `session_binding.expected_endpoint_generation` | Current endpoint generation from Bootstrap. |
    | Open | `session_binding.expected_session_id` | Exact active Bootstrap session. |
    | Open | `session_binding.expected_manifest_revision` | Exact accepted manifest whose trigger declarations govern the stream. |
    | Open | `requested_max_in_flight_publications` | Agent receive window from 1 through 1024. |
    | Ready | `provider_instance_id`, `endpoint_generation`, `session_id`, `manifest_revision` | Echoed stream fences that must match the opening request. |
    | Ready | `maximum_in_flight_publications` | Positive Provider-selected window no larger than the Agent requested. |

=== "Example open"

    ``` { .json .annotate title="StreamTriggersRequest · open" }
    {
      "open": {
        "sessionBinding": {
          "expectedProviderInstanceId": "7f7db7d8-68b4-4f71-9769-065b5c4f941c (1)",
          "expectedEndpointGeneration": "4",
          "expectedSessionId": "trigger-session-A (2)",
          "expectedManifestRevision": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa (3)"
        },
        "requestedMaxInFlightPublications": 64
      }
    }
    ```

    1.  Begins the endpoint fence; `expectedEndpointGeneration` completes it.
    2.  Selects one active Bootstrap session.
    3.  Selects the exact trigger declarations and payload schemas for this
        stream.

=== "Example ready"

    ``` { .json .annotate title="StreamTriggersResponse · ready" }
    {
      "ready": {
        "providerInstanceId": "7f7db7d8-68b4-4f71-9769-065b5c4f941c (1)",
        "endpointGeneration": "4",
        "sessionId": "trigger-session-A",
        "manifestRevision": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa (2)",
        "maximumInFlightPublications": 32
      }
    }
    ```

    1.  Echoes the requested endpoint fence; the session must match as well.
    2.  Confirms the same declaration snapshot and completes stream setup.

Empty binding values are invalid rather than wildcards. A stale or inactive
binding fails with `FAILED_PRECONDITION`. A second active trigger stream for
the same session fails with `ALREADY_EXISTS`.

### Flow control

The selected receive window is the maximum number of publications sent but not
yet terminally acknowledged. The Provider may choose a smaller window than the
Agent requested, but never a larger one. When the window is full, the Provider
stops sending and allows gRPC backpressure to reach its pending queue.

The Agent treats a Provider that exceeds the selected window as a local
`RESOURCE_EXHAUSTED` protocol failure and cancels the stream. A larger queue in
either runtime never changes the negotiated wire window.

## Trigger declarations and payloads

Every publishable trigger is a key in the accepted
`ProviderManifest.triggers` map. A declaration pairs its versioned identifier,
such as `stateforge.git/reference.changed@1`, with a JSON Schema Draft 2020-12
object schema.

The publication's `trigger_identifier` must exactly match one of those keys.
The bound `manifest_revision` selects the declaration snapshot, so a
publication has no separate schema-version field and cannot negotiate a schema
independently.

Provider presentation does not participate in publication or acknowledgement.
Trigger policy and event surfaces may improve how a consumer configures or
renders a declared trigger, but the trigger identifier and authoritative
`payload_schema` remain the complete wire contract.
`presentation_revision` is not part of the stream binding or publication
content fingerprint.

The Provider normalizes and validates its payload before publishing. The Agent
validates the decoded payload again against the exact accepted declaration.
Trigger-specific repository, resource, project, or source identity belongs in
that declared payload. It is not a generic SFP envelope field.

## Publication and acknowledgement

Each publication describes one immutable logical event. Each acknowledgement
is one terminal delivery decision correlated by `publication_id`.

=== "Field reference"

    | Message | Field | Meaning |
    | --- | --- | --- |
    | Publication | `publication_id` | Provider-minted canonical UUIDv4 retained unchanged across every retry of this logical event. |
    | Publication | `trigger_identifier` | Exact versioned key selecting the accepted manifest's payload schema. |
    | Publication | `observed_at` | UTC time when the Provider observed the event; not a cross-Provider ordering authority. |
    | Publication | `payload` | Required normalized object satisfying the selected trigger declaration. |
    | Acknowledgement | `publication_id` | Correlates the terminal decision with one publication awaiting acknowledgement on this stream. |
    | Acknowledgement | `disposition` | `ACCEPTED_NEW`, `ACCEPTED_DUPLICATE`, or `REJECTED`. |
    | Rejection | `reason` | Stable machine-readable reason for a rejected publication. |
    | Rejection | `retryable`, `retry_after` | Whether unchanged content may be retried and optional bounded timing guidance. |
    | Rejection | `explanation` | Sanitized diagnostic context; never a machine-readable discriminator. |

=== "Example publication"

    ``` { .json .annotate title="StreamTriggersResponse · publication" }
    {
      "publication": {
        "publicationId": "11111111-1111-4111-8111-111111111111 (1)",
        "triggerIdentifier": "stateforge.git/reference.changed@1 (2)",
        "observedAt": "2026-09-27T08:30:00Z",
        "payload": {
          "repository": "stateforge-org/stateforge-protocol",
          "ref": "refs/heads/mvp/implementation",
          "commitSha": "38d528c560d29a0553d204d7e53662264b82f626"
        }
      }
    }
    ```

    1.  Identifies this logical publication across retransmission and
        reconnect.
    2.  Selects the payload schema from the stream's accepted manifest.

=== "Example accepted"

    ``` { .json .annotate title="StreamTriggersRequest · accepted" }
    {
      "acknowledgement": {
        "publicationId": "11111111-1111-4111-8111-111111111111 (1)",
        "disposition": "TRIGGER_ACKNOWLEDGEMENT_DISPOSITION_ACCEPTED_NEW (2)"
      }
    }
    ```

    1.  Correlates the decision with an outstanding publication on this
        stream.
    2.  Confirms that the Agent durably accepted a new logical trigger before
        sending the acknowledgement.

=== "Example rejected"

    ``` { .json .annotate title="StreamTriggersRequest · rejected" }
    {
      "acknowledgement": {
        "publicationId": "11111111-1111-4111-8111-111111111111",
        "disposition": "TRIGGER_ACKNOWLEDGEMENT_DISPOSITION_REJECTED",
        "rejection": {
          "reason": "TRIGGER_REJECTION_REASON_IDEMPOTENCY_CONFLICT (1)",
          "retryable": false,
          "explanation": "The publication ID was already used with different canonical content."
        }
      }
    }
    ```

    1.  Identifies a permanent conflict without ending an otherwise healthy
        stream.

An acknowledgement is valid only for a publication awaiting its first
terminal acknowledgement on the current stream. An unknown ID, an ID already
acknowledged on that stream, or an ID transmitted only on an earlier stream is
an `INVALID_ARGUMENT` framing violation and terminates the stream. After
reconnect, the Provider must first replay a retained publication before the
Agent can acknowledge it on the new stream.

## Identity and canonical equality

Two different identities answer two different questions:

| Identity | Components | Purpose |
| --- | --- | --- |
| Idempotency key | Authenticated Provider installation + `publication_id` | Determines whether the Agent has already accepted this logical event. |
| Content fingerprint | SHA-256 of canonical publication content | Detects identical replay versus conflicting reuse of that identity. |

Canonical content is RFC 8785 JSON derived from the decoded publication:

| Included | Excluded |
| --- | --- |
| `triggerIdentifier` | `publicationId` |
| `observedAt` | Provider, endpoint, session, and manifest identity |
| `payload` | Stream framing and acknowledgement data |

Changing any included value while reusing the idempotency key is an
`IDEMPOTENCY_CONFLICT`. Transport replacement and a new session do not change
the content comparison. A replacement Provider installation has its own
publication namespace even if it happens to mint the same UUID.

## Acceptance, rejection, and responsibility

| Disposition | Meaning |
| --- | --- |
| `ACCEPTED_NEW` | The Agent atomically recorded a new valid publication and assumed subsequent delivery responsibility before acknowledging it. |
| `ACCEPTED_DUPLICATE` | The same Provider installation and publication identity were already accepted with identical canonical content. No second logical trigger is created. |
| `REJECTED` | The Agent did not accept the publication. The structured rejection states why and whether unchanged content may be useful later. |

!!! important "Acceptance is not business completion"

    An accepted trigger may later cause policy evaluation or operation
    admission, but those outcomes are not part of this acknowledgement. SFP
    transfers delivery responsibility only.

### Rejection reasons

| Reason | Retry unchanged? | Meaning |
| --- | :---: | --- |
| `INVALID_PUBLICATION` | No | The envelope or bounded content is invalid. |
| `TRIGGER_NOT_DECLARED` | No | The identifier is absent from the accepted manifest revision. |
| `PAYLOAD_SCHEMA_VIOLATION` | No | The payload does not satisfy the selected declaration. |
| `IDEMPOTENCY_CONFLICT` | No | The same idempotency key was used with different canonical content. |
| `AGENT_CAPACITY_EXHAUSTED` | Yes | The bounded Agent acceptance queue cannot currently assume responsibility. |
| `DELIVERY_RESPONSIBILITY_UNAVAILABLE` | Yes | The Agent cannot currently establish durable delivery responsibility. |

`retry_after` is allowed only for a retryable rejection, must be positive, and
cannot exceed 24 hours. Retryable means the same canonical publication may be
useful later; it does not authorize changing content under the same
`publication_id`.

## Retry, replay, and ordering

If an acknowledgement is lost, the Provider retains and replays the same
publication ID and canonical content after a new stream becomes ready. If the
Agent already committed the publication, it answers `ACCEPTED_DUPLICATE`.
Replaying an accepted publication never creates a second logical trigger.

Provider persistence across process restart is optional. A Provider that
claims crash replay must persist the complete unacknowledged publication or be
able to reconstruct the exact canonical content from its source. Missing
Provider evidence is not converted into a new publication.

Messages are ordered only as observed on one stream. Publications may be
processed and acknowledged independently, acknowledgements may be returned out
of transmission order, and ordering across Providers, sessions, or trigger
identifiers is undefined. A trigger that needs domain ordering must carry the
required ordering data inside its declared payload.

## Contract limits

| Resource | Limit |
| --- | ---: |
| Agent-to-Provider stream envelope | 64 KiB serialized |
| Provider-to-Agent stream envelope | 2 MiB serialized |
| Canonical payload JSON | 1 MiB |
| Payload nesting | 64 levels |
| Members per payload object or items per array | 256 |
| Payload property name | 128 Unicode code points |
| Payload string value | 65,536 Unicode code points |
| Trigger identifier | 255 Unicode code points |
| Session identifier | 255 Unicode code points |
| Rejection explanation | 1,024 Unicode code points |
| Retry delay | 24 hours |
| Receive window | 1–1,024 publications |

The serialized envelope limits include unknown protobuf fields. Payload bounds
and the declaration's JSON Schema are independent checks; passing one does not
skip the others.

## Stream failures

Failure reporting follows gRPC direction. The Provider server can return a
gRPC status for invalid Agent-originated messages. The Agent client cannot
return a gRPC status to the Provider; it records a local protocol failure and
cancels the RPC instead.

| Detected by | Condition | Result |
| --- | --- | --- |
| Provider | Invalid open framing, bounds, or acknowledgement correlation | `INVALID_ARGUMENT`; terminate the stream. |
| Provider | Stale or mismatched session or manifest binding | `FAILED_PRECONDITION`; terminate the stream. |
| Provider | A second active trigger stream for the same session | `ALREADY_EXISTS`; terminate the new stream. |
| Provider | Bound session becomes unavailable | `UNAVAILABLE`; terminate the stream. |
| Agent | Publication arrives before `ready` | Local `INTERNAL`; cancel the RPC. |
| Agent | `ready` does not echo the requested binding | Local `FAILED_PRECONDITION`; cancel the RPC. |
| Agent | Provider exceeds the selected receive window | Local `RESOURCE_EXHAUSTED`; cancel the RPC. |
| Agent | Invalid or oversized Provider envelope | Corresponding local protocol error; cancel the RPC. |

A validly framed publication-level failure uses `REJECTED` and leaves the
stream open. Stream termination is reserved for framing, binding, flow-control,
or transport failure.

## Privacy

Trigger declarations and publications must not contain credentials or secrets.
Payload schemas should expose only the data required by that trigger contract.
Rejection explanations are sanitized diagnostics: they must not echo raw
payloads, stack traces, credentials, or unnecessary customer data.
