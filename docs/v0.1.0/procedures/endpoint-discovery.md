# Endpoint discovery and channel establishment

Before Bootstrap can prove which Provider is on the other side, the Agent must
find a local endpoint that is safe to contact. The Provider binds a
generation-specific Unix socket and atomically publishes a small descriptor.
The Agent validates the complete filesystem observation, then opens a
provisional gRPC channel to that exact endpoint generation.

Endpoint discovery is a versioned filesystem contract, not an RPC. The channel
it produces remains untrusted until
[Handshake and version negotiation](../bootstrap.md) succeeds.

## Endpoint discovery at a glance

The Provider publishes one generation-specific endpoint. The Agent trusts it
only after the descriptor and Unix socket pass their separate validation
boundaries.

```stateforge-entity-flow
source: endpoint-discovery-overview.yaml
```

## Interactive walkthrough

```stateforge-procedure
source: endpoint-discovery.yaml
scenario: success
```

??? info "Endpoint discovery sequence"

    ```mermaid
    sequenceDiagram
        participant Provider as Provider Process
        participant Directory as Discovery Directory
        participant Socket as Unix Socket
        participant Agent as StateForge Agent

        Provider->>Provider: Retain installation UUID<br/>Allocate endpoint generation
        Provider->>Socket: Bind generation-specific socket
        Provider->>Directory: Atomically publish final descriptor
        Directory-->>Agent: Filesystem notification (hint only)
        Agent->>Directory: Open and read final descriptor
        Agent->>Agent: Validate bounded JSON and filename correlation
        Agent->>Socket: Validate path, type, owner, group, and mode

        alt Descriptor and socket are trusted
            Agent->>Socket: Open provisional gRPC channel
            Socket->>Provider: Local HTTP/2 connection
            Note over Provider,Agent: Continue to Bootstrap<br/>Peer identity is not yet proven
        else Descriptor violates the Protocol contract
            Agent->>Agent: Reject the observation
            Note over Provider,Agent: No channel is created
        else Filesystem or socket boundary is unsafe
            Agent->>Agent: Reject the observation
            Note over Provider,Agent: Valid JSON alone is not trusted
        end
    ```

## Who implements endpoint discovery

