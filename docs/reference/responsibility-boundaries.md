# Runtime responsibility boundaries

StateForge Protocol is the single source of truth for every rule that decides
whether data is valid on an SFP boundary. Agent and Provider runtimes import
those contracts and add only checks that require their local state.

| Resource | Protocol owns | Agent owns | Provider owns |
| --- | --- | --- | --- |
| Shared scalars | Canonical UUIDv4 and protobuf integer semantics | Runtime creation and local storage | Runtime creation and local storage |
| Endpoint discovery | Descriptor shape, fields, names, modes, transport, identity and generation ranges | Directory trust, ownership checks, discovery watching | Atomic publication, state-file security, monotonic allocation |
| Bootstrap | Service identity, byte limits, version validity, envelope semantics and session-ID bounds | Deadline, offered versions, response correlation and connection state | Version selection, endpoint comparison, session allocation and shutdown |
| Manifest exchange | Service identity, byte/schema limits, canonical revision and full semantic validation | Retry policy, accepted-schema offer, response correlation and cache policy | Declaration authoring, tighter resource budgets, snapshot lifetime and serving |
| Capability assessment | Service identity, byte/schema limits, full request/response semantics and context-independent exchange correlation | Active-session and accepted-manifest checks, eligibility, normalization, caching and retry policy | Active-session and served-manifest checks, declaration lookup, readiness, requirement-check execution and serving |
| Standard Health | Service identity, monitored key, byte limits and status vocabulary | Watch retry, availability state and admission policy | Health hook, current process status and service lifecycle |
| Shared endpoint | Inventory of procedures and aggregate transport ceilings | Client channel construction | Server registration and construction |

Protocol rules must not be copied into a runtime, even when they are simple
constants or one-line validators. Runtime policy must not be moved into
Protocol merely because it affects an SFP call. A check belongs to Protocol
when two independent implementations must reach the same validity decision
from the same message alone. It belongs to a runtime when the decision depends
on current process state, filesystem trust, retry policy, cache capacity,
admission state, or another local resource.

Generated protobuf bindings define wire shape. Versioned `contract` modules
define normative limits and identifiers that protobuf cannot express.
Versioned validation modules define context-independent semantic obligations.
Agent and Provider code translate their failures into local exceptions or gRPC
status codes and then enforce contextual invariants.

Within Protocol, public procedure validators compose the private
`stateforge_protocol.sfp._validation` mechanics instead of copying schema
loading, ProtoJSON projection, scalar parsing, bounded traversal, or canonical
JSON code. The private support module is not a consumer API and owns no
procedure-specific constants or policy. Procedure `validation.py` modules keep
the public error surface and domain rules; specialized private modules may hold
complex algorithms that belong only to that procedure. Architectural tests
enforce this split so future procedures follow the same ownership model.
