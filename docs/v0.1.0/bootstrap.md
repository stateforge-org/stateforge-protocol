# Handshake and version negotiation

Bootstrap turns a provisional local gRPC channel into a fenced SFP session.
The Agent confirms that it reached the endpoint discovered on disk, both peers
select one SFP wire version, and the Provider issues the runtime and session
identifiers required by subsequent procedures.

The StateForge Agent is the gRPC client. The Provider runtime is the gRPC
server. Bootstrap is the first RPC on the shared local channel and no later
SFP procedure may use that channel until the handshake succeeds.

## Interactive walkthrough

```stateforge-procedure
source: procedures/bootstrap.yaml
scenario: success
```

??? info "Bootstrap sequence"

    ```mermaid
    sequenceDiagram
        participant Provider as Provider Process
        participant Agent as StateForge Agent
        Note over Provider,Agent: Validated endpoint descriptor<br/>Provisional local gRPC channel ready
        Agent->>Agent: Build request
        Note over Provider,Agent: Agent runtime ID and software version<br/>Expected Provider instance and endpoint generation<br/>Explicit supported SFP versions
        Agent->>Provider: Bootstrap.Handshake(request)
        Provider->>Provider: Validate request
        Provider->>Provider: Confirm identity fence
        Provider->>Provider: Intersect versions
        alt No mutually supported SFP version
            Provider-->>Agent: UNIMPLEMENTED
            Agent->>Agent: Mark generation incompatible
            Note over Provider,Agent: Retry only after the endpoint generation<br/>or supported versions change
        else Compatible SFP version
            Provider->>Provider: Select highest mutual version
            Provider->>Provider: Issue fresh session ID
            Provider-->>Agent: HandshakeResponse
            Note over Provider,Agent: Provider instance and runtime ID<br/>Confirmed endpoint generation<br/>Selected SFP version and fresh session ID
            Agent->>Agent: Validate response fences
            Agent->>Agent: Bind negotiated session
            Note over Provider,Agent: Handshake succeeded<br/>Continue to Provider Manifest Exchange
        end
    ```

## Who implements Bootstrap

