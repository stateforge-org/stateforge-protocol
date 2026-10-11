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
