# StateForge Protocol

StateForge Protocol (SFP) is the local protocol between the StateForge Agent
and independently running StateForge Provider processes. It uses multiplexed
gRPC so one established HTTP/2 channel can carry handshake, health,
capability, operation, progress, and trigger streams.

This repository is the source of truth for Protocol Buffer schemas and their
generated language contracts. It contains no Agent runtime, Provider runtime,
or vendor-specific integration logic.

## Contract ownership

The `.proto` sources define the wire contract. Generated Python modules are
build artifacts derived from those sources and must not be edited manually.

SFP concerns only local Agent-to-Provider communication. Communication between
the Agent and the StateForge Control Plane belongs to SF-AOP and is outside
this repository.
