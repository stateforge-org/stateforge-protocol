# Handshake and version negotiation

The bootstrap service establishes the identity and negotiated wire version of
an SFP session before operational RPCs are allowed on the channel.

[![Handshake and Version Negotiation sequence diagram](assets/diagrams/handshake-and-version-negotiation.png)](assets/diagrams/handshake-and-version-negotiation.png)

_Select the diagram to open the full-resolution version._

The request binds the provisional channel to the discovered Provider instance
and endpoint generation. The response confirms that identity, chooses exactly
one protocol version, and supplies runtime and session identifiers.

If no wire version overlaps, the Provider returns gRPC `UNIMPLEMENTED`. The
Agent classifies the endpoint generation as incompatible rather than retrying
an unchanged generation indefinitely.
