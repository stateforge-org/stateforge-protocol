# SFP procedure map

StateForge Protocol is defined as a set of related procedures executed over a
multiplexed local gRPC channel. Each page describes a procedure's sequence,
messages, validation rules, state transitions, and failure behavior.

| Procedure | Purpose |
| --- | --- |
| [Endpoint discovery and channel establishment](endpoint-discovery.md) | Publishes, discovers, validates, and connects to a local Provider endpoint. |
| [Handshake and version negotiation](../bootstrap.md) | Confirms endpoint identity and selects one mutually supported SFP wire version. |
| [Provider manifest exchange](provider-manifest.md) | Retrieves and validates the Provider's effective capability declaration. |
| [Health and availability monitoring](health.md) | Maintains Provider availability through the standard gRPC health service. |
| [Capability assessment](capability-assessment.md) | Evaluates whether current runtime evidence supports requested declared operations. |
| [Trigger publication and acknowledgement](triggers.md) | Publishes normalized Provider events and returns durable acknowledgement dispositions. |
| [Operation admission and idempotency](operation-admission.md) | Admits an immutable request exactly once for a given operation identity. |
| [Progress, results, and cancellation](progress-results-cancellation.md) | Streams current state, progress, immutable results, errors, and cancellation outcomes. |
| [Disconnection and recovery](disconnection-recovery.md) | Re-establishes Provider availability and reconciles operation and trigger state safely. |
