# StateForge Protocol

StateForge Protocol (SFP) is the local protocol between the StateForge Agent
and independently running StateForge Provider processes. It uses multiplexed
gRPC so one established HTTP/2 channel can carry handshake, health,
capability, operation, progress, and trigger streams.

SFP gives both sides a versioned, typed contract for discovering a Provider,
learning what it exposes, deciding what it can do in its current environment,
executing declared operations, receiving triggers, and recovering safely after
a connection is lost.

## Protocol flow

1. The Provider publishes an endpoint descriptor and the Agent establishes a
   local gRPC channel.
2. Bootstrap confirms endpoint identity, negotiates a protocol version, and
   establishes a fenced session.
3. The Agent retrieves the Provider manifest, including its operations,
   triggers, and their schemas.
4. Health monitoring establishes process-wide availability, while capability
   assessment evaluates operation support for a specific runtime context.
5. The Agent admits operations and consumes their lifecycle updates, while
   Providers publish triggers and receive acknowledgement dispositions.
6. Reconnection creates a new session and reconciles retained operation and
   trigger state without accepting stale messages.

[![StateForge Protocol flow from endpoint discovery through recovery](assets/diagrams/protocol-flow.svg)](assets/diagrams/protocol-flow.svg)

## Contract ownership

The `.proto` sources define the RPC services and messages. Packaged schemas
and public validation APIs define the rules that cannot be expressed in
Protocol Buffers alone.

> Generated Python modules are derived build artifacts
and must not be edited manually.

The repository also ships conformance fixtures and verification tooling so
Agent and Provider implementations can prove that they interpret the same
contract consistently.

## Read the protocol

- Start with the [SFP procedure map](procedures/index.md) for the complete
  protocol sequence.
- Use the [generated Python contracts](reference/python-contracts.md) when
  implementing an Agent or Provider in Python.
- See [conformance coverage](reference/conformance-coverage.md) for the
  verification surface required of packaged releases and consumers.