Most Provider developers do not implement this RPC directly.
[StateForge Provider Python](https://github.com/stateforge-org/stateforge-provider-python)
registers the service, validates the request, negotiates the version, and
manages session identifiers for them.

Use `stateforge-protocol` directly when building:

- the StateForge Agent or another conforming SFP client;
- a Provider runtime in a language or framework without an official runtime;
- conformance tooling that exercises the wire contract; or
- the low-level Agent and Provider frameworks themselves.

The package supplies generated messages and gRPC interfaces plus canonical
constants and context-independent validators. It deliberately does not supply
Agent discovery policy, Provider lifecycle state, retry policy, or session
persistence.

## Implementing Bootstrap with Python

Install the generated contracts and the gRPC runtime:

```console
python -m pip install stateforge-protocol grpcio
```

### Python API surface

| Purpose | Python API |
| --- | --- |
| Request and response messages | `bootstrap_pb2.HandshakeRequest` and `bootstrap_pb2.HandshakeResponse` |
| Asynchronous client stub | `bootstrap_pb2_grpc.BootstrapServiceStub` constructed with a `grpc.aio.Channel` |
| Server interface | `bootstrap_pb2_grpc.BootstrapServiceServicer` |
| Server registration | `bootstrap_pb2_grpc.add_BootstrapServiceServicer_to_server` |
| Service identity and procedure limits | `stateforge_protocol.sfp.bootstrap.v1.contract` |
| Context-independent semantic validation | `stateforge_protocol.sfp.bootstrap.v1.validation` |
| Aggregate shared-endpoint ceilings | `stateforge_protocol.sfp.shared_endpoint` |

Import the complete Bootstrap surface from its versioned package:

```python
from stateforge_protocol.sfp import shared_endpoint
from stateforge_protocol.sfp.bootstrap.v1 import (
    bootstrap_pb2,
    bootstrap_pb2_grpc,
    contract,
    validation,
)
```

### Contract sources

| Source | Responsibility |
| --- | --- |
| [`contract.py`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/bootstrap/v1/contract.py) | Owns the canonical service identity, serialized request and response limits, and session-ID length limit. |
| [`validation.py`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/bootstrap/v1/validation.py) | Validates complete Handshake requests, responses, and wire versions, then returns canonical typed values for runtime comparisons. |

Consumers should import these public modules through
`stateforge_protocol.sfp.bootstrap.v1`. The repository-wide private validation
helpers are implementation details; they are not an API for Agent or Provider
runtimes.

Generated protobuf classes do not enforce the StateForge semantic contract by
themselves. Call the public validators explicitly, and enforce serialized byte
limits at each RPC boundary.

### Agent-side asynchronous client

The client starts from an endpoint descriptor that the Agent has already read
and validated. It configures the shared channel, builds and validates the
request, applies a deadline, validates the response, and then compares the
response with Agent-owned discovery and request state.

<!-- fmt: off -->
??? example "Example Bootstrap client"

    ```python
    --8<-- "examples/bootstrap/client.py"
    ```
<!-- fmt: on -->

`UNIMPLEMENTED` means the peers share no SFP wire version. The example maps it
to a distinct exception so the caller can mark this endpoint generation
incompatible instead of retrying it indefinitely. Every other gRPC failure is
re-raised unchanged; callers inspect `AioRpcError.code()` and apply the
status-specific behavior in [Outcomes and recovery](#outcomes-and-recovery).

### Provider-side asynchronous server

The server combines Protocol validation with facts only the live Provider can
know: which instance and generation it serves, which versions its runtime
supports, and whether it is stopping. It uses the same UUIDv4 session-ID
strategy as StateForge Provider Python. An alternative runtime remains
responsible for ensuring its own issuer does not reuse an identifier.

<!-- fmt: off -->
??? example "Example Bootstrap server"

    ```python
    --8<-- "examples/bootstrap/server.py"
    ```
<!-- fmt: on -->

The example installs only Bootstrap to keep the implementation focused. A
production Provider installs every supported SFP service on the same
`grpc.aio.Server`; the aggregate ceilings in `shared_endpoint` allow that
single transport to carry the largest valid request and response while each
service still enforces its narrower procedure limit.

### Run the examples

The example modules are executable documentation stored in the source tree;
they are intentionally not installed by the library wheel. Run them from a
repository checkout:

```console
git clone https://github.com/stateforge-org/stateforge-protocol.git
cd stateforge-protocol
python -m pip install -e .
```

Start the server with a Provider instance UUID and endpoint generation:

```console
python -m examples.bootstrap.server \
  unix:/tmp/stateforge-bootstrap.sock \
  7f7db7d8-68b4-4f71-9769-065b5c4f941c \
  1
```

In another terminal, pass the same values to the client. In a real Agent these
values come from the validated endpoint descriptor rather than command-line
arguments.

```console
python -m examples.bootstrap.client \
  unix:/tmp/stateforge-bootstrap.sock \
  7f7db7d8-68b4-4f71-9769-065b5c4f941c \
  1
```

The repository test suite imports these exact files and exercises successful
negotiation and incompatible versions. The canonical Bootstrap contract tests
separately own invalid-field and exact message-boundary coverage. The
documentation therefore uses executable package APIs without duplicating the
conformance suite.

### Validation order and ownership

| Order | Check | Owner | Why it is not owned elsewhere |
| ---: | --- | --- | --- |
| 1 | Configure aggregate gRPC send and receive ceilings | Both runtimes, using `shared_endpoint` | The shared channel carries every SFP procedure, not only Bootstrap. |
| 2 | Enforce the serialized Bootstrap request or response limit | The sender before sending and the receiver before accepting | Generated protobuf messages and gRPC transport ceilings do not enforce the narrower procedure limit. |
| 3 | Validate message presence, canonical UUIDs, generation range, version shape and uniqueness, and session-ID shape | `stateforge-protocol` through `validation` | Independent implementations must make the same decision from the same message. |
| 4 | Compare the request with the live Provider instance and generation | Provider runtime | Only the serving process knows which endpoint is live now. |
| 5 | Intersect supported versions, check stopping state, and issue a fresh session ID | Provider runtime | These decisions depend on runtime support and installation history. |
| 6 | Validate the constructed response before returning it | Provider runtime using `validation` | A malformed Provider response is an internal contract violation. |
| 7 | Compare the response with the descriptor, request, and offered versions | Agent runtime | Only the Agent owns the discovery observation and request context used for this call. |
| 8 | Bind or reject the session and apply reconnect policy | Agent runtime | Session lifecycle and retry state are local coordination policy. |

Protocol validators return canonical typed values such as UUID objects and
`ProtocolVersion` instances. Runtime implementations should use those values
for contextual comparisons instead of parsing the same fields again.

## Procedure

SFP exposes the unary method
`/stateforge.sfp.bootstrap.v1.BootstrapService/Handshake`. It runs on the local
channel established from a validated endpoint descriptor.

1. The Agent creates a fresh runtime identity for its current process and
   copies the expected Provider instance and endpoint generation from the
   descriptor.
2. The Agent offers every SFP `major.minor` wire version it supports.
3. The Provider validates the request and confirms that the expected instance
   and generation identify the endpoint it is serving.
4. The Provider selects the highest version supported by both peers and creates
   a fresh session identifier.
5. The Agent validates the response against its request and descriptor, then
   binds the channel to the Provider instance, endpoint generation, Provider
   runtime, selected version, and session.

Only after all five steps succeed may the Agent continue to Provider Manifest
Exchange. A successful handshake does not by itself establish a valid manifest,
Provider availability, capability support, or authorization to run operations.

## Request and response

=== "Field reference"

    | Message | Field | Meaning |
    | --- | --- | --- |
    | Request | `agent_runtime.runtime_id` | Canonical lowercase UUIDv4 for the current Agent process. It is not a durable Control Plane Agent identity. |
    | Request | `agent_runtime.software_version` | Nonempty version of the running Agent software. |
    | Request | `expected_provider_instance_id` | Canonical lowercase UUIDv4 copied from the validated endpoint descriptor. It identifies the Provider installation. |
    | Request | `expected_endpoint_generation` | Positive generation copied from the descriptor. It fences endpoint replacement. |
    | Request | `supported_sfp_versions` | Nonempty, duplicate-free list of supported `major.minor` wire versions. Offer order conveys no preference. |
    | Response | `provider_instance_id` | Confirmation of the requested Provider installation. |
    | Response | `endpoint_generation` | Confirmation of the requested endpoint generation. |
    | Response | `selected_sfp_version` | Highest version supported by both peers. It must be one the Agent offered. |
    | Response | `provider_runtime_id` | Canonical lowercase UUIDv4 for the current Provider process. |
    | Response | `session_id` | Opaque identifier issued for this successful handshake and copied unchanged into session-bound procedures. |

=== "Example request"

    ``` { .json .annotate title="HandshakeRequest" }
    {
      "agentRuntime": {
        "runtimeId": "d81855f6-79ac-4b49-9f1a-c9f0985e7c58 (1)",
        "softwareVersion": "0.1.0"
      },
      "expectedProviderInstanceId": "7f7db7d8-68b4-4f71-9769-065b5c4f941c (2)",
      "expectedEndpointGeneration": "4",
      "supportedSfpVersions": [
        {
          "major": 1,
          "minor": 0
        }
      ]
    }
    ```

    1.  Identifies this Agent process, not a durable Control Plane identity.
    2.  Carries the installation fence observed during endpoint discovery;
        `expectedEndpointGeneration` completes that fence.

=== "Example response"

    ``` { .json .annotate title="HandshakeResponse" }
    {
      "providerInstanceId": "7f7db7d8-68b4-4f71-9769-065b5c4f941c (1)",
      "endpointGeneration": "4",
      "selectedSfpVersion": {
        "major": 1,
        "minor": 0
      },
      "providerRuntimeId": "68d818de-3671-471d-a0ba-044cf60e2c8e (2)",
      "sessionId": "session-A (3)"
    }
    ```

    1.  Echoes the installation fence the Agent requested; the endpoint
        generation must also match.
    2.  Identifies the currently running Provider process.
    3.  Fences every later session-bound procedure on this connection.

SFP wire versions contain only unsigned-integer `major` and `minor` components.
The major version is positive and the minor version may be zero. Patch versions
belong to software packages and are deliberately not part of wire negotiation.

## Identity and session fencing

The identifiers serve different purposes and must not be substituted for one
another:

- `provider_instance_id` remains stable for one Provider installation.
- `endpoint_generation` changes when that installation publishes a replacement
  endpoint.
- `provider_runtime_id` identifies the currently executing Provider process.
- `session_id` identifies the negotiated context created by one successful
  handshake.

Every successful handshake creates a session ID that the Provider installation
has not issued before, including after endpoint replacement or process restart.
The value is opaque: consumers preserve its exact case and contents and do not
parse, normalize, or assume it is a UUID. Unrelated Provider installations may
use the same value because session bindings also include the Provider instance.

The context-independent response validator can verify the shape and length of
a session ID, but only the Provider runtime can enforce freshness against IDs it
previously issued. Likewise, only the Agent can confirm that the response
identity, generation, and selected version match the descriptor and request
used for that call.

## Contract ownership and limits

The protobuf source defines the service and message shape. The versioned
`stateforge_protocol.sfp.bootstrap.v1.contract` module owns the canonical
service identity and byte limits, while the adjacent `validation` module owns
context-independent request and response validation.

| Resource | Limit |
| --- | ---: |
| Serialized request | 64 KiB |
| Serialized response | 8 KiB |
| Session ID | 255 Unicode code points |

The request and response limits apply to serialized protobuf bytes at the RPC
boundary. Procedure-specific checks remain required even when the shared gRPC
channel accepts a larger message for another SFP procedure.

The canonical validators require:

- canonical lowercase UUIDv4 Agent runtime, Provider instance, and Provider
  runtime identities;
- an allocated endpoint generation;
- a nonempty Agent software version;
- at least one unique valid SFP wire version; and
- a nonempty session ID within the code-point limit.

Generated protobuf bindings do not run these validators automatically.

## Outcomes and recovery

| Outcome | gRPC status or local result | Required behavior |
| --- | --- | --- |
| Malformed request or invalid field semantics | `INVALID_ARGUMENT` | Correct the request. Do not treat default or malformed values as wildcards. |
| Serialized request or response exceeds its procedure limit | `RESOURCE_EXHAUSTED` | Reject the message before accepting the session. |
| Requested Provider instance or endpoint generation does not identify the serving endpoint | `FAILED_PRECONDITION` | Revalidate discovery and connect to the current endpoint before trying again. |
| No mutually supported SFP wire version | `UNIMPLEMENTED` | Mark that endpoint generation protocol-incompatible. Do not retry it indefinitely without a change. |
| Provider endpoint is stopping before it can create a session | `UNAVAILABLE` | Treat the attempt as transient and follow bounded reconnect policy. |
| Provider constructs an invalid response | `INTERNAL` | Reject the session; the Provider has violated its own contract. |
| Response identity or generation differs from the descriptor, or the selected version was not offered | Local protocol failure | Reject the response and do not bind the channel. |

Transport loss, Provider restart, endpoint-generation change, or channel
replacement requires a new handshake and a fresh session. Late messages from a
superseded session remain stale even if the Provider instance is unchanged.
