# Security model and local trust boundary

SFP connects an Agent to independently running Provider processes on the same
host. Its security model begins with operating-system isolation around a
protected discovery directory and Unix socket. Protocol validation, Bootstrap,
and session fences then ensure that every accepted message belongs to the
endpoint and contract the Agent selected.

SFP does not turn identifiers into credentials. A Provider UUID, endpoint
generation, runtime ID, session ID, manifest revision, or request fingerprint
is useful only inside the validated local boundary and for the purpose defined
by its procedure.

<div class="sf-docs-card-grid sf-docs-card-grid--two">
  <article class="sf-docs-card">
    <span class="sf-docs-card__label">HOST</span>
    <h3>Protect the local boundary</h3>
    <p>
      Service users, groups, directory ownership, and Unix permissions decide
      which processes may publish or reach an endpoint.
    </p>
  </article>
  <article class="sf-docs-card">
    <span class="sf-docs-card__label">ENDPOINT</span>
    <h3>Validate one observation</h3>
    <p>
      The Agent correlates descriptor bytes, filename, generation, socket path,
      type, ownership, group, and mode before connecting.
    </p>
  </article>
  <article class="sf-docs-card">
    <span class="sf-docs-card__label">SESSION</span>
    <h3>Fence every exchange</h3>
    <p>
      Bootstrap confirms the selected endpoint and creates a fresh session.
      Later procedures carry the current generation, session, and declaration.
    </p>
  </article>
  <article class="sf-docs-card">
    <span class="sf-docs-card__label">WORK</span>
    <h3>Authorize outside the wire contract</h3>
    <p>
      SFP transports approved work. Agent policy and Provider runtime checks
      decide whether that work is allowed and currently safe to admit.
    </p>
  </article>
</div>

## Trust is established in layers

No single identifier or RPC establishes the complete trust relationship. Each
layer depends on the preceding one and must fail closed when its evidence is
missing or stale.

```mermaid
flowchart LR
    OS[Protected local<br/>OS boundary]
    DISC[Validated descriptor<br/>and Unix socket]
    CH[Provisional<br/>gRPC channel]
    SESSION[Negotiated and<br/>fenced SFP session]
    DECL[Accepted manifest<br/>and availability]
    WORK[Admitted operation<br/>or trigger stream]

    OS -->|ownership and permissions| DISC
    DISC -->|connect to exact generation| CH
    CH -->|Bootstrap confirms fences| SESSION
    SESSION -->|validate declaration and Health| DECL
    DECL -->|policy and runtime checks| WORK

    classDef root fill:#17324d,stroke:#79b8ff,color:#fff
    classDef observed fill:#12372f,stroke:#45c49a,color:#fff
    classDef provisional fill:#4a3517,stroke:#f4b860,color:#fff
    classDef trusted fill:#2f255a,stroke:#a991ff,color:#fff
    class OS root
    class DISC observed
    class CH provisional
    class SESSION,DECL,WORK trusted
```

| Layer | Evidence | What it permits | What it does not prove |
| --- | --- | --- | --- |
| Local OS boundary | Protected directory, service identity, ownership, group, and permissions | Which local processes may publish descriptors or connect to sockets | That a document or peer obeys the SFP contract |
| Endpoint observation | Canonical bounded descriptor plus a correlated Unix socket | Opening a provisional channel to one Provider generation | A negotiated session or permission to use later procedures |
| Bootstrap session | Matching Provider identity and generation, mutually supported wire version, Provider runtime ID, fresh session ID | Binding the channel to one negotiated SFP session | Authorization to invoke an operation |
| Accepted declaration | Valid manifest envelope, schemas, deterministic revision, and current Health | Selecting declared operations and triggers from the current Provider surface | That a declaration is truthful or that an operation is safe now |
| Runtime admission | Current session, declaration, availability, schema, profile, prerequisite, capacity, deadline, and policy checks | Creating or resolving one immutable operation record | That an earlier capability finding remains current |

## The local trust anchor

SFP v0.1.0 standardizes a Unix-domain endpoint. It does not define a TCP
listener, TLS, certificates, bearer credentials, or a remote-access perimeter.
Deployments must protect the discovery directory and socket with operating-
system identities and permissions, and run Agent and Provider processes with
only the privileges they require.

The endpoint descriptor is untrusted input even when it is valid JSON. The
Provider publishes the final descriptor with mode `0640` and the socket with
mode `0660`; directory ownership and access policy remain deployment and
runtime responsibilities. The Agent must:

1. reopen the final descriptor rather than trusting a filesystem event;
2. bound the read and reject symbolic links, unsafe file types, and unsafe
   metadata;
