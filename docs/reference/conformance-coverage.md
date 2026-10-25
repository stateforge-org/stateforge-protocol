# SFP conformance coverage

The Protocol release gate derives its expected surface from protobuf sources,
the shared endpoint inventory, and the packaged conformance catalog at
`stateforge_protocol/fixtures/conformance/coverage.json`. A contract surface
cannot be added without declaring its public owner, fixtures, tests, installed
artifact result, and standard CI entry points.

| Contract surface | Authoritative Python API | Packaged evidence |
| --- | --- | --- |
| `endpoint-discovery` | `sfp.endpoint_discovery.v1.contract` | Canonical descriptor vectors |
| `bootstrap` | `sfp.bootstrap.v1.contract` and `validation` | Handshake request and response vectors |
| `health` | `sfp.health_contract` and standard `grpc.health.v1` messages | Watch, lifecycle, eligibility, and boundary scenarios |
| `manifest` | `sfp.manifest.v1.contract` and `validation` | Manifest, schema, revision, and session vectors |
| `capability-assessment` | `sfp.capability_assessment.v1.contract` and `validation` | Mixed findings and invalid exchange vectors |
| `trigger-publication` | `sfp.trigger_publication.v1.contract` and `validation` | Stream, publication, replay, and acknowledgement vectors |
| `operation-admission` | `sfp.operation_admission.v1.contract` and `validation` | Admission, duplicate, conflict, and error vectors |
| `operation-lifecycle` | `sfp.operation_lifecycle.v1.contract` and `validation` | Watch, progress, result, cursor, and cancellation vectors |
| `disconnection-recovery` | `sfp.recovery` composed with procedure validators | Channel-loss and retained/lost-state scenarios |
| `shared-endpoint` | `sfp.shared_endpoint` | Complete service and transport-limit inventory |

Standard gRPC Health is the deliberate exception to the custom-procedure
layout. StateForge does not duplicate its protobuf service or invent a second
semantic validator. Endpoint discovery is a filesystem contract, while
disconnection recovery and the shared endpoint compose other procedure
contracts rather than introducing new RPC services.

Every pull request and release candidate must pass:

1. Source conformance, deterministic generation, compatibility, typing, and
   documentation checks.
2. Exact wheel and sdist installation on every supported Python/platform
   combination.
3. Installed execution of every catalog entry using only packaged resources.
4. Independent Agent and Provider suites using the exact built Protocol wheel.
5. Consumer ownership auditing that rejects private validation imports, copied
   service identities or limits, and generated-binding use without the public
   contract and validator.

Missing catalog coverage is a release-blocking error, not an informational
report.
