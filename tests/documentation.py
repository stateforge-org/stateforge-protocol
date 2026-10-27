"""Shared assertions for executable documentation examples."""

import json
import re
from typing import Any


def annotated_json_example(
    documentation: str,
    *,
    title: str,
) -> dict[str, Any]:
    """Load one titled JSON example after removing Material annotations."""
    match = re.search(
        rf'``` \{{ \.json \.annotate title="{re.escape(title)}" \}}\n'
        r"(?P<payload>.*?)\n[ ]*```",
        documentation,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(
            f"Could not find documented JSON example {title!r}"
        )

    payload = re.sub(r" \([1-9][0-9]*\)", "", match.group("payload"))
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise AssertionError(
            f"Documented JSON example {title!r} is not an object"
        )
    return value
