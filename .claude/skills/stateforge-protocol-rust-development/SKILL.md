---
name: stateforge-protocol-rust-development
description: Design, implement, test, or package Rust-native contracts and libraries in the StateForge Protocol repository, including the Python binding used by the Python Agent. Use alongside stateforge-protocol-development for SFP semantics and ownership.
---

# StateForge Protocol Rust Development

Implement Protocol behavior once in Rust for the MVP, with language bindings
acting as thin interfaces. The Agent remains Python; this skill does not move
Agent orchestration into Rust.

Read and follow [the shared Rust engineering standard](../stateforge-rust-development/SKILL.md)
before designing, implementing, packaging, testing, or reviewing Rust code.
This skill adds Protocol-specific ownership and migration rules.

## Establish scope and authority

Before editing:

1. Read `AGENTS.md`, `CLAUDE.md`, root `STATEFORGE_DPT.md`, and the selected
   Issue's acceptance criteria and mapped DPT step.
2. Read `stateforge-protocol-development` for the active SFP procedure,
   ownership, and wire semantics.
3. Inspect the Cargo workspace, Python package, generated code, build system,
   tests, and CI before choosing where code or generated artifacts belong.
4. Keep changes within the Protocol repository and selected milestone. Agent
   call-site rewrites belong to the Agent repository and its own milestone.

Use the source appropriate to each wire contract:

- `.proto` files are authoritative for protobuf messages and services. Generate
  Rust and Python message bindings from the same source; never hand-edit
  generated bindings.
- For non-protobuf contracts, choose one normative source and make Rust the
  executable implementation. Do not maintain independent handwritten Python
  validation or serialization rules. Generated schemas and language adapters
  are derived artifacts, not competing authorities.
- Keep shared conformance vectors language-neutral and run them against the
  Rust implementation and every binding that consumes the contract.

Preserve required SFP wire behavior and compatibility. Do not preserve an old
Python API merely for compatibility: this is an MVP migration. Define the
Python-facing API needed by the Python Agent, use the Rust implementation
through a supported native binding, and remove superseded duplicate behavior
within the active milestone's scope. Do not rewrite Agent orchestration or
change its repository as part of Protocol work.

## Structure Protocol code deliberately

- Use a Cargo workspace for the Protocol core and Python extension. Keep
  crate boundaries aligned with implementation ownership and packaging.
- Mirror the SFP procedure and version hierarchy in the Rust core. Keep
  generated types and handwritten contract metadata and semantic validators
  in the owning procedure's modules. Do not implement Agent or Provider
  runtime state in those modules.
- Keep the Python layer ergonomic but thin. It translates Python values and
  Rust errors; it must not become a second owner of contract rules. Never
  allow a Rust panic to cross the binding boundary.

## Test the contract and binding boundary

- Test contract behavior in Rust, including valid inputs, malformed inputs,
  limits, serialization, and compatibility cases that apply to the contract.
- Use shared conformance fixtures for Rust and Python-facing behavior. Do not
  treat two independently implemented validators that happen to pass the same
  examples as proof of a single authoritative implementation.
- Test the built Python extension and installed wheel in a clean environment;
  a source-tree import is not sufficient. Include the Python versions,
  platforms, and architectures the MVP actually supports.
- Keep protobuf generation and compatibility checks in the verification path
  whenever `.proto` sources change.
- Do not claim that a binding works based only on Rust unit tests. Exercise the
  public Python API and the Agent integration in their respective repositories
  when those changes are in scope.

Use the commands configured by this repository. For applicable Cargo crates,
the baseline is:

```sh
cargo fmt --all -- --check
cargo check --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo doc --workspace --no-deps
```

Run Buf, Python, package, and documentation checks required by the changed
source and repository CI. Report checks that could not run; do not infer
successful packaging from source tests.

## Keep ownership and delivery boundaries

- Protocol owns SFP wire contracts, generated protocol types, and
  context-independent contract behavior.
- Agent owns Python orchestration and local lifecycle behavior. Its use of the
  Rust-backed Protocol API does not make Agent behavior part of this crate.
- Provider Runtime owns Provider execution behavior. Do not move Provider
  runtime concerns into this repository.
- Follow the selected DPT milestone. Humans own pushing, PR creation, formal
  review, and merging; local implementation and verification do not complete a
  DPT step.

Consult the current official references when needed:

- [The Cargo Book](https://doc.rust-lang.org/cargo/)
- [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/)
- [PyO3 guide](https://pyo3.rs/)
- [Maturin guide](https://www.maturin.rs/)
