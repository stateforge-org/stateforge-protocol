# Provider manifest exchange

After a successful handshake, the Agent retrieves the Provider's effective
manifest over the negotiated SFP service. The exchange confirms identity,
manifest schema compatibility, operations, contracts, triggers,
runtime requirements, and configuration schema without transferring secrets.

[![Provider Manifest Exchange sequence diagram](../assets/diagrams/provider-manifest-exchange.png)](../assets/diagrams/provider-manifest-exchange.png)

_Select the diagram to open the full-resolution version._

## Wire contract

SFP 1.0 exposes the unary method
`/stateforge.sfp.manifest.v1.ManifestService/GetManifest` on the same local
gRPC channel as bootstrap. The authoritative source is
`proto/stateforge_protocol/sfp/manifest/v1/manifest.proto`. No new connection,
reverse RPC, operation admission, or persistent registry is involved.

The Agent may call this read-only, idempotent RPC only after a successful
handshake. It supplies `expected_provider_instance_id`,
`expected_endpoint_generation`, `expected_session_id`, and
`supported_manifest_schema_versions`. The session identifier is copied unchanged
from `HandshakeResponse.session_id`; all three identity values must match the
active negotiated session. Missing identities, zero generations, and empty
session identifiers are invalid; they never mean "any Provider or session".
The schema offer contains 1-32 unique positive uint32 values. Offer order has
no meaning. Select the highest version supported by both peers; this change
defines only manifest schema **1**. Software, SFP, and manifest schema versions
are independent. Supporting SFP 1.0 does not imply supporting every future
manifest schema.

Every successful response contains the confirmed instance and generation,
selected `manifest_schema_version`, `manifest_revision`, a complete
`ProviderManifest`, and `session_id` echoing the validated request's
`expected_session_id`. There is no empty success or implicit not-modified reply.
The declaration, identity, generation, and revision come from one consistent
snapshot; `session_id` belongs to this call's validated session, not the
immutable declaration. Concurrent callers can receive the same declaration
and revision with different session headers. Never reuse another call's header
or substitute a global "latest session" identifier.

### Session binding

`GetManifestRequest.expected_session_id` uses field **4** and
`GetManifestResponse.session_id` uses field **6**. Existing field numbers and
meanings are preserved. Both are required opaque strings of 1–255 Unicode
code points, matching capability assessment. Preserve exact case and contents;
do not trim, normalize, parse as UUID, or derive them from endpoint identity.
No mandatory session metadata header is introduced.

The Provider must resolve the requested identifier to a known, active session
established by successful SFP negotiation, for the requested Provider instance
and endpoint generation. It must validate that binding before selecting the
manifest schema or serving the snapshot. A successful handshake by some other
session on the endpoint is insufficient. Unknown, inactive, or mismatched
sessions fail with `FAILED_PRECONDITION`; malformed or missing identifiers
fail with `INVALID_ARGUMENT` before semantic lookup. If the Provider detects
invalidation before returning, it must fail rather than substitute another
session. How the runtime stores active sessions is outside this contract.

A new handshake can produce a different session without changing the instance
or generation. The Agent captures the negotiated session for each request and
accepts a response only if its `session_id` matches both that request and the
Agent's still-current session. A late reply for a superseded session is rejected
even if the manifest revision is cached and otherwise valid. Session identifiers
express negotiated context; they are not authentication credentials or
permission to execute operations. Existing channel trust requirements still
apply.

## Declaration model

The public Provider framework constructs these declarations from Python
metadata, typed models, decorators, and explicit compliance claims. Provider
authors do not construct protobuf messages or calculate revisions themselves.

