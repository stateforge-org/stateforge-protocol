# StateForge Protocol repository instructions

Read root `STATEFORGE_DPT.md` for the shared milestone declaration and
generated delivery snapshot, not an editable local implementation ledger.
For every milestone assignment, read and follow
`.agents/skills/stateforge-dpt-milestone/SKILL.md`. It applies equally to
agents reached through `AGENTS.md` or `CLAUDE.md`.

Use `stateforge-python-development` for Python, packaging, tests, and docs;
`stateforge-protocol-development` for SFP contracts or integrations; and
`stateforge-documentation` for public documentation structure, writing,
versioning, visuals, and walkthroughs. Use `stateforge-pr-review` when drafting
a PR description or assisting a review. These engineering skills live under
`.claude/skills/`.

## Delivery discipline

- Work only on the human-selected Issue and its mapped DPT step. Use the
  Issue's acceptance criteria for implementation and DPT for ownership,
  prerequisites, and the declared result. Ask about material disagreements.
- Follow `stateforge-dpt-milestone` for dependency checks, branch context,
  verification, scoped local commits, and the human handoff. Never infer the
  assignment from queue order or start a later milestone opportunistically.
- Humans own pushing, Issue/PR mutations, PR creation, formal review, and
  merging. Local implementation commits are allowed; they do not complete a
  step. End with verification evidence and a human-readable PR draft.
- Do not edit `STATEFORGE_DPT.md`, its manifest/revision/statuses, or SQLite to
  record implementation progress. Plan changes are managed through DPT in a
  separate human-requested workflow.
- A step is delivered only after its correctly associated PR has been
  reviewed by a human and merged into the intended integration branch.
  DPT reconciliation records the GitHub-derived state. A local commit,
  passing tests, an approval, or a closed Issue alone is not completion.
- This project's current source/integration branch is `mvp/implementation`.
  Prefer the human-selected Issue branch and DPT's declared branch; never use
  descriptive placeholders such as "Existing work" as branch names.
  Issue and PR titles currently use `[TASK][MVP] Title`.

## MVP boundary

The active phase is SFP, the local Agent-to-Provider protocol. SF-AOP and the
StateForge Control Plane are mandatory MVP phases, but SF-AOP is not yet
designed. SFP implementation will inform that design. Never classify either
phase as optional, post-MVP, or excluded.

Do not introduce SF-AOP schemas or Control Plane APIs in an SFP pull request.
Their detailed PR plans will be written after the local SFP phase.

The local SFP phase must work across Protocol, Provider, and Agent, including
backup-engine-backed backup and disaster recovery. Only afterward are the
SF-AOP contracts and Control Plane milestones defined from that proven
behavior. The end-to-end MVP must let a trigger create a coordinated snapshot
and use that snapshot for disaster recovery. These are product-level exit
conditions, not permission to implement additional milestones.

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
