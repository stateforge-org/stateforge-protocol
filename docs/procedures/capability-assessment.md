# Capability assessment

Capability assessment evaluates a requested operation set without executing
those operations. The Provider examines its current session, manifest, runtime,
and bounded non-secret context, then returns normalized support, limits,
requirements, and blockers. Resource-specific input belongs to each
operation's declared input schema and later invocation payload.

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
that a particular operation payload or resource is compatible. It performs
only the minimum bounded inspection necessary to assess the requested
operations and must not mutate resources, dispatch work, or rely on a hidden
write as a probe.

## Request model

| Field | Schema-1 meaning |
| --- | --- |
| `assessment_request_id` | Agent-assigned immutable UUIDv4 correlation identity. Reusing it correlates a retry of the same semantic request; changed content requires a new id. |
| `expected_provider_instance_id` | Copied from Handshake. |
| `expected_endpoint_generation` | Copied from Handshake, never a process ID. |
| `expected_session_id` | Copied from `HandshakeResponse.session_id`; the actual session-level fence. |
| `expected_manifest_revision` | Copied from the Agent's accepted `GetManifestResponse.manifest_revision`. |
| `execution_context` | Bounded, non-secret situational metadata the Provider inspection may use to refine a finding. Not manifest-schema-validated and never a substitute for operation-specific resource input. |
| `operation_identifiers` | Bounded, nonempty, unique set of `namespace/name@major` identifiers. Every entry must be declared in the accepted manifest's `operations`. Order conveys no preference; duplicates are invalid. |

Identifier syntax for `operation_identifiers` matches
[provider manifest exchange](provider-manifest.md): `namespace/name@major`,
case-sensitive, at most 255 characters, never coerced into a closed
operation enum.

The manifest's `configuration_schema` describes Provider configuration, not a
generic target or operation payload. This RPC does not carry Provider secrets
or resource configuration. Resource selection, where needed, belongs to the
operation's `input_schema` and later invocation payload.

## Normalized findings

Each per-operation finding uses one of these bounded protocol states. The
zero/`UNSPECIFIED` value is never valid in a well-formed response.

| State | Meaning |
| --- | --- |
| `SUPPORTED` | The Provider obtained enough current evidence to support the operation and found no additional unmet requirement. |
| `SUPPORTED_WITH_REQUIREMENTS` | The operation can be supported only after the returned requirements, constraints, or prerequisites are satisfied. |
| `UNSUPPORTED` | Current evidence proves that the declared operation is not supported. |
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
| `CapabilityFinding` | `operation_identifier` (exact requested identifier), `support_state`, `requirement_findings`, `reasons`, `constraints`. |
| `RequirementFinding` | `requirement_id` (stable, dotted, extensible), `state`, `description`, `version_constraint` (empty means no constraint; syntax is owned by the named requirement, mirroring `RuntimeRequirement.version_constraint`). |
| `ReasonDetail` | `reason_code` (dotted, the discriminator), `explanation` (bounded, sanitized; never the discriminator). |
| `ConstraintDetail` | `constraint_id` (stable, dotted), `value` (bounded, may be empty), `explanation` (bounded, sanitized). |

### Cross-field invariants

- `SUPPORTED` must not carry a `requirement_findings` entry in state
  `UNSATISFIED` or `UNKNOWN`.
- `SUPPORTED_WITH_REQUIREMENTS` must carry at least one `requirement_findings`
  entry in state `UNSATISFIED` or `UNKNOWN`, or at least one `constraints`
  entry — an actual unmet item, not merely any requirement or an empty
  finding. A finding whose requirements are all already `SATISFIED` and
  which carries no constraints has nothing left pending and does not justify
  this state.
- `UNSUPPORTED` and `INDETERMINATE` must carry at least one `reasons` entry.
- `requirement_findings[*].requirement_id`, `reasons[*].reason_code`, and
  `constraints[*].constraint_id` are each unique within one finding. JSON
  Schema cannot express uniqueness by a sub-key over an array of objects;
  this rule is enforced by dedicated tests, not the packaged schema.

### Reason-code vocabulary

`reason_code` is an open, extensible dotted identifier, not a closed enum.
Providers should reuse this canonical core vocabulary where applicable:

