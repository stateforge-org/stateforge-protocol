# Health and operational eligibility conformance vectors

These vectors describe StateForge's use of the standard `grpc.health.v1`
contract. They do not define another health service or implement an Agent or
Provider runtime.

- `registry.json` fixes the empty Provider-wide health key used by the Agent,
  the exact diagnostic service names, and standard empty/named/unknown lookup
  outcomes.
- `scenarios.json` covers Provider lifecycle, Agent-derived eligibility,
  Watch loss and recovery, stale-stream fencing, admitted-work preservation,
  backpressure, and diagnostic bounds.

The installed-artifact verifier reads these files from the built wheel. The
source contract tests also compare every registered name with its generated
SFP service descriptor. A future procedure adds its service name to the
registry only when that service is actually hosted on the multiplexed SFP
channel.
