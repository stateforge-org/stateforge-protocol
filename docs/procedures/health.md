# Health and availability monitoring

The Provider exposes the standard gRPC health service. The Agent watches the
versioned operational service over the established multiplexed channel and
updates Provider availability when the stream changes, fails, or recovers.

[![Health and Availability Monitoring sequence diagram](../assets/diagrams/health-and-availability-monitoring.png)](../assets/diagrams/health-and-availability-monitoring.png)

_Select the diagram to open the full-resolution version._