3. parse the document with the versioned Protocol contract;
4. correlate the descriptor filename, Provider UUID, endpoint generation,
   socket filename, and absolute path; and
5. validate the socket type, owner, group, and mode without following links.

Only then may the Agent open a provisional channel. Bootstrap must still
confirm the same Provider identity and endpoint generation before any later
procedure is allowed.

!!! danger "Filesystem access is part of the security boundary"

    A process that can replace trusted descriptors or sockets can attempt to
    impersonate a Provider. SFP message validation does not repair a
    compromised directory, service account, Agent process, Provider process,
    or privileged host administrator.

See [Endpoint discovery and channel establishment](../procedures/endpoint-discovery.md)
for the complete publication and validation order.

## Identity, freshness, and integrity

SFP carries several values that are easy to over-trust. Their security meaning
is deliberately narrow.

| Value | Purpose | Never treat it as |
| --- | --- | --- |
| `provider_instance_id` | Stable installation identity used to correlate one Provider across endpoint generations | A credential or proof that the process is authorized |
| `endpoint_generation` | Distinguishes successive published endpoints for one installation | Permission to reuse an older channel or session |
| `provider_runtime_id` | Identifies the currently executing Provider process | A durable installation identity |
| `session_id` | Fresh opaque fence for one successful Bootstrap session | A bearer token, secret, or global identity |
| `manifest_revision` | SHA-256 correlation for one canonical declaration | A signature, source attestation, or proof that the implementation is honest |
| Operation or publication fingerprint | Detects identical retry versus conflicting identity reuse | Authentication, authorization, or safe public representation of the source request |

The Agent offers wire versions and accepts only a version it actually offered.
The Provider selects the highest common version. The version exchange prevents
accidental negotiation drift inside the validated endpoint boundary; it is not
a cryptographic handshake.

Every session-bound procedure validates the current Provider installation,
endpoint generation, and session. Procedures that depend on declarations also
pin the accepted manifest revision. A response that is well-formed but carries
stale or mismatched fences is rejected locally.

## Authorization and capability are separate

SFP defines how an already approved operation is described, admitted,
observed, and reconciled. It does not define the policy that grants that
approval.

| Signal | What it means | What it does not mean |
| --- | --- | --- |
| Manifest declaration | The Provider declares an operation, trigger, schema, requirement, or profile claim | The Agent authorizes its use or the implementation satisfies the claim |
| Health `SERVING` | The Provider reports process-wide readiness and the Agent may include it in eligibility | A target is authorized or a particular operation will succeed |
| Capability finding | Point-in-time evidence about runtime support and requirements | Authorization, capacity reservation, or a durable promise |
| Profile claim or required role | A versioned semantic claim is declared and selected | A permission or independent proof of compliance |
| Admission success | The Provider atomically accepted or resolved one immutable invocation under current fences | Authorization for a different invocation or identity |

The Agent passes only approved, non-secret metadata in `execution_context`.
The Provider independently revalidates current session, manifest, Health,
schemas, prerequisites, capacity, and deadline before admitting new work. A
cached Capability Assessment never substitutes for those checks.

## Protecting secrets and diagnostics

SFP keeps secrets out of discovery, declarations, evidence, and diagnostics.
Actual secret-bearing operation input is permitted only where the operation's
input schema explicitly marks it `writeOnly`.

| Surface | Security rule |
| --- | --- |
| Endpoint descriptor and Bootstrap | Carry identity and negotiation data only; no credentials or configured values |
| Provider manifest | Carries schema and declarations, never configuration values; secret-bearing fields use `writeOnly: true` and cannot embed `default`, `examples`, `const`, or `enum` values |
| Capability Assessment | `execution_context` is non-secret; findings contain no configuration, credentials, customer data, or raw inspection failures |
| Trigger Publication | Declarations and publications must not carry credentials or secrets; rejection details are sanitized |
| Operation Admission | `payload` may contain values for schema-declared `writeOnly` inputs; those values must not appear in responses, errors, diagnostics, fixtures, or logs |
| Operation Lifecycle | Progress, failures, effects, and structured errors are bounded and sanitized; they never include raw exceptions, stack traces, credentials, or payload echoes |

Machine-readable codes and enums drive behavior. Human-readable explanations
are bounded diagnostics and must never be parsed as policy or used to echo
rejected input. A revision or fingerprint does not redact its source and must
not be exposed as a substitute for the underlying trusted request.

## Validation and resource isolation

Every received artifact is untrusted until the owning layer validates it.
Generated protobuf classes enforce wire types, not the complete SFP contract.