| Reason code | Meaning |
| --- | --- |
| `stateforge.capability_assessment.v1.access_denied` | The Provider could not access evidence needed for assessment. |
| `stateforge.capability_assessment.v1.permission_uncertain` | The Provider could not determine whether required permissions are present. |
| `stateforge.capability_assessment.v1.unsupported_vendor_state` | The current vendor-side state does not support the operation. |
| `stateforge.capability_assessment.v1.insufficient_evidence` | Inspection could not gather enough evidence to decide. |
| `stateforge.capability_assessment.v1.requirement_unmet` | A specific declared requirement is not met. |

A runtime adapting declared prerequisite checks uses `requirement_unmet` when
one of those prerequisites proves incompatible and `insufficient_evidence`
when inspection cannot decide. `unsupported_vendor_state` is reserved for
incompatibility specifically caused by the current vendor-side state; it is
not the generic code for an unsupported operating system, missing executable,
or other unmet runtime prerequisite.

A Provider-specific reason code must be namespaced under its own
`provider_identity` to avoid colliding with the core vocabulary or another
Provider's codes.

Python consumers import these canonical values from
`stateforge_protocol.sfp.capability_assessment.v1.contract` as
`REASON_CODE_ACCESS_DENIED`, `REASON_CODE_PERMISSION_UNCERTAIN`,
`REASON_CODE_UNSUPPORTED_VENDOR_STATE`, `REASON_CODE_INSUFFICIENT_EVIDENCE`,
and `REASON_CODE_REQUIREMENT_UNMET`. These constants expose the reusable core
vocabulary; they do not close the extensible `reason_code` namespace.

## Structural and semantic validation