| Declaration | Schema-1 meaning |
| --- | --- |
| `provider_identity` | Author-declared dotted lowercase identity such as `stateforge.git`. |
| `implementation_version` | SemVer 2.0.0 of the running Provider implementation. |
| `display_name` | Nonempty human-readable name. |
| `operations` | Map from extensible operation identifier to Draft 2020-12 input schema, result schema, and explicit `implements` roles. |
| `runtime_requirements` | Map of dotted requirement identifiers to descriptions and version constraints. These are declarations, not installed-state observations or commands to execute. |
| `platforms` | Nonempty list of explicit operating-system/architecture pairs, such as `linux` / `x86_64`. No wildcard or implied Cartesian product. |
| `configuration_schema` | JSON Schema Draft 2020-12 object schema describing configuration shape. |
| `triggers` | Map from declared trigger identifier to a payload schema. No streaming or acknowledgement behavior is defined here. |

Operation and trigger identifiers use
`namespace/name@major`, for example `stateforge.git/reference.resolve@1`.
The namespace contains at least two dotted lowercase segments. Name segments
are lowercase and may be dotted; segments start with a letter and may contain
digits or underscores. The major is positive with no leading zero. Identifiers
are case-sensitive and at most 255 characters. They must never be coerced into
a closed operation enum.

Empty operation or trigger maps declare no such support. Empty requirements
declare no additional prerequisite. An empty version constraint means no
declared version restriction; its nonempty syntax is owned by the requirement
identifier, not interpreted by the protocol package. An unfamiliar requirement
is not evidence that the Agent satisfies it; assessment/admission policy is
owned by their later contracts.

Compliance roles are explicit per-operation dotted identifiers such as
`stateforge.backup.v1.prepare` and
`stateforge.disaster_recovery.v1.reconstruct`. An operation named "backup"
with an empty `implements` list makes no compliance claim. Unknown roles may
be transported but cannot establish a recognized compliance profile. A known
claim must be checked against that profile's exact versioned input/result
schemas and semantic requirements before use. The versioned operation
identifier identifies its input/result contract; an incompatible operation
contract change requires a new identifier version.

Every operation declaration contains exactly `input_schema`, `result_schema`,
and `implements`. The operation's `result_schema` is the only manifest-level
declaration of terminal result shape. Generic, custom, backup-profile, and
DR-profile operations all use the same structure. Construction and structural
validation must not infer additional result modes from names, roles, or schema
payloads. Protobuf field 4 and `backup_source_modes` are reserved; the ProtoJSON
schema rejects `backupSourceModes` and `backup_source_modes` as unknown
operation properties, including empty values. Names inside embedded schemas
remain ordinary schema data and do not create manifest fields or claims.

The later backup-preparation profile will define the exact terminal result
schema as an explicitly tagged choice between `materialized_source` and
`provider_reference`. This manifest contract does not define its tag key or
variant fields. The Provider prepares data and returns one schema-valid
result. The Agent validates the variant; it may route a materialized source
to an Agent-owned BackupEngine, while a Provider reference bypasses it.
Engine configuration, capabilities, routing, credentials, and lifecycle have
no place in Manifest Exchange. Providers do not choose or invoke an engine.

## Structural and semantic validation

The package ships `stateforge_protocol/sfp/manifest/v1/manifest.schema.json`.
It validates the **ProtoJSON projection** of a complete response. The
`getManifestRequest` definition validates requests. Use lowerCamelCase names
and emit every scalar, repeated-field, and map default that has no presence.
Present message fields remain present; absent required messages are invalid.
For Python, use `MessageToDict(message,
always_print_fields_with_no_presence=True)`. Do not use a serializer's
default field-omission behavior for validation or revision calculation.

The protobuf definition owns field names, numbers, types and service shape.
The JSON Schema adds required-field, identifier, uniqueness, count, and nested
JSON Schema constraints. Protobuf deserialization alone is not validation.
Neither generated bindings nor this package run a server, negotiate schemas,
validate a session, construct manifests, or maintain Agent caches.

The schema enforces canonical lowercase UUIDv4 identities, positive decimal
generation strings, SemVer, required messages, unique lists, identifier syntax,
known schema version, and a `sha256:` revision with 64 lowercase hex digits.
Protobuf also enforces the uint64 bound on generations. Implementations must
enforce the following limits before accepting a snapshot:

