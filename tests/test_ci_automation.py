"""Contract tests for reusable Protocol CI automation."""

import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / ".github" / "actions"
WORKFLOWS = ROOT / ".github" / "workflows"
SOURCE_ROOT_RESOLUTION_COUNT = 2
CONSUMER_COUNT = 2
MINIMUM_COVERAGE_PERCENT = 95


def read(path: Path) -> str:
    """Read one automation file as UTF-8 text."""
    return path.read_text(encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    """Parse one automation file as a YAML mapping."""
    document = yaml.safe_load(read(path))
    assert isinstance(document, dict)
    return document


def uses_values(document: dict[str, Any]) -> set[str]:
    """Return every action or reusable-workflow reference in a document."""
    values: set[str] = set()
    runs = document.get("runs")
    if isinstance(runs, dict):
        for step in runs.get("steps", []):
            if isinstance(step, dict) and isinstance(step.get("uses"), str):
                values.add(step["uses"])
    jobs = document.get("jobs")
    if isinstance(jobs, dict):
        for job in jobs.values():
            if not isinstance(job, dict):
                continue
            if isinstance(job.get("uses"), str):
                values.add(job["uses"])
            for step in job.get("steps", []):
                if isinstance(step, dict) and isinstance(
                    step.get("uses"), str
                ):
                    values.add(step["uses"])
    return values


def test_protocol_builder_is_location_independent() -> None:
    """Build the Protocol checkout that owns the invoked action."""
    action = read(ACTIONS / "python" / "build" / "action.yml")
    workflow = read(WORKFLOWS / "protocol-build.yml")
    parsed_workflow = load_yaml(WORKFLOWS / "protocol-build.yml")

    assert "ACTION_PATH: ${{ github.action_path }}" in action
    assert (
        action.count("${ACTION_PATH}/../../../..")
        == SOURCE_ROOT_RESOLUTION_COUNT
    )
    assert '"${source_directory}"' in action
    assert 'git -C "${source_directory}" rev-parse --verify HEAD' in action
    assert "${GITHUB_SHA" not in action
    assert 'output_directory="$(mkdir -p' in action
    assert 'evidence_directory="$(mkdir -p' in action
    assert "path: .stateforge-ci/protocol" in workflow
    assert "./.stateforge-ci/protocol/.github/actions/python/build" in workflow
    assert (
        "./.stateforge-ci/protocol/.github/actions/python/build"
        in uses_values(parsed_workflow)
    )


def test_protocol_builder_preserves_artifact_contract() -> None:
    """Keep exact artifacts, hashes, provenance, and public outputs."""
    action = read(ACTIONS / "python" / "build" / "action.yml")

    for artifact in ("stateforge_protocol-*.whl", "*.tar.gz"):
        assert artifact in action
    for record in ("PROVENANCE", "SHA256SUMS"):
        assert record in action
    for output in ("version", "wheel-path", "wheel-sha256"):
        assert f"{output}:" in action


def test_installed_verifier_covers_wheel_and_sdist() -> None:
    """Verify both distribution formats throughout the full matrix."""
    action = read(ACTIONS / "python" / "test-installed" / "action.yml")
    workflow = read(WORKFLOWS / "protocol-installed-test.yml")

    assert "verify-sdist:" in action
    assert "sdist-path=${sdist_path}" in action
    assert "installed-sdist.log" in action
    assert 'verify-sdist: "true"' in workflow
    assert "wheel-conformance.json" in action
    assert "sdist-conformance.json" in action


def test_health_contract_is_registered_in_reusable_validation() -> None:
    """Run focused Health vectors in every standard source-validation path."""
    health_action = read(ACTIONS / "contracts" / "health" / "action.yml")
    contract_action = read(ACTIONS / "contracts" / "validate" / "action.yml")
    source_workflow = read(WORKFLOWS / "protocol-source-verify.yml")
    build_workflow = read(WORKFLOWS / "protocol-build-and-verify.yml")
    release_workflow = read(WORKFLOWS / "protocol-release-candidate.yml")
    contract_document = load_yaml(
        ACTIONS / "contracts" / "validate" / "action.yml"
    )
    source_document = load_yaml(WORKFLOWS / "protocol-source-verify.yml")
    build_document = load_yaml(WORKFLOWS / "protocol-build-and-verify.yml")
    release_document = load_yaml(WORKFLOWS / "protocol-release-candidate.yml")

    assert "tests/test_health_contract.py" in health_action
    assert "./.github/actions/contracts/health" in contract_action
    assert "./.github/actions/contracts/validate" in source_workflow
    assert "./.github/workflows/protocol-source-verify.yml" in build_workflow
    assert (
        "./.github/workflows/protocol-build-and-verify.yml" in release_workflow
    )
    assert "./.github/actions/contracts/health" in uses_values(
        contract_document
    )
    assert "./.github/actions/contracts/validate" in uses_values(
        source_document
    )
    assert "./.github/workflows/protocol-source-verify.yml" in uses_values(
        build_document
    )
    assert "./.github/workflows/protocol-build-and-verify.yml" in uses_values(
        release_document
    )


def test_recovery_contract_is_registered_in_reusable_validation() -> None:
    """Run recovery vectors through every standard source-verification path."""
    recovery_action = read(ACTIONS / "contracts" / "recovery" / "action.yml")
    contract_action = read(ACTIONS / "contracts" / "validate" / "action.yml")
    installed_verifier = read(ROOT / "scripts" / "ci" / "verify_installed.py")
    contract_document = load_yaml(
        ACTIONS / "contracts" / "validate" / "action.yml"
    )

    assert "tests/test_disconnection_recovery_contract.py" in recovery_action
    assert "./.github/actions/contracts/recovery" in contract_action
    assert "_verify_recovery_contracts" in installed_verifier
    assert '"recovery_scenario_count"' in installed_verifier
    assert "./.github/actions/contracts/recovery" in uses_values(
        contract_document
    )


def test_source_validation_enforces_handwritten_branch_coverage() -> None:
    """Keep generated bindings outside a strict handwritten-code gate."""
    contract_action = read(ACTIONS / "contracts" / "validate" / "action.yml")
    configuration = tomllib.loads(read(ROOT / "pyproject.toml"))
    coverage = configuration["tool"]["coverage"]

    assert "python -m pytest --cov" in contract_action
    assert coverage["run"]["branch"] is True
    assert coverage["report"]["fail_under"] == MINIMUM_COVERAGE_PERCENT
    assert coverage["run"]["source"] == [
        "stateforge_protocol",
        "scripts.ci.audit_consumer",
        "scripts.ci.verify_consumer_protocol",
    ]
    assert coverage["run"]["omit"] == [
        "*/sfp/*/v*/*_pb2.py",
        "*/sfp/*/v*/*_pb2_grpc.py",
    ]


def test_complete_gate_runs_independent_consumers_against_exact_wheel() -> (
    None
):
    """Keep Agent and Provider compatibility in the standard release gate."""
    consumer = read(WORKFLOWS / "protocol-consumer-test.yml")
    build = read(WORKFLOWS / "protocol-build-and-verify.yml")
    release = read(WORKFLOWS / "protocol-release-candidate.yml")
    consumer_document = load_yaml(WORKFLOWS / "protocol-consumer-test.yml")
    build_document = load_yaml(WORKFLOWS / "protocol-build-and-verify.yml")
    release_document = load_yaml(WORKFLOWS / "protocol-release-candidate.yml")

    for repository in (
        "stateforge-org/stateforge-agent",
        "stateforge-org/stateforge-provider-python",
    ):
        assert repository in consumer
    assert "sha256sum --check SHA256SUMS" in consumer
    assert "scripts/ci/audit_consumer.py" in consumer
    assert "scripts/ci/verify_consumer_protocol.py" in consumer
    assert consumer.count("protocol-install.json") == CONSUMER_COUNT
    assert "python -m pytest" in consumer
    assert "python -m mypy src" in consumer
    assert "python -m mkdocs build --strict" in consumer
    assert "./.github/workflows/protocol-consumer-test.yml" in build
    for input_name in ("agent-ref", "provider-ref"):
        assert f"{input_name}:" in build
        assert f"{input_name}: ${{{{ inputs.{input_name} }}}}" in release
    assert set(consumer_document["jobs"]) == {"resolve", "agent", "provider"}
    assert "./.github/workflows/protocol-consumer-test.yml" in uses_values(
        build_document
    )
    assert "./.github/workflows/protocol-build-and-verify.yml" in uses_values(
        release_document
    )
