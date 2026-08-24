"""Focused helpers for tests that cross fragile boundaries."""

from collections.abc import Iterable, Mapping
import json
from pathlib import Path
import subprocess
import sys
from typing import TypeVar


_T = TypeVar("_T")


def find_named_item(items: Iterable[_T], name: str) -> _T:
    """Return the one item whose public ``name`` equals ``name``."""
    matches = [item for item in items if getattr(item, "name", None) == name]
    assert len(matches) == 1, (
        f"Expected exactly one item named {name!r}, found {len(matches)}"
    )
    return matches[0]


def assert_sensitive_value_absent(value: object, sentinel: str) -> None:
    """Assert a sentinel is absent from common outward representations."""
    if not sentinel:
        raise ValueError("sentinel must not be empty")
    representations = [str(value), repr(value)]
    if not isinstance(value, str):
        representations.append(
            json.dumps(
                value,
                default=repr,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    for representation in representations:
        assert sentinel not in representation


def run_python_in_clean_process(
    code: str,
    *,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run local source in a subprocess without inheriting credentials."""
    source_root = Path(__file__).resolve().parents[2] / "src"
    clean_environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(source_root),
    }
    if environment is not None:
        clean_environment.update(environment)

    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=clean_environment,
        capture_output=True,
        text=True,
        check=False,
    )
