# StateForge Protocol

StateForge Protocol (SFP) defines the local wire contract between the
StateForge Agent and independently running StateForge Providers.

This repository contains only the authoritative Protocol Buffer definitions
and generated language contracts. It contains no Agent implementation,
Provider runtime, or third-party integration logic.

## Contract development

Use Python 3.11+ and Buf. Create an isolated environment and install the package
with its `dev` and `docs` dependency groups. Generated runtime bindings use
pinned official Buf registry plugins; generation therefore needs network
access. The mypy generators run locally from the development environment.

```bash
buf lint
buf format --diff --exit-code
buf generate
python scripts/check_generated.py
buf breaking --against '.git#branch=origin/mvp/implementation'
ruff format --check .
ruff check .
mypy src
pytest
python -m build
mkdocs build --strict
```

Generation preserves handwritten package files. The freshness check generates
twice in isolated temporary directories, rejects nondeterministic output, and
detects modified, missing, and stale generated modules. Keep source schemas,
generated bindings, validation schemas and conformance vectors in the same
change. See the procedure pages and Python contract reference in `docs/` for
schema validation, canonical revisions, and operation fingerprints.

## CI/CD architecture

Protocol automation is split into focused repository-local actions and
reusable workflows. The entry workflows only select when the shared pipeline
runs; validation, packaging, installed verification, and evidence behavior are
defined once.

| Layer | Location | Responsibility |
| --- | --- | --- |
| Contract action | `.github/actions/contracts/validate` | Buf lint and format, deterministic generation, compatibility, fixtures, and the full contract suite |
| Build action | `.github/actions/python/build` | Build one wheel and one sdist and record their SHA-256 hashes and source provenance |
| Installed-test action | `.github/actions/python/test-installed` | Verify and install the exact downloaded wheel in a clean environment outside the checkout |
| Evidence action | `.github/actions/evidence/collect` | Bound logs and record a small, non-secret runner summary |
| Reusable workflows | `.github/workflows/protocol-*.yml` | Compose source, build, and Python 3.11-3.13 installed-package verification across Linux, macOS, and Windows |
| Entry workflows | `protocol-ci.yml`, `protocol-release-candidate.yml` | Supply event-specific artifact names, retention, concurrency, and compatibility baselines |

`protocol-build.yml` is the only build owner. It uploads one immutable artifact
containing the wheel, source distribution, `SHA256SUMS`, and a readable
`PROVENANCE` record. `protocol-installed-test.yml` downloads that artifact,
verifies its hashes, and installs the recorded wheel. It does
not rebuild. The aggregate workflow exposes the artifact name, package version,
and wheel digest so a future publication workflow can consume the same tested
bytes.

The installed-package matrix verifies distribution metadata, `py.typed`, all
generated protobuf and gRPC modules, validation schemas, and packaged
conformance fixtures without a repository `PYTHONPATH`. Release-candidate runs
retain tested artifacts but deliberately do not publish or sign them.

The package action can also be invoked from another repository. The consumer
owns revision selection and checks out Protocol below its workspace; the
builder always resolves and builds the checkout containing the action:

```yaml
- uses: actions/checkout@<immutable-sha>
  with:
    repository: stateforge-org/stateforge-protocol
    ref: <protocol-ref-or-commit>
    path: .stateforge-ci/protocol
    persist-credentials: false

- uses: ./.stateforge-ci/protocol/.github/actions/python/build
  with:
    output-directory: dist/protocol
    evidence-directory: evidence/protocol-build
```

Both destination paths are normalized in the caller workspace before the
source build begins. `PROVENANCE` records the exact commit and ref from the
Protocol checkout, never the consuming repository.

All workflows use read-only repository permissions, pin external actions to
full commit SHAs, disable persisted checkout credentials, set job timeouts, and
key Python caches from `pyproject.toml`. Actionlint validates workflow syntax;
zizmor blocks medium- or high-severity workflow security findings without
receiving a GitHub token. Evidence uploads contain bounded logs and a small,
allow-listed runner summary; they never dump the process environment.

### Workflow interfaces

- `protocol-build-and-verify.yml` accepts `artifact-name`,
  `breaking-against`, and `retention-days`; it returns `artifact-name`,
  `version`, and `wheel-sha256`.
- `protocol-build.yml` accepts artifact/evidence names and retention; it returns
  the exact build identity.
- `protocol-installed-test.yml` accepts the artifact name produced by the build
  workflow plus an evidence prefix and retention.
- `protocol-source-verify.yml` accepts the Buf comparison source plus an
  evidence name and retention.

Pull requests and integration pushes retain artifacts for seven days. Manual
release-candidate runs default to 30 days. Every source, build, and installed
matrix job uploads evidence from the Actions run even when an earlier check
fails.

### Local parity

After installing the `dev` and `docs` dependency groups, run the same source
checks with:

```bash
GOBIN="$(pwd)/.cache/actionlint" \
  go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12
./.cache/actionlint/actionlint
zizmor --offline --persona auditor --min-severity medium .
buf lint
buf format --diff --exit-code
python scripts/check_generated.py
buf breaking --against '.git#branch=origin/mvp/implementation'
ruff format --check .
ruff check .
mypy src
pytest
mkdocs build --strict
python -m build
```

Checksum and provenance handling is intentionally visible in the build and
installed-test actions. The only CI-specific Python helper verifies the
installed wheel's imports and packaged resources from outside the checkout.