The package ships
`stateforge_protocol/sfp/capability_assessment/v1/capability_assessment.schema.json`.
It validates the **ProtoJSON projection** of a complete response; the
`assessCapabilitiesRequest` definition validates requests. Use lowerCamelCase
names and `MessageToDict(message, always_print_fields_with_no_presence=True)`,
matching [provider manifest exchange](provider-manifest.md#structural-and-semantic-validation).
Every request and response field shown by the schema is required in that
projection. Proto3 zero/default values are not wildcards: empty identities,
generation zero, `UNSPECIFIED` enums, a missing findings collection, or an
empty requested-operation collection are invalid. Empty repeated detail
collections remain explicit empty arrays in a complete projected response.

The protobuf definition owns field names, numbers, types, and service shape.
The JSON Schema adds required-field, identifier, uniqueness, count, and the
cross-field invariants above. `execution_context` accepts recursively nested
JSON. The packaged schema bounds every object and array to 32 entries, every
property name to 128 characters, and every string value to
2,048 characters. The packaged Python validator enforces the aggregate
64-container nesting limit before schema processing. Runtimes enforce the
serialized-message limits at the transport boundary; JSON Schema cannot
portably express either limit, and `maxLength` counts Unicode code points
rather than encoded bytes.

These are structural ceilings only. `execution_context` is not
manifest-schema-validated and must not carry operation-specific resource input.
The static schema cannot verify that a response contains exactly one finding
per requested operation with no duplicates or omissions. The packaged Python
validator composes the schema with those exchange invariants so Agent and
Provider implementations do not reproduce Protocol rules.

| Limit | Maximum |
| --- | ---: |
| Serialized request | 8 MiB |
| Serialized response | 16 MiB |
| `execution_context` nesting depth | 64 containers |
| `execution_context` entries per container | 32 |
| `execution_context` property name | 128 characters |
| `execution_context` string value | 2,048 characters |
| `operation_identifiers` per request | 64 unique entries |
| `requirement_findings` per finding | 64 entries, unique `requirement_id` |
| `reasons` per finding | 16 entries, unique `reason_code` |
| `constraints` per finding | 32 entries, unique `constraint_id` |
| `explanation` | 1,024 characters |
| `RequirementFinding.description` | 2,048 characters |
| `version_constraint` | 255 characters (matches `RuntimeRequirement.version_constraint`) |
| `ConstraintDetail.value` | 512 characters |
| `ConstraintDetail.explanation` | 1,024 characters |

Configure transport message limits before decoding, matching
[provider manifest exchange](provider-manifest.md#structural-and-semantic-validation).
The byte limits are independent of the field-level bounds: a structurally
valid payload containing multibyte Unicode strings can still exceed the wire
limit. Reject that payload with `RESOURCE_EXHAUSTED`. After decoding, call the
packaged request validator. It enforces the nesting limit with a cheap
iterative walk before schema processing; malformed shape or excessive nesting
is `INVALID_ARGUMENT` after runtime status translation.

## Assessment semantics and correlation

An `AssessCapabilitiesResponse` is point-in-time evidence, not an
authorization, reservation, lease, health guarantee, or promise that later
admission will succeed. Provider health, manifest declaration, runtime
compatibility, and requirement satisfaction remain distinct facts; `SERVING`
and a valid declaration alone do not prove payload- or resource-specific
support.

Read-only retries are safe but may observe newer Provider state. Reusing
`assessment_request_id` correlates the same semantic request; changed
semantic content requires a new request id. The contract requires no
persistent assessment or idempotency ledger. `assessment_id` is
Provider-minted per call and is never derived from `assessment_request_id`,
since a read-only retry may legitimately yield a new `assessment_id` for an
unchanged request. `assessment_timestamp` is Provider-clock evidence of when
the assessment's evidence was captured — point-in-time evidence only, never
a trusted ordering or authorization mechanism across sessions or Providers.

A successful response reports exactly one finding per requested operation
identifier in request order for a deterministic projection. Consumers still
correlate by `operation_identifier`, not position. The Agent validates a
successful response against the active session and manifest before normalizing
it for a consumer; a Provider response cannot add operations or roles absent
from the accepted manifest. Later operation
admission performs its own current validation and must not treat an old
assessment as permission to dispatch.

## Failures, deadlines and retries

| Outcome | Required behavior |
| --- | --- |
| Malformed fields, invalid identifier syntax, duplicate `operation_identifiers`, invalid or oversized bounds | Provider returns `INVALID_ARGUMENT`. |
| Missing handshake; instance, generation, or session mismatch; stale or mismatched manifest revision; undeclared operation identifier | Provider returns `FAILED_PRECONDITION`; Agent re-handshakes or re-fetches the manifest before retrying. |
| Request or response would exceed declared resource limits | Provider returns `RESOURCE_EXHAUSTED`. |
| Client deadline or cancellation | Standard `DEADLINE_EXCEEDED` / `CANCELLED`; inspection stops where possible and there is no resource mutation to undo. |
| Transport or whole-service temporary unavailability | `UNAVAILABLE`; bounded retry is safe only after session revalidation. |
| Unexpected Provider boundary failure that prevents a valid normalized response | Sanitized `INTERNAL`; never expose stack traces, credentials, or raw operation payloads. |
| Access denial, permission uncertainty, unsupported vendor state, or per-operation inability to inspect, for an otherwise-valid request | **Not an RPC error.** Becomes an explicit `UNSUPPORTED` or `INDETERMINATE` finding. |

Check request syntax before session binding, then session/manifest fencing,
then perform read-only operation assessment. Diagnostic text is not a
machine-readable error discriminator; this contract uses standard gRPC
statuses and reason codes, not a separate error-detail schema.

The Agent supplies a finite per-call deadline; the wire contract defines no
implicit default. On cancellation or deadline expiry, the Provider stops
inspection where possible and never returns or acts on a partial result.
Retries are bounded and use backoff. Reuse `assessment_request_id` only when
the semantic request is unchanged, and revalidate the negotiated session and
accepted manifest before every retry; changed content receives a new request
identity.

## Contract boundary

Capability assessment uses the active handshake session and accepted manifest
revision. Each request names manifest-declared operations and carries only
bounded, non-secret execution context; it has no generic target fields. An
operation's versioned input and result schemas define operation-specific
resource input and output. Assessment does not validate a future invocation
payload, admit or dispatch work, or grant authorization.

This package defines the Protocol-only assessment messages, validation schema,
canonical Python validation API, and conformance vectors. Provider assessment
behavior and Agent-side use of the results are separate implementations.
