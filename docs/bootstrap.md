# Handshake and version negotiation

The bootstrap service establishes the identity and negotiated wire version of
an SFP session before operational RPCs are allowed on the channel.

[![Handshake and Version Negotiation sequence diagram](assets/diagrams/handshake-and-version-negotiation.png)](assets/diagrams/handshake-and-version-negotiation.png)

_Select the diagram to open the full-resolution version._

The request binds the provisional channel to the discovered Provider instance
and endpoint generation. The response confirms that identity, chooses exactly
one protocol version, and supplies runtime and session identifiers.

## Wire contract

SFP exposes the unary method
`/stateforge.sfp.bootstrap.v1.BootstrapService/Handshake`. The protobuf source
defines its message shape; the versioned
`stateforge_protocol.sfp.bootstrap.v1.contract` module is the authoritative
consumer API for limits and the canonical service identifier. The adjacent
`validation` module is the authoritative semantic validator for request and
response envelopes.

| Resource | Limit |
| --- | --- |
| Serialized request | 64 KiB |
| Serialized response | 8 KiB |
| Session ID | 255 Unicode code points |

The request and response limits apply to serialized protobuf bytes at the RPC
boundary. The session ID is an opaque value issued by the Provider and copied
unchanged by consumers; its length is measured in Unicode code points rather
than encoded bytes. Procedure-specific checks remain required even when the
shared gRPC channel accepts a larger message for another SFP procedure.

Every successful Handshake creates a fresh session ID within that Provider
installation. The Provider must not reuse an earlier session ID from the same
installation, including after endpoint replacement or process restart. Session
IDs need not be globally unique across unrelated Provider installations because
all session bindings also carry `provider_instance_id`. Freshness is a
live-context obligation and therefore cannot be established by the
context-independent response validator alone.

The canonical validator requires lowercase UUIDv4 runtime and Provider
identities, an allocated endpoint generation, at least one unique valid SFP
wire version, and a non-empty bounded session identifier. Consumers then apply
only live-context checks: the Provider compares the requested identity and
generation with the endpoint it is serving, while the Agent compares the
response with the descriptor and version offer it used for that call.

If no wire version overlaps, the Provider returns gRPC `UNIMPLEMENTED`. The
Agent classifies the endpoint generation as incompatible rather than retrying
an unchanged generation indefinitely.
