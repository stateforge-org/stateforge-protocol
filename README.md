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
into a temporary directory and detects modified, missing, and stale generated
modules. Keep source schemas, generated bindings, validation schemas and
conformance vectors in the same change. See the procedure pages and Python
contract reference in `docs/` for schema validation, canonical revisions, and
operation fingerprints.