Provider authors using
[StateForge Provider Python](https://github.com/stateforge-org/stateforge-provider-python)
do not publish descriptors by hand. The runtime owns the Provider identity,
socket, endpoint generation, atomic publication, and cleanup. The StateForge
Agent owns directory monitoring, race-safe validation, channel creation, and
replacement handling.

Use `stateforge-protocol` directly when building:

- another Provider runtime or Agent implementation;
- tooling that reads or emits endpoint descriptors; or
- conformance tests for the local discovery boundary.

The package defines the document shape, names, limits, and context-independent
validation. It does not create directories, inspect filesystem ownership,
watch for changes, bind sockets, or decide retry policy.

## Using the Python contract

Install the versioned contract package:

```console
python -m pip install stateforge-protocol
```

### Contract sources

| Source | Responsibility |
| --- | --- |
| [`contract.py`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/endpoint_discovery/v1/contract.py) | Owns descriptor constants, limits, canonical names, the validated `EndpointDescriptor` model, deterministic serialization, and `parse_descriptor`. |
| [`endpoint_descriptor.schema.json`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/endpoint_discovery/v1/endpoint_descriptor.schema.json) | Describes the same descriptor document for schema-aware tooling and conformance checks. |

Endpoint discovery v1 has no separate `validation.py`. Parsing the JSON
document and validating its complete context-independent contract are one
operation in `contract.parse_descriptor`. Host filesystem and socket checks
cannot be performed from document bytes, so they remain with the Agent runtime.

### Python API surface

| Purpose | Python API |
| --- | --- |
| Validated descriptor model | `contract.EndpointDescriptor` |
| Parse and validate descriptor bytes | `contract.parse_descriptor` |
| Canonical descriptor filename | `contract.descriptor_filename` |
| Canonical socket filename | `contract.socket_filename` |
| Recover identity from a descriptor filename | `contract.provider_instance_id_from_descriptor_filename` |
| Schema, modes, size, and generation limits | `stateforge_protocol.sfp.endpoint_discovery.v1.contract` |
| Machine-readable document contract | `endpoint_descriptor.schema.json` in the same package |

The same model serializes the Provider's document and parses the Agent's
bounded read:

```python
from uuid import UUID

from stateforge_protocol.sfp.endpoint_discovery.v1 import contract

provider_instance_id = UUID("7f7db7d8-68b4-4f71-9769-065b5c4f941c")
generation = 4
descriptor = contract.EndpointDescriptor(
    provider_instance_id=provider_instance_id,
    endpoint_generation=generation,
    socket_path=(
        "/run/stateforge-agent/providers/"
        f"{contract.socket_filename(provider_instance_id, generation)}"
    ),
)

published_bytes = descriptor.to_json_bytes()
observed_descriptor = contract.parse_descriptor(published_bytes)
```

`parse_descriptor` validates bytes, not the host filesystem. A successful
parse does not prove that the file is safely owned, that the socket exists, or
that the socket belongs to the same trusted boundary. Those checks remain the
Agent runtime's responsibility.

## Descriptor v1 contract

The Provider atomically publishes `<provider_instance_id>.sfp.json` as UTF-8
JSON. The final descriptor uses mode `0640`, is limited to 4 KiB, and rejects
duplicate, missing, or unknown fields.

=== "Field reference"

    | Field | Contract |
    | --- | --- |
    | `schema_version` | Exactly `"1"`. |
    | `provider_instance_id` | Canonical lowercase UUIDv4 identifying one Provider installation. |
    | `endpoint_generation` | Integer from 1 through 2^63 - 1, allocated monotonically for that installation. |
    | `transport.type` | Exactly `"unix"`. |
    | `transport.socket_path` | Non-empty absolute Unix path. The filename is `<provider_instance_id>.<endpoint_generation>.sock`. |

=== "Example descriptor"

    ``` { .json .annotate title="Endpoint descriptor" }
    {
      "schema_version": "1 (1)",
      "provider_instance_id": "7f7db7d8-68b4-4f71-9769-065b5c4f941c (2)",
      "endpoint_generation": 4,
      "transport": {
        "type": "unix",
        "socket_path": "/run/stateforge-agent/providers/7f7db7d8-68b4-4f71-9769-065b5c4f941c.4.sock (3)"
      }
    }
    ```

    1.  Selects the only descriptor schema defined by this release.
    2.  Identifies the Provider installation and must match the descriptor
        filename.
    3.  Names the generation-specific socket and must agree with both the
        Provider identity and `endpoint_generation`.

The Unix socket uses mode `0660`. The descriptor and socket are direct children
of the same protected discovery directory. A descriptor's stable filename
identifies the Provider installation; the generation-specific socket filename
identifies one published endpoint.

## Publication and validation order

| Order | Action | Owner | Required result |
| ---: | --- | --- | --- |
| 1 | Retain a stable Provider instance UUID and allocate a higher endpoint generation | Provider runtime | This endpoint cannot be confused with another installation or an older endpoint. |
| 2 | Bind the canonical generation-specific Unix socket with mode `0660` | Provider runtime | The transport exists before it is advertised. |
| 3 | Serialize the canonical descriptor, write a complete temporary file, and atomically replace the stable final filename with mode `0640` | Provider runtime | Watchers can observe either the previous complete descriptor or the new complete descriptor, never a partial document. |
| 4 | Treat a filesystem notification only as a hint and reopen the final descriptor path | Agent runtime | Validation uses the current final artifact rather than event payloads or temporary names. |
| 5 | Bound the read, reject links and unsafe file types or metadata, and parse the bytes with `contract.parse_descriptor` | Agent runtime using Protocol constants | The document and its filesystem container both pass their respective boundaries. |
| 6 | Correlate the descriptor filename, Provider identity, endpoint generation, and canonical socket filename | Agent runtime | Every observed value identifies the same endpoint. |
| 7 | Validate the socket type, ownership, group, and mode without following symbolic links | Agent runtime | An attacker-controlled path cannot be treated as the Provider endpoint. |
| 8 | Open or reuse the matching channel and carry the validated discovery fences into Bootstrap | Agent runtime | The channel remains provisional until the peer confirms the same identity and generation. |

The Protocol package owns values that independent implementations must agree
on. Secure directory creation, atomic filesystem operations, race resistance,
monitoring, channel lifecycle, and cleanup remain runtime responsibilities.

## Outcomes and replacement

| Observation | Agent behavior |
| --- | --- |
| Canonical descriptor and trusted matching socket | Open or reuse the provisional channel, then run Bootstrap. |
| Empty, oversized, malformed, ambiguous, or unsupported descriptor | Reject the observation before selecting a socket. |
| Valid document with unsafe file or socket metadata | Reject the observation; valid JSON does not cross the filesystem trust boundary. |
| Higher endpoint generation | Validate the replacement independently, retire the previous observation, and run Bootstrap on a new provisional channel. |
| Lower endpoint generation | Treat the observation as stale and do not replace a newer validated endpoint. |

A new endpoint generation never inherits session trust. Bootstrap must confirm
the replacement, and later recovery procedures decide whether retained
operation or trigger state may be reconciled.
