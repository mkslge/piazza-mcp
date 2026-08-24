#!/usr/bin/env python3
"""Verify that selected tests fail for one deliberate production mutation.

The baseline and mutation run in a temporary copy containing only ``src/``,
``tests/``, and ``pyproject.toml``. The working tree is never modified.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def _resolve_source_target(project_root: Path, raw_target: str) -> Path:
    target = (project_root / raw_target).resolve()
    try:
        relative = target.relative_to(project_root)
    except ValueError as error:
        raise ValueError("mutation target must be inside the repository") from error
    if not relative.parts or relative.parts[0] != "src" or target.suffix != ".py":
        raise ValueError("mutation target must be a Python file under src/")
    if not target.is_file():
        raise ValueError(f"mutation target does not exist: {raw_target}")
    return relative


def _validate_test_targets(project_root: Path, targets: list[str]) -> None:
    for selector in targets:
        path_text = selector.split("::", 1)[0]
        path = (project_root / path_text).resolve()
        try:
            relative = path.relative_to(project_root)
        except ValueError as error:
            raise ValueError(
                "test selectors must point inside the repository"
            ) from error
        if not relative.parts or relative.parts[0] != "tests":
            raise ValueError("test selectors must point under tests/")


def _copy_test_project(project_root: Path, destination: Path) -> None:
    shutil.copytree(project_root / "src", destination / "src")
    shutil.copytree(project_root / "tests", destination / "tests")
    shutil.copy2(project_root / "pyproject.toml", destination / "pyproject.toml")


def _test_environment(source_root: Path) -> dict[str, str]:
    return {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(source_root),
    }


def _run_tests(project_copy: Path, targets: list[str]) -> int:
    command = [sys.executable, "-m", "pytest", "-q", *targets]
    completed = subprocess.run(
        command,
        cwd=project_copy,
        env=_test_environment(project_copy / "src"),
        check=False,
    )
    return completed.returncode


def run_challenge(
    project_root: Path,
    *,
    target: str,
    old: str,
    new: str,
    test_targets: list[str],
) -> int:
    if not old:
        raise ValueError("--old must not be empty")
    if old == new:
        raise ValueError("--old and --new must differ")

    relative_target = _resolve_source_target(project_root, target)
    _validate_test_targets(project_root, test_targets)

    with tempfile.TemporaryDirectory(prefix="piazza-test-challenge-") as raw:
        project_copy = Path(raw)
        _copy_test_project(project_root, project_copy)

        print("Running unmodified baseline...", flush=True)
        if _run_tests(project_copy, test_targets) != 0:
            print(
                "Challenge invalid: the selected baseline tests failed.",
                flush=True,
            )
            return 2

        copied_target = project_copy / relative_target
        source = copied_target.read_text(encoding="utf-8")
        occurrence_count = source.count(old)
        if occurrence_count != 1:
            raise ValueError(
                "--old must occur exactly once in the target; "
                f"found {occurrence_count} occurrences"
            )
        mutated_source = source.replace(old, new, 1)
        try:
            compile(mutated_source, str(relative_target), "exec")
        except SyntaxError as error:
            raise ValueError(
                f"mutation must remain syntactically valid: {error.msg}"
            ) from error
        copied_target.write_text(mutated_source, encoding="utf-8")

        print(
            "Running the same tests against the isolated mutation...",
            flush=True,
        )
        mutation_exit_code = _run_tests(project_copy, test_targets)
        if mutation_exit_code == 0:
            print(
                "Challenge failed: the tests survived the production mutation.",
                flush=True,
            )
            return 1
        if mutation_exit_code != 1:
            print(
                "Challenge invalid: mutated pytest run did not produce a "
                f"normal test failure (exit code {mutation_exit_code}).",
                flush=True,
            )
            return 2

        print(
            "Challenge passed: the production mutation was detected.",
            flush=True,
        )
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Python file under src/")
    parser.add_argument(
        "--old",
        required=True,
        help="Exact source text that must occur once",
    )
    parser.add_argument("--new", required=True, help="Replacement source text")
    parser.add_argument(
        "tests",
        nargs="+",
        help="One or more pytest selectors under tests/",
    )
    arguments = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[1]
    try:
        return run_challenge(
            project_root,
            target=arguments.target,
            old=arguments.old,
            new=arguments.new,
            test_targets=arguments.tests,
        )
    except ValueError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    sys.exit(main())