| Control | Security purpose |
| --- | --- |
| Exact schemas and public validators | Reject missing, unknown, malformed, ambiguous, or semantically invalid data consistently across implementations |
| Bounded descriptor and message sizes | Prevent unbounded allocation before procedure handling |
| Bounded JSON depth, breadth, strings, and canonicalization | Prevent pathological structured input and inconsistent fingerprints |
| Local-only JSON Schema references | Prevent remote schema retrieval and reference-base substitution |
| Aggregate transport ceilings plus narrower procedure limits | Let one shared endpoint carry every valid procedure without accepting oversized procedure messages |
| Stream windows, observer limits, deadlines, and bounded backoff | Contain slow peers and prevent unbounded retries or retained work |
| Canonical identities and immutable fingerprints | Distinguish safe replay from conflicting reuse |

Runtimes enforce byte limits before accepting messages, call the versioned
Protocol validators, and only then evaluate live filesystem, session, policy,
capacity, or persistence state.

## Fail-closed behavior

Loss of evidence never creates permission or a successful business outcome.

| Lost or invalid evidence | Required behavior |
| --- | --- |
| Unsafe descriptor or socket | Create no channel |
| Failed or mismatched Bootstrap | Bind no session and run no later procedure |
| Invalid or uncorrelated manifest | Keep the Provider ineligible for declared work |
| Health Watch failure or `NOT_SERVING` | Stop new admission and fail availability closed; do not rewrite already admitted work |
| Unknown capability evidence | Preserve `INDETERMINATE` or an unsatisfied prerequisite; do not infer support |
| Channel loss or endpoint replacement | Create a new channel and fresh session before exchanging more messages |
| Missing retained operation or trigger evidence | Preserve uncertainty; resolve, Watch, or replay according to the owning procedure, never automatically redispatch |

Cancellation, deadlines, transport loss, and process replacement do not prove
that side effects stopped. Recovery uses retained identities and validated
state instead of manufacturing success, failure, or permission to try again.
See [Disconnection and recovery](../procedures/disconnection-recovery.md) and
[SFP status and error handling](status-errors.md).

## Implementation checklist

### Deployment

- Protect the discovery directory with a dedicated ownership and group policy.
- Run Agent and Provider services with least privilege.
- Keep Provider credentials in an appropriate local secret source, not in
  descriptors, manifests, capability evidence, or diagnostics.
- Restrict and review logs because operation input may contain `writeOnly`
  values even though protocol diagnostics may not.

### Provider runtime

- Allocate stable installation identity, monotonic endpoint generations, and a
  fresh session ID for every successful Bootstrap.
- Bind the canonical socket before atomically publishing the descriptor.
- Enforce transport and procedure limits, validate every request, and compare
  every live fence before acting.
- Revalidate authorization-dependent runtime facts at admission time and stop
  advertising readiness before teardown.
- Sanitize all returned explanations, failures, effects, and error details.

### Agent runtime

- Treat filesystem notifications as hints and validate final artifacts without
  following symbolic links.
- Compare descriptor, socket, Bootstrap, session, manifest, and response
  identities before accepting each layer.
- Supply finite deadlines, bounded retry, and the exact immutable identity for
  idempotent replay.
- Treat Health and capability evidence as eligibility inputs, not permission.
- Fail closed on replacement, Watch failure, mismatched fences, invalid
  responses, and missing retained evidence.

## Canonical sources

| Source | Security responsibility |
| --- | --- |
| [`endpoint_discovery/v1/contract.py`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/endpoint_discovery/v1/contract.py) | Descriptor identity, filenames, modes, bounds, deterministic serialization, and complete document parsing |
| [`bootstrap/v1/contract.py`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/bootstrap/v1/contract.py) and [`validation.py`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/bootstrap/v1/validation.py) | Bootstrap service identity, message limits, wire versions, endpoint confirmation, runtime identity, and session shape |
| [`shared_endpoint.py`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/shared_endpoint.py) | Aggregate send and receive ceilings for the multiplexed endpoint |
| [`manifest/v1/validation.py`](https://github.com/stateforge-org/stateforge-protocol/blob/mvp/implementation/src/stateforge_protocol/sfp/manifest/v1/validation.py) | Declaration validation, safe embedded schemas, canonical revision, and response correlation |
| Versioned procedure `contract.py` and `validation.py` modules | Procedure bounds and context-independent semantic validation |
| Agent and Provider runtimes | Filesystem trust, live-session comparisons, policy, authorization, admission, persistence, logging, and process lifecycle |

For the ownership split behind these controls, see
[Responsibility boundaries](responsibility-boundaries.md).