| Limit | Maximum |
| --- | ---: |
| Serialized request | 8 KiB |
| Serialized response | 2 MiB |
| Canonical revision preimage | 1 MiB |
| Each operations, triggers, or requirements map | 1,024 entries |
| Platform pairs | 256 unique pairs |
| Compliance roles per operation | 64 unique roles |
| Embedded JSON nesting | 64 containers |

Configure transport message limits before decoding and check the canonical
preimage size and nesting before expensive schema processing. Implementations
may impose stricter local resource limits and report them safely.

All input, result, configuration, and trigger schemas are Draft 2020-12 object
schemas represented using `google.protobuf.Struct`. Each root explicitly
declares `$schema` and `type: object`. Boolean subschemas are allowed. Only
local fragment references are allowed; `$id` is prohibited so a nested schema
cannot change a reference's base. Consumers must check that every reference
resolves inside its own schema document and must not retrieve remote schemas.
No non-JSON values, duplicate JSON object keys, NaN, infinity, invalid Unicode,
or values outside RFC 8785's interoperable numeric domain are allowed.

Schemas describe types, constraints, and safe static metadata. They never carry
actual configured values, credentials, customer data, or component bindings.
Mark every secret-bearing input with `writeOnly: true`; a write-only schema
cannot contain `default`, `examples`, `const`, or `enum` values. References and
composed schemas must not introduce those values for a secret-bearing input
indirectly. The structural schema catches direct and recursively nested
write-only violations. It cannot recognize arbitrary secrets in descriptions
or prove a business-specific declaration truthful. Those semantic checks
remain mandatory in the Provider runtime and Agent. Never echo rejected
values or whole schemas in errors.

## Deterministic revision

For a validated `GetManifestResponse` named `response`, construct the preimage
as follows (this Python example uses the development dependency `rfc8785`):

```python
import hashlib

import rfc8785
from google.protobuf.json_format import MessageToDict

preimage = {
    "manifest": MessageToDict(
        response.manifest, always_print_fields_with_no_presence=True
    ),
    "manifestSchemaVersion": response.manifest_schema_version,
    "providerInstanceId": response.provider_instance_id,
}
revision = "sha256:" + hashlib.sha256(rfc8785.dumps(preimage)).hexdigest()
```

Canonicalize the object using
[RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html),
encode it as UTF-8, and set the revision to `sha256:` followed by the lowercase
SHA-256 digest. Include all schema-1 declaration fields, including display
metadata, explicit empty maps/lists/strings, embedded schemas, and compliance
claims. Exclude `manifest_revision`, `endpoint_generation`, and `session_id`.
Thus a new handshake or a restart with unchanged declarations and stable
installation identity can retain its revision, while a new installation or
changed declarations gets a new one. Session binding changes only the exchange
envelope: the checked-in canonical preimage bytes and golden digest stay the
same.

Changing an input or result schema changes the revision even if the role is
unchanged. Object/map key insertion order does not affect the revision. Array
order is preserved and contributes to the revision, including JSON Schema arrays. A
Provider should generate stable ordering for set-like declaration lists to
avoid unnecessary revision changes. RFC 8785 supplies string escaping, UTF-16
key ordering and IEEE 754 number formatting; do not apply extra Unicode
normalization, schema rewriting, or application defaults to the preimage.

