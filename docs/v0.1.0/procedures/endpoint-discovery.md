# Endpoint discovery and channel establishment

This procedure establishes the provisional local gRPC channel used by all
later SFP procedures. The Provider owns its stable instance identity, starts
its server, and atomically publishes a generation-specific endpoint. The Agent
Library monitors the discovery directory, validates the descriptor and local
filesystem boundary, then establishes or reuses the matching channel.

## Descriptor v1 contract

Endpoint discovery is a versioned local-filesystem contract. It deliberately
does not add a protobuf service: the descriptor exists so the Agent can locate
the Provider's multiplexed gRPC endpoint before Bootstrap is available.

The Provider atomically publishes
`<provider_instance_id>.sfp.json` with mode `0640`. The document is UTF-8 JSON,
is limited to 4 KiB, rejects duplicate or unknown fields, and has this exact
shape:

```json
{
  "schema_version": "1",
  "provider_instance_id": "7f7db7d8-68b4-4f71-9769-065b5c4f941c",
  "endpoint_generation": 4,
  "transport": {
    "type": "unix",
    "socket_path": "/run/stateforge-agent/providers/7f7db7d8-68b4-4f71-9769-065b5c4f941c.4.sock"
  }
}
```

| Field | Contract |
| --- | --- |
| `schema_version` | Exactly `"1"`. |
| `provider_instance_id` | Canonical lowercase UUIDv4 identifying the Provider installation. |
| `endpoint_generation` | Integer from 1 through 2^63 − 1, allocated monotonically for that installation. |
| `transport.type` | Exactly `"unix"`. |
| `transport.socket_path` | Non-empty absolute Unix path. Its filename is `<provider_instance_id>.<endpoint_generation>.sock`. |

The socket has mode `0660`. Both artifacts are direct children of the same
protected discovery directory. The Agent validates the descriptor's file
type, ownership, group, mode, size, canonical filename, and exact socket
binding without following symbolic links. It also validates that the socket
is a Unix-domain socket with matching owner and group before connecting.

The versioned constants, document model, parser, serializer, and JSON Schema
are distributed by `stateforge-protocol` from
`stateforge_protocol.sfp.endpoint_discovery.v1`. Provider and Agent runtimes
consume that contract; they do not redefine it. Runtime directory creation,
atomic publication, filesystem race protection, monitoring, and cleanup stay
with the owning runtime.

[![Endpoint Discovery and Channel Establishment sequence diagram](../assets/diagrams/endpoint-discovery-and-channel-establishment.png)](../assets/diagrams/endpoint-discovery-and-channel-establishment.png)

_Select the diagram to open the full-resolution version._
