# Capability assessment

Capability assessment evaluates a concrete target and requested operation set
without executing those operations. The Provider validates configuration,
examines the third-party target, and returns normalized support, limits,
requirements, and blockers.

[![Capability Assessment sequence diagram](../assets/diagrams/capability-assessment.png)](../assets/diagrams/capability-assessment.png)

_Select the diagram to open the full-resolution version._

## Wire contract

SFP exposes the unary method
`/stateforge.sfp.capability_assessment.v1.CapabilityAssessmentService/AssessCapabilities`
on the same local gRPC channel as bootstrap and manifest exchange. The
authoritative source is
`proto/stateforge_protocol/sfp/capability_assessment/v1/capability_assessment.proto`.

The Agent may call this read-only RPC only after a successful handshake and
after it has validated and accepted a manifest. It binds every request to
`expected_provider_instance_id`, `expected_endpoint_generation`,
`expected_session_id`, and `expected_manifest_revision`. The first two values
identify only an endpoint generation; `expected_session_id` is the field that
actually fences the request to one negotiated session, since multiple
handshakes can in principle occur against the same generation.
`expected_manifest_revision` must match the Agent's currently accepted
manifest, so a Provider reload or restart with changed declarations cannot
produce an apparently current assessment against a manifest the Agent never
validated.

This RPC never executes an operation, reserves capacity, creates a
StateForge binding, or converts a Provider manifest declaration into proof
that a particular target is compatible. It performs only the minimum bounded
inspection necessary to assess the requested operations and must not mutate
the target, dispatch work, or rely on a hidden write as a probe.

## Request and target model

| Field | Schema-1 meaning |
| --- | --- |
| `assessment_request_id` | Agent-assigned immutable UUIDv4 correlation identity. Reusing it correlates a retry of the same semantic request; changed content requires a new id. |
| `expected_provider_instance_id` | Copied from Handshake. |
| `expected_endpoint_generation` | Copied from Handshake, never a process ID. |
| `expected_session_id` | Copied from `HandshakeResponse.session_id`; the actual session-level fence. |
| `expected_manifest_revision` | Copied from the Agent's accepted `GetManifestResponse.manifest_revision`. |
| `target_kind` | Single declared target kind, `namespace/name@major`, must be one of the accepted manifest's `target_kinds`. |
| `target_configuration` | Target-specific configuration needed for inspection. Structurally must be an object; its contents are validated against the accepted manifest's `configuration_schema` for `target_kind` at runtime, not by this package. |
| `execution_context` | Bounded, non-secret situational metadata the Provider inspection may use to refine a finding. Not manifest-schema-validated and never treated as part of the target's identity or configuration. |
| `operation_identifiers` | Bounded, nonempty, unique set of `namespace/name@major` identifiers. Every entry must be declared in the accepted manifest's `operations`. Order conveys no preference; duplicates are invalid. |

Identifier syntax for `target_kind` and `operation_identifiers` matches
[provider manifest exchange](provider-manifest.md): `namespace/name@major`,
case-sensitive, at most 255 characters, never coerced into a closed
operation enum.

`target_configuration` may carry `writeOnly`-declared secret-bearing fields
as input where the manifest's `configuration_schema` permits it. The
Provider must never copy such values into the response, reasons, logs,
assessment identity, fixtures, or diagnostics.

## Normalized findings

Each per-operation finding uses one of these bounded protocol states. The
zero/`UNSPECIFIED` value is never valid in a well-formed response.

| State | Meaning |
| --- | --- |
| `SUPPORTED` | The Provider obtained enough current evidence to support the operation for this target and found no additional unmet requirement. |
| `SUPPORTED_WITH_REQUIREMENTS` | The operation can be supported only after the returned requirements, constraints, or prerequisites are satisfied. |
| `UNSUPPORTED` | Current evidence proves that the declared operation is not supported for this valid target or target state. |
| `INDETERMINATE` | The Provider cannot establish support or non-support from the available evidence, for example because inspection, access, permissions, or vendor state is insufficient. |

`SUPPORTED_WITH_REQUIREMENTS`, `UNSUPPORTED`, and `INDETERMINATE` are
successful domain results, not RPC failures. A mixed request may return
different states per operation.