Do not hash protobuf bytes, even with deterministic serialization enabled:
[protobuf serialization is not canonical](https://protobuf.dev/programming-guides/serialization-not-canonical/).
The checked-in `tests/fixtures/manifest/response.json` and
`revision-preimage.json` form a cross-language conformance vector. Its revision
is `sha256:34f54f69855f1fbebef4d3d6bb74c0238785e0f8ef43f9efb1a12e6b4353183d`.

## Agent acceptance and caching

1. Verify successful handshake, expected identity and generation, and that the
   selected schema was offered and is understood.
2. Require a complete response, valid header, and bounded payload. Match the
   response `session_id` to the request's `expected_session_id` and the current
   negotiated session before considering any cached declaration.
3. Compare `(provider_instance_id, negotiated SFP version,
   manifest_schema_version, manifest_revision)` with a previously **validated**
   cache entry. On a match, reuse that exact cached declaration; do not merge
   fields from the new response or skip current session/generation checks.
4. For a new key, validate the complete schema, embedded references, identity,
   profile claims, limits, and canonical digest before acceptance. Store only
   accepted snapshots. A revision is a change detector, not authentication.
5. An invalid manifest leaves the integration unusable even if gRPC health is
   `SERVING`. Block operational requests. A valid changed manifest replaces the
   normalized declaration and triggers Agent-owned reconciliation.

This permits header comparison and reuse without re-validating and normalizing
an unchanged declaration. Protobuf decoding still occurs because the response
is complete. Cache the declaration separately from its per-call session header;
a matching cache entry never authorizes skipping current-session checks. The
protocol package does not implement the cache or inventory.

## Failures, deadlines and retries

| Outcome | Required behavior |
| --- | --- |
| Malformed request, duplicate/empty version offer, invalid identity/generation, or missing/empty/oversized session ID | Provider returns `INVALID_ARGUMENT`. |
| Session unknown/inactive, handshake missing, or instance/generation does not match the requested active session | Provider returns `FAILED_PRECONDITION`; Agent re-establishes a session (rediscovering if needed) before a new attempt. |
| No common manifest schema version | Provider returns `UNIMPLEMENTED`; Agent marks the endpoint incompatible instead of indefinitely retrying unchanged capabilities. |
| Provider cannot produce a valid snapshot | Fail startup before ready publication where possible; otherwise return `INTERNAL` with sanitized diagnostics, never partial success. |
| Transport lost or temporarily unavailable | `UNAVAILABLE`; bounded read retries with backoff are safe after validating/re-establishing the session. |
| Client deadline or cancellation | Standard `DEADLINE_EXCEEDED` / `CANCELLED`; no operation is started or cancelled by this read. |
| Success payload fails Agent validation or revision check | Local manifest rejection, independently of transport health; it is not a successful capability negotiation. |

Check request syntax before session binding, then schema compatibility, then
obtain a snapshot. Each unary call has an explicit finite deadline chosen by
the Agent. Cancellation stops response work; it has no Provider business side
effects. After re-handshake, build a new request using the new handshake's
session ID and confirmed identity/generation; do not retry the old session ID
or accept its outstanding responses. Bounded retries within a still-valid
session may reuse its identifier. Retries may observe a newer complete
revision. Diagnostic text is not a machine-readable error discriminator; this
contract uses standard gRPC statuses and introduces no separate error-detail
schema.

## Contract boundary

Manifest schema 1 is the only schema defined by this package. A request names
the expected Provider instance, endpoint generation, and negotiated session;
the response echoes that session and carries one complete declaration and its
revision. Unknown manifest schema versions are not interpreted as schema 1.

`ProviderManifest` describes Provider-wide identity, operations, runtime and
platform requirements, Provider configuration shape, and triggers. It contains
no generic target-kind declaration or configured resource. An operation's
`input_schema` defines any resource information that operation needs. The
manifest contains schemas, not configuration values or operation inputs.

The `manifest_revision` hashes the canonical declaration, schema version, and
Provider instance identity. Session ID and endpoint generation are not part of
that preimage. Consumers must validate the full response and revision before
caching it; a changed declaration has a different revision.

This package defines wire messages, validation schemas, and conformance
vectors, not Provider session storage or an Agent client. The portable
`tests/fixtures/manifest/request.json`, `response.json`, and
`session-binding.json` fixtures exercise the current schema and session
binding.
