# Disconnection and recovery

A transport loss does not implicitly cancel Provider work. The Agent marks the
Provider unavailable, reconnects with bounded backoff, repeats session
establishment, and reconciles operations and trigger acknowledgements. Lost
operation state remains indeterminate and must not be retried automatically.

[![Disconnection and Recovery sequence diagram](../assets/diagrams/disconnection-and-recovery.png)](../assets/diagrams/disconnection-and-recovery.png)

_Select the diagram to open the full-resolution version._