Each `RequirementFinding` carries one of these states. An unknown
requirement is never evidence of satisfaction, and an unverified
`version_constraint` is never evidence of satisfaction either.

| State | Meaning |
| --- | --- |
| `SATISFIED` | The requirement is met. |
| `UNSATISFIED` | The requirement is not met. |
| `UNKNOWN` | The Provider could not establish whether the requirement is met. |

### Finding fields

| Message | Fields |
| --- | --- |
| `CapabilityFinding` | `operation_identifier` (exact requested identifier), `support_state`, `requirement_findings`, `reasons`, `constraints`, `backup_source_modes`. |
| `RequirementFinding` | `requirement_id` (stable, dotted, extensible), `state`, `description`, `version_constraint` (empty means no constraint; syntax is owned by the named requirement, mirroring `RuntimeRequirement.version_constraint`). |
| `ReasonDetail` | `reason_code` (dotted, the discriminator), `explanation` (bounded, sanitized; never the discriminator). |
| `ConstraintDetail` | `constraint_id` (stable, dotted), `value` (bounded, may be empty), `explanation` (bounded, sanitized). |

### Cross-field invariants

- `SUPPORTED` must not carry a `requirement_findings` entry in state
  `UNSATISFIED` or `UNKNOWN`.
- `SUPPORTED_WITH_REQUIREMENTS` must carry at least one `requirement_findings`
  or `constraints` entry — an actionable item, not an empty finding.
- `UNSUPPORTED` and `INDETERMINATE` must carry at least one `reasons` entry.
- `requirement_findings[*].requirement_id` and `reasons[*].reason_code` are
  unique within one finding. JSON Schema cannot express uniqueness by a
  sub-key over an array of objects; this rule is enforced by dedicated tests,
  not the packaged schema.

### Backup source modes

`backup_source_modes` is populated only when the accepted manifest's
declaration for `operation_identifier` explicitly claims a backup or
disaster-recovery role via `implements` with a nonempty
`backup_source_modes`; it is empty for ordinary operations. Its values are
the same closed schema-1 vocabulary as the manifest field it echoes —
`staged_filesystem` and `provider_reference`, at most two unique values —
never a new taxonomy. BackupEngine mechanics, staging shapes, and
Provider-reference formats are Agent/BackupEngine-owned concepts (backup
engines are in-process Agent tools and never SFP peers) and are not modeled
by this Protocol-only contract.

### Reason-code vocabulary

`reason_code` is an open, extensible dotted identifier, not a closed enum.
Providers should reuse this canonical core vocabulary where applicable:

| Reason code | Meaning |
| --- | --- |
| `stateforge.capability_assessment.v1.access_denied` | The Provider could not access the target with the supplied configuration. |
| `stateforge.capability_assessment.v1.permission_uncertain` | The Provider could not determine whether required permissions are present. |
| `stateforge.capability_assessment.v1.unsupported_vendor_state` | The target's current vendor-side state does not support the operation. |
| `stateforge.capability_assessment.v1.insufficient_evidence` | Inspection could not gather enough evidence to decide. |
| `stateforge.capability_assessment.v1.target_not_found` | The declared target could not be located. |
| `stateforge.capability_assessment.v1.requirement_unmet` | A specific declared requirement is not met. |

A Provider-specific reason code must be namespaced under its own
`provider_identity` to avoid colliding with the core vocabulary or another
Provider's codes.

## Structural and semantic validation

