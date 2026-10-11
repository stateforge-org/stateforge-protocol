"""Contract tests for reusable Protocol CI automation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / ".github" / "actions"
WORKFLOWS = ROOT / ".github" / "workflows"
SOURCE_ROOT_RESOLUTION_COUNT = 2


def read(path: Path) -> str:
    """Read one automation file as UTF-8 text."""
    return path.read_text(encoding="utf-8")


def test_protocol_builder_is_location_independent() -> None:
    """Build the Protocol checkout that owns the invoked action."""
    action = read(ACTIONS / "python" / "build" / "action.yml")
    workflow = read(WORKFLOWS / "protocol-build.yml")

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


def test_protocol_builder_preserves_artifact_contract() -> None:
    """Keep exact artifacts, hashes, provenance, and public outputs."""
    action = read(ACTIONS / "python" / "build" / "action.yml")

    for artifact in ("stateforge_protocol-*.whl", "*.tar.gz"):
        assert artifact in action
    for record in ("PROVENANCE", "SHA256SUMS"):
        assert record in action
    for output in ("version", "wheel-path", "wheel-sha256"):
        assert f"{output}:" in action


def test_health_contract_is_registered_in_reusable_validation() -> None:
    """Run focused Health vectors in every standard source-validation path."""
    health_action = read(ACTIONS / "contracts" / "health" / "action.yml")
    contract_action = read(ACTIONS / "contracts" / "validate" / "action.yml")
    source_workflow = read(WORKFLOWS / "protocol-source-verify.yml")
    build_workflow = read(WORKFLOWS / "protocol-build-and-verify.yml")
    release_workflow = read(WORKFLOWS / "protocol-release-candidate.yml")

    assert "tests/test_health_contract.py" in health_action
    assert "./.github/actions/contracts/health" in contract_action
    assert "./.github/actions/contracts/validate" in source_workflow
    assert "./.github/workflows/protocol-source-verify.yml" in build_workflow
    assert (
        "./.github/workflows/protocol-build-and-verify.yml"
        in release_workflow
    )
