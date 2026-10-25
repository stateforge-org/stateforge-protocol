"""Audit one SFP consumer for violations of Protocol ownership."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_PROTOCOL_PREFIX = "stateforge_protocol.sfp"
_CUSTOM_PROCEDURES = {
    "bootstrap",
    "capability_assessment",
    "manifest",
    "operation_admission",
    "operation_lifecycle",
    "trigger_publication",
}
_OWNED_NAMES = {
    "MAX_DESCRIPTOR_BYTES",
    "MAX_ENDPOINT_GENERATION",
    "MAX_PROVIDER_RECEIVE_BYTES",
    "MAX_PROVIDER_SEND_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "MAX_SESSION_ID_CODE_POINTS",
    "PROCEDURE_LIMITS",
    "SERVICE_NAME",
}


@dataclass(frozen=True, slots=True)
class Finding:
    """Describe one consumer ownership violation."""

    path: str
    line: int
    message: str


@dataclass(slots=True)
class _ProcedureImports:
    """Track how one consumer imports a custom procedure."""

    generated: bool = False
    contract: bool = False
    validation: bool = False


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    """Return simple names assigned by one syntax node."""
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {target.id for target in targets if isinstance(target, ast.Name)}


def _procedure(module: str) -> str | None:
    """Return the versioned SFP procedure addressed by one import."""
    prefix = f"{_PROTOCOL_PREFIX}."
    if not module.startswith(prefix):
        return None
    name = module.removeprefix(prefix).split(".", 1)[0]
    return name if name in _CUSTOM_PROCEDURES else None


def _record_import(
    imports: dict[str, _ProcedureImports],
    module: str,
    names: set[str],
) -> None:
    """Record generated, contract, and validation imports by procedure."""
    procedure = _procedure(module)
    if procedure is None:
        return
    record = imports.setdefault(procedure, _ProcedureImports())
    module_name = module.rsplit(".", 1)[-1]
    record.generated |= "_pb2" in module_name or any(
        "_pb2" in name for name in names
    )
    record.contract |= module.endswith(".contract") or "contract" in names
    record.validation |= (
        module.endswith(".validation") or "validation" in names
    )


def _audit_node(
    node: ast.AST,
    relative: str,
    imports: dict[str, _ProcedureImports],
) -> list[Finding]:
    """Return ownership violations represented by one syntax node."""
    findings: list[Finding] = []
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        names = {alias.name for alias in node.names}
        _record_import(imports, node.module, names)
        if node.module == f"{_PROTOCOL_PREFIX}._validation" or (
            node.module == _PROTOCOL_PREFIX and "_validation" in names
        ):
            findings.append(
                Finding(
                    relative,
                    node.lineno,
                    "consumer imports private Protocol validation",
                )
            )
    elif isinstance(node, ast.Import):
        for alias in node.names:
            _record_import(imports, alias.name, {alias.name})
            if alias.name == f"{_PROTOCOL_PREFIX}._validation":
                findings.append(
                    Finding(
                        relative,
                        node.lineno,
                        "consumer imports private Protocol validation",
                    )
                )
    elif isinstance(node, (ast.Assign, ast.AnnAssign)):
        findings.extend(
            Finding(
                relative,
                node.lineno,
                f"consumer redeclares Protocol-owned {name}",
            )
            for name in _assigned_names(node) & _OWNED_NAMES
        )
    elif (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and (
            node.value.startswith("stateforge.sfp.")
            or node.value == "grpc.health.v1.Health"
        )
    ):
        findings.append(
            Finding(
                relative,
                node.lineno,
                "consumer copies a Protocol-owned service identity",
            )
        )
    return findings


def audit(source: Path) -> list[Finding]:
    """Return ownership violations below one consumer source tree."""
    if not source.is_dir():
        raise ValueError("consumer source directory does not exist")
    findings: list[Finding] = []
    imports: dict[str, _ProcedureImports] = {}
    for path in sorted(source.rglob("*.py")):
        relative = str(path.relative_to(source))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            findings.extend(_audit_node(node, relative, imports))

    for procedure, record in sorted(imports.items()):
        if record.generated and not record.contract:
            findings.append(
                Finding(
                    ".",
                    0,
                    f"{procedure} uses generated bindings without its "
                    "contract",
                )
            )
        if record.generated and not record.validation:
            findings.append(
                Finding(
                    ".",
                    0,
                    f"{procedure} uses generated bindings without public "
                    "validation",
                )
            )
    return findings


def main() -> int:
    """Run the ownership audit and write bounded JSON evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    findings = audit(arguments.source)
    result = {
        "source": str(arguments.source),
        "pythonFileCount": sum(1 for _ in arguments.source.rglob("*.py")),
        "findings": [asdict(finding) for finding in findings],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if findings:
        for finding in findings:
            sys.stderr.write(
                f"{finding.path}:{finding.line}: {finding.message}\n"
            )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main().
    raise SystemExit(main())
