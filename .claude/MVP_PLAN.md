# StateForge Protocol MVP plan

This ledger tracks implemented SFP wire contracts. Every SFP procedure is
already designed in the specification; this table records whether an
authoritative protobuf contract exists where one is required.

## Product-level MVP sequence

| Phase | Status | Exit condition |
| --- | --- | --- |
| Local SFP Agent-to-Provider foundation | `IN PROGRESS` | Versioned contracts needed by all local SFP procedures are generated, tested, and consumed by Provider and Agent. |
| SF-AOP design and contracts | `ON HOLD` | Agent-to-Control-Plane procedures and wire contracts are designed from the proven SFP behavior. |
| StateForge Control Plane | `ON HOLD` | Control Plane coordination and persistence are implemented against SF-AOP. |
| End-to-end MVP integration | `ON HOLD` | Trigger, snapshot, backup, and disaster-recovery paths work across every boundary. |

SF-AOP and the Control Plane remain required MVP work. They are on hold only
because SF-AOP has not yet been designed; do not invent their schemas while
implementing SFP.

## Current SFP contract implementation

| # | Procedure | Status | Evidence or remaining work |
| ---: | --- | --- | --- |
| 1 | Endpoint Discovery and Channel Establishment | `N/A` | Designed and documented as a filesystem contract; no protobuf is required. |
| 2 | Handshake and Version Negotiation | `IMPLEMENTED` | `BootstrapService.Handshake` v1 and generated Python contracts exist. |
| 3 | Provider Manifest Exchange | `IMPLEMENTED` | `ManifestService.GetManifest` v1, generated typed bindings, ProtoJSON schema, and revision vectors exist. By explicit user direction, schema 1 now uses generic input/result/implements declarations with field 4/name reserved; the schema and golden revision were updated in place. Provider/Agent runtime integration remains in their repositories. |
| 4 | Health and Availability Monitoring | `N/A` | Uses the standard `grpc.health.v1` contract rather than a StateForge duplicate. |
| 5 | Capability Assessment | `BLOCKED` | Define after the effective manifest contract. |
| 6 | Trigger Publication and Acknowledgement | `BLOCKED` | Define after manifest and capability declarations stabilize. |
| 7 | Operation Admission and Idempotency | `BLOCKED` | Generic operation-envelope and admission contracts are absent. |
| 8 | Backup Preparation | `BLOCKED` | Compliance-profile source and reference contracts are absent. |
| 9 | Disaster-Recovery Execution | `BLOCKED` | Compliance-profile recovery contracts are absent. |
| 10 | Progress, Results, and Cancellation | `BLOCKED` | Operation lifecycle streaming and terminal-result contracts are absent. |
| 11 | Disconnection and Recovery | `BLOCKED` | Reconciliation contracts cannot be finalized until triggers and operations exist. |

`IMPLEMENTED` means authoritative schema, generated artifacts, and automated
contract checks exist. `N/A` means no repository code should be invented.

## Ordered pull-request queue

All PRs target `mvp/implementation`. Each contract PR must update schema docs,
generated Python modules, tests, and compatibility checks together.

| ID | Status | Branch | Pull-request title | Required result |
| --- | --- | --- | --- | --- |
| P0 | `IMPLEMENTED` | Existing work | `[TASK][MVP] Define SFP Handshake and Version Negotiation` | Bootstrap v1 selects one mutually supported wire version and binds discovered Provider identity and generation. |
| P1 | `IMPLEMENTED` | `mvp/3-taskmvp-define-provider-manifest-exchange-contract` | `[TASK][MVP] Define Provider Manifest Exchange Contract` | Versioned manifest messages, generic operation/trigger declarations, explicit compliance claims, configuration/runtime/platform schemas, canonical revisions, generated Python bindings, and automated contract checks are implemented locally for issue #3. The explicit in-place correction removes backup source modes and updates schema-1 validation, fixtures, golden revision, and generic-operation tests. This intentional breaking change supersedes the earlier v2 migration approach. Review and GitHub merge state remain user-owned. |
| P2 | `BLOCKED` | `mvp/capability-assessment` | `[TASK][MVP] Define Capability Assessment Contract` | Assess a declared operation identifier against a target and return normalized support, requirements, reasons, and assessment identity. |
| P3 | `BLOCKED` | `mvp/trigger-publication` | `[TASK][MVP] Define Trigger Publication and Acknowledgement Contract` | Define normalized trigger envelopes, source identity, idempotency, publication streaming, and acknowledgement dispositions without introducing SF-AOP. |
| P4 | `BLOCKED` | `mvp/operation-admission` | `[TASK][MVP] Define Operation Admission and Idempotency Contract` | Define immutable operation envelopes, generic identifiers, request fingerprints, and deterministic admission dispositions. |
| P5 | `BLOCKED` | `mvp/operation-lifecycle` | `[TASK][MVP] Define Operation Progress Results and Cancellation Contract` | Define resumable progress observation, immutable terminal results, normalized errors, and explicit cancellation outcomes. |
| P6 | `BLOCKED` | `mvp/backup-preparation` | `[TASK][MVP] Define Backup Preparation Compliance Contract` | Define the exact tagged `materialized_source` / `provider_reference` terminal result schema, consistency boundaries, verification data, and cleanup ownership as a profile over operations; no separate manifest source-mode declaration. |
| P7 | `BLOCKED` | `mvp/disaster-recovery` | `[TASK][MVP] Define Disaster Recovery Compliance Contract` | Define staged/restored inputs, Provider references, reconstructed targets, verification results, and replacement identity without a generic restore operation. |
| P8 | `BLOCKED` | `mvp/sfp-reconciliation` | `[TASK][MVP] Define SFP Disconnection Recovery Contracts` | Define cursors and reconciliation messages needed to resume trigger and operation state after reconnect. |
| P9 | `BLOCKED` | `mvp/sfp-contract-integration` | `[TASK][MVP] Verify the Complete SFP Contract Surface` | Verify imports, package contents, generated-code freshness, compatibility checks, docs, and clean installation for the complete SFP v1 surface. |

## Cross-repository delivery order

For each custom SFP procedure, this repository lands the versioned contract
first. `stateforge-provider-implemntation` then implements the server side, and
`stateforge-agent` integrates the client side. Health may proceed directly in
the runtime repositories because it uses the standard gRPC health contract.

## Definition of done

For each PR: preserve backward compatibility within v1; document ownership,
presence, retry, idempotency, and errors; regenerate rather than edit generated
files; add contract tests; pass Buf and configured Python/docs checks; update
this ledger; prepare the PR draft; and stop for review.
