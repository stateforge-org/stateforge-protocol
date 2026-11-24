---
name: stateforge-rust-development
description: Apply the shared StateForge Rust engineering standard when designing, implementing, testing, packaging, or reviewing Rust crates, build scripts, generated bindings, and language adapters. Use with the repository-specific architecture skill.
---

# StateForge Rust Development

Write maintainable, idiomatic Rust with one authoritative implementation of each
rule. Apply this standard to Protocol, Provider Runtime, Engine Runtime, and
their native language adapters. Repository-specific skills define ownership,
scope, and product behavior; this skill defines common engineering practice.

## Establish the design before coding

- Inspect the existing crate layout, dependency APIs, toolchain, generated
  types, and tests before choosing an implementation. Prefer a dependency's
  documented safe API to a custom workaround; consult the pinned dependency's
  source or official documentation if necessary.
- Identify which layer owns the behavior and which rules the type system,
  generated code, or existing library already guarantees. Do not duplicate
  those rules in another crate or language adapter.
- Introduce a crate, module, wrapper, constructor, dependency, or trait only
  when it provides a concrete ownership, safety, reuse, or API boundary.
  MVP code need not preserve an inferior unpublished API.

## Organize crate code by responsibility

- Keep `lib.rs` and `main.rs` focused on module declarations, public exports,
  initialization, and application entry points. Put substantive domain
  behavior, errors, and tests in the modules that own them.
- Mirror meaningful domain boundaries in named files and directories. Prefer
  modern Rust module paths such as `sfp/bootstrap/v1.rs` and
  `sfp/bootstrap/v1/validation.rs`. Keep generated includes at the correct
  module depth. Do not create empty placeholder modules or catch-all helpers.
- For generated wire contracts, use generated message types directly. Do not
  recreate the message as a handwritten model or provide a constructor merely
  to populate fields already exposed by the generated type. A separate
  domain model or constructor is justified when it enforces a real invariant
  or provides distinct behavior beyond wire representation.
- Keep semantic validators close to the owning domain. Accept the existing
  message by reference and validate only invariants not already enforced by
  its types. Return a structured `Result`; use the owning procedure's error
  type. Do not revalidate scalar bounds guaranteed by a Rust integer type.
- Keep language adapters thin: translate existing language data into the
  Rust contract, invoke the authoritative implementation, and map results
  and errors. Do not maintain parallel validation or lifecycle decisions.
- Keep public APIs intentional. Document their error conditions, units,
  ownership, thread safety, and cancellation behavior where applicable.

## Prefer safe and explicit implementations

- Forbid handwritten `unsafe` in safe crates, including build scripts.
  Use safe dependency interfaces when they exist. Never introduce unsafe
  environment mutation just to configure a compiler or library.
- Allow unsafe only at a technically unavoidable, approved boundary such as
  raw native FFI. Isolate it in the smallest appropriate crate or module,
  document every safety invariant, and expose a safe interface. Explicitly
  deny unsafe operations in unsafe functions and undocumented unsafe blocks
  where unsafe is permitted; do not relax the safety policy of unrelated
  crates. Follow the repository's FFI ownership and panic-containment rules.
- Prefer ordinary Rust types and explicit errors over sentinel values,
  global state, or panics for expected invalid input.

## Keep builds and artifacts clean

- Use `build.rs` only for real build-time work such as code generation or
  native compilation. Keep it deterministic, cross-platform, and limited to
  Cargo's declared inputs and output directories.
- Use Cargo's existing environment variables for crate-local paths. When
  multiple crates need repository-level inputs, configure a named,
  config-relative repository-root variable in workspace Cargo configuration;
  do not infer the root by climbing a fixed number of parent directories.
  Prefer passing configuration directly rather than mutating the process
  environment.
- Generate language bindings from the authoritative contract source. Never
  hand-edit generated code or copy generated definitions into handwritten
  modules.
- Keep test fixtures in their single source/test corpus. Do not copy them
  during compilation or ship them in runtime wheels or binaries. Pass the
  fixture location explicitly to installed-artifact tests. Include test
  sources and fixtures in source distributions when needed to reproduce
  verification. Retain schemas and other data actually required at runtime.

## Write tests that prove behavior

- Test observable outcomes of real implementations: successful inputs,
  rejected inputs, boundary conditions, state transitions, and error mapping
  as relevant. Avoid tests that merely compare a hardcoded value with another
  constant, call a demonstration-only function, or check a dependency exists.
- For conformance, use shared, language-neutral inputs and independently
  specified expected outcomes. Execute the actual implementation and assert
  the outcome; comparing fixture fields with an example constant is not
  conformance. Test each supported binding or adapter against the same rules.
- A temporary packaging smoke probe may be useful before a real contract
  exists. Identify it as such, keep it out of the public API, and replace it
  with an installed-artifact check against real behavior as soon as possible.
  Do not keep it as a permanent contract test.
- Verify packaged artifacts in clean environments, not just source-tree
  imports or successful compilation. Inspect artifact contents and prove
  required runtime resources are present and test-only resources absent.

## Enforce and review the standard

- Declare the workspace's edition, MSRV, resolver and lint policy. Inherit
  common lints for all ordinary crates (`[lints] workspace = true`). In
  workspaces that need no unsafe code, set
  `[workspace.lints.rust] unsafe_code = "forbid"`. If a later FFI crate truly
  requires unsafe, keep safe crates protected and define a narrowly scoped,
  documented lint policy for that crate instead of weakening everyone.
- Centralize shared dependency versions and package metadata at the
  workspace root. Track `Cargo.lock` when the workspace distributes
  executable or native artifacts or requires reproducible locked checks.
- Require formatting, locked-dependency builds, strict Clippy, tests,
  rustdoc, and the declared minimum Rust version in the configured verification
  path as applicable. Use the actual supported feature, platform, language,
  and artifact matrices. Do not claim a matrix passed when only one local
  target was exercised.
- Before handing off, review the changed code against the preceding rules:
  correct module ownership, existing safe APIs, necessary abstractions,
  one authoritative implementation, meaningful tests, and clean artifacts.
  These are review questions, not arbitrary file-length or source-text tests.
  Report verified checks and any gaps; do not bypass gates to get a green run.

Typical Cargo checks:

```sh
cargo fmt --all -- --check
cargo check --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo doc --workspace --no-deps --locked
```

Use the minimum-version toolchain and repository's additional checks too.

Authoritative references: [Rust Book: modules](https://doc.rust-lang.org/book/ch07-05-separating-modules-into-different-files.html),
[Rust API Guidelines](https://rust-lang.github.io/api-guidelines/),
[Cargo workspaces](https://doc.rust-lang.org/cargo/reference/workspaces.html),
[Cargo build scripts](https://doc.rust-lang.org/cargo/reference/build-scripts.html),
and the pinned dependency's own documentation.
