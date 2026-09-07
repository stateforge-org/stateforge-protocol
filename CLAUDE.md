# StateForge Protocol repository instructions

Read `.claude/MVP_PLAN.md` before planning or changing this repository. It is
the delivery ledger and identifies the next reviewable contract change.

Use `stateforge-python-development` for handwritten Python, packaging, tests,
and docs; `stateforge-protocol-development` for every SFP contract change; and
`stateforge-pr-review` when reviewing or drafting a pull request. Their
instructions live under `.claude/skills/`.

## Delivery discipline

- Work on one plan item at a time and do not define later procedures inside an
  earlier pull request.
- Target `mvp/implementation`. Use `mvp/<issue-slug>` for issue branches and
  `[TASK][MVP] Title` for issue and pull-request titles.
- The user owns GitHub mutations. Do not create issues, open pull requests,
  push, or merge unless explicitly instructed.
- End each completed item with a human-readable PR draft and stop for review.
- Update `.claude/MVP_PLAN.md` when implementation evidence changes. Existing
  design documentation alone is not wire-contract implementation.

## MVP boundary

The active phase is SFP, the local Agent-to-Provider protocol. SF-AOP and the
StateForge Control Plane are mandatory MVP phases, but SF-AOP is not yet
designed. SFP implementation will inform that design. Never classify either
phase as optional, post-MVP, or excluded.

Do not introduce SF-AOP schemas or Control Plane APIs in an SFP pull request.
Their detailed PR plans will be written after the local SFP phase.

## Repository boundary

This repository contains authoritative Protocol Buffer sources and generated
language contracts. It contains no Agent client behavior, Provider server
runtime, third-party integration, BackupEngine, or Control Plane logic.

Operations are namespaced string identifiers rather than a closed enum. Backup
and disaster recovery are predefined compliance profiles constructed on the
generic operation model. Contracts must leave room for custom operations.

Edit `.proto` sources first. Never hand-edit generated `_pb2.py`, `_pb2.pyi`,
`_pb2_grpc.py`, or `_pb2_grpc.pyi` files. Regenerate them with the checked-in
Buf configuration and keep generated code synchronized in the same PR.

Endpoint discovery is a filesystem contract and health uses the standard gRPC
health service; neither requires a custom StateForge protobuf merely to make
the procedure list appear uniform.

## Review and verification

- Review the wire semantics, compatibility, field ownership, presence rules,
  idempotency, and error mapping for the active plan item.
- Follow the Python Packaging User Guide, PEP 8, PEP 257, PEP 484, and the
  repository's `pyproject.toml` for generated-package and handwritten code.
- Tests are automated behavioral gates. Do not substitute manual experiments
  or qualitatively review test files unless requested.
- Run Buf lint and generation checks plus Ruff, strict mypy, pytest, package
  build, and strict MkDocs build where applicable.
- Preserve unrelated files, including the untracked `.idea/` directory.
