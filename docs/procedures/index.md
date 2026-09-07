# SFP procedure map

StateForge Protocol is defined as a set of related procedures executed over a
multiplexed local gRPC channel. The diagrams in this section are the original
sequence diagrams maintained with the StateForge Protocol specification.

| Procedure | Purpose |
| --- | --- |
| [Endpoint discovery and channel establishment](endpoint-discovery.md) | Publishes, discovers, validates, and connects to a local Provider endpoint. |
| [Handshake and version negotiation](../bootstrap.md) | Confirms endpoint identity and selects one mutually supported SFP wire version. |
| [Provider manifest exchange](provider-manifest.md) | Retrieves and validates the Provider's effective capability declaration. |
| [Health and availability monitoring](health.md) | Maintains Provider availability through the standard gRPC health service. |
| [Capability assessment](capability-assessment.md) | Evaluates whether a Provider can perform requested operations against a target. |
| [Trigger publication and acknowledgement](triggers.md) | Publishes normalized Provider events and returns durable acknowledgement dispositions. |
| [Operation admission and idempotency](operation-admission.md) | Admits an immutable request exactly once for a given operation identity. |
| [Backup preparation](backup-preparation.md) | Prepares staged data or a recoverable Provider reference for the Agent SDK. |
| [Disaster-recovery execution](disaster-recovery.md) | Reconstructs a target from staged backup data or a Provider reference. |
| [Progress, results, and cancellation](progress-results-cancellation.md) | Streams current state, progress, immutable results, errors, and cancellation outcomes. |
| [Disconnection and recovery](disconnection-recovery.md) | Re-establishes Provider availability and reconciles operation and trigger state safely. |
