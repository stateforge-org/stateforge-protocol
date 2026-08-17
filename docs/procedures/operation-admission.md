# Operation admission and idempotency

The Agent assigns an immutable `operation_id` and submits one operation
envelope. The Developer RPC Library validates it against the active manifest,
computes its canonical fingerprint, and uses the Provider's operation registry
to create a new admission or resolve the existing one without duplicate
execution.

[![Operation Admission and Idempotency sequence diagram](../assets/diagrams/operation-admission-and-idempotency.png)](../assets/diagrams/operation-admission-and-idempotency.png)

_Select the diagram to open the full-resolution version._