The package ships
`stateforge_protocol/sfp/capability_assessment/v1/capability_assessment.schema.json`.
It validates the **ProtoJSON projection** of a complete response; the
`assessCapabilitiesRequest` definition validates requests. Use lowerCamelCase
names and `MessageToDict(message, always_print_fields_with_no_presence=True)`,
matching [provider manifest exchange](provider-manifest.md#structural-and-semantic-validation).

The protobuf definition owns field names, numbers, types, and service shape.
The JSON Schema adds required-field, identifier, uniqueness, count, and the
cross-field invariants above. It validates `target_configuration` and
`execution_context` only as `{"type": "object"}`; validating their contents
against the accepted manifest's `configuration_schema` is a runtime semantic
check this static schema cannot perform. It likewise cannot verify that
`backup_source_modes` is actually a subset of what the accepted manifest
declared for that operation, or that a response contains exactly one finding
per requested operation with no duplicates or omissions — both are consumer
and test-suite responsibilities, not schema responsibilities.

| Limit | Maximum |
| --- | ---: |
| `operation_identifiers` per request | 64 unique entries |
| `requirement_findings` per finding | 64 entries, unique `requirement_id` |
| `reasons` per finding | 16 entries, unique `reason_code` |
| `constraints` per finding | 32 entries |
| `backup_source_modes` per finding | 2 entries (matches P1 exactly) |
| `explanation` | 1,024 characters |
| `RequirementFinding.description` | 2,048 characters |
| `version_constraint` | 255 characters (matches `RuntimeRequirement.version_constraint`) |
| `ConstraintDetail.value` | 512 characters |
| `ConstraintDetail.explanation` | 1,024 characters |

## Assessment semantics and correlation

An `AssessCapabilitiesResponse` is point-in-time evidence, not an
authorization, reservation, lease, health guarantee, or promise that later
admission will succeed. Provider health, manifest declaration, runtime
compatibility, target compatibility, and requirement satisfaction remain
distinct facts; `SERVING` and a valid declaration alone do not prove
target-specific support.

Read-only retries are safe but may observe a newer target state. Reusing
`assessment_request_id` correlates the same semantic request; changed
semantic content requires a new request id. This milestone introduces no
persistent assessment or idempotency ledger. `assessment_id` is
Provider-minted per call and is never derived from `assessment_request_id`,
since a read-only retry may legitimately yield a new `assessment_id` for an
unchanged request. `assessment_timestamp` is Provider-clock evidence of when
the assessment's evidence was captured — point-in-time evidence only, never
a trusted ordering or authorization mechanism across sessions or Providers.

A successful response reports exactly one finding per requested operation
identifier, correlated by `operation_identifier`, not position. The Agent
validates a successful response against the active session and manifest
before normalizing it for a consumer; a Provider response cannot add
operations, roles, source modes, or target kinds absent from the accepted
manifest. Later operation admission performs its own current validation and
must not treat an old assessment as permission to dispatch.

## Failures, deadlines and retries

| Outcome | Required behavior |
| --- | --- |
| Malformed fields, invalid identifier syntax, duplicate `operation_identifiers`, invalid or oversized bounds, schema-invalid `target_configuration` | Provider returns `INVALID_ARGUMENT`. |
| Missing handshake; instance, generation, or session mismatch; stale or mismatched manifest revision; undeclared `target_kind` or operation identifier | Provider returns `FAILED_PRECONDITION`; Agent re-handshakes or re-fetches the manifest before retrying. |
| Request or response would exceed declared resource limits | Provider returns `RESOURCE_EXHAUSTED`. |
| Client deadline or cancellation | Standard `DEADLINE_EXCEEDED` / `CANCELLED`; inspection stops where possible and there is no target mutation to undo. |
| Transport or whole-service temporary unavailability | `UNAVAILABLE`; bounded retry is safe only after session revalidation. |
| Unexpected Provider boundary failure that prevents a valid normalized response | Sanitized `INTERNAL`; never expose stack traces, credentials, or raw target payloads. |
| Access denial, permission uncertainty, unsupported vendor state, or per-operation inability to inspect, for an otherwise-valid request | **Not an RPC error.** Becomes an explicit `UNSUPPORTED` or `INDETERMINATE` finding. |

Check request syntax before session binding, then session/manifest fencing,
then perform target-specific inspection. Diagnostic text is not a
machine-readable error discriminator; this contract uses standard gRPC
statuses and reason codes, not a separate error-detail schema.

## Compatibility and delivery boundary

Keep bootstrap v1 and the P1 manifest contract unchanged — its schema 1,
versioned string identifiers, explicit `implements` roles, backup
source-mode declarations, and deterministic manifest revision rules are
untouched by this milestone. Never reuse field numbers or silently change
this package's meaning; new interoperability semantics require explicit
versioning.

This procedure defines the Protocol-only capability-assessment contract.
Provider runtime and author-facing assessment hooks, Agent client/SDK
normalization, operation admission, dispatch, backup or disaster-recovery
execution, policy evaluation, SF-AOP, and Control Plane behavior are
implemented in their own planned steps.
