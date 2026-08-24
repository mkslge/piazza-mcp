#!/usr/bin/env python3
"""Reject a small set of objective test anti-patterns.

This checker is intentionally conservative. It catches mechanical problems;
human or agent review still owns whether a test protects the right contract.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Iterable


_ALLOW_RE = re.compile(
    r"#\s*test-quality:\s*allow\s+(TQ\d{3})\s+-\s+\S",
    re.IGNORECASE,
)
_IMPORT_ISOLATION_RE = re.compile(
    r"(?:import.*without|without.*import|lazy.*import|import.*lazy|"
    r"import_isolation)"
)
_SENSITIVE_CLAIM_RE = re.compile(
    r"(?:without_(?:private|secret|sensitive)|does_not_leak|redact|privacy|"
    r"hides_sensitive)"
)


@dataclass(frozen=True, order=True)
class Finding:
    path: Path
    line: int
    code: str
    test_name: str
    message: str

    def render(self) -> str:
        return (
            f"{self.path}:{self.line}: {self.code} "
            f"{self.test_name}: {self.message}"
        )


def _call_name(call: ast.Call) -> str:
    function = call.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        parts = [function.attr]
        value = function.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def _is_assertion_mechanism(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return True
    if not isinstance(node, ast.Call):
        return False
    name = _call_name(node)
    leaf = name.rsplit(".", 1)[-1]
    return (
        name in {"pytest.raises", "pytest.warns", "pytest.fail"}
        or leaf.startswith("assert_")
    )


def _walk_executed_test_body(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.AST]:
    """Walk the test body without counting uncalled nested definitions."""
    nodes: list[ast.AST] = []
    pending = list(reversed(function.body))
    while pending:
        node = pending.pop()
        nodes.append(node)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
        ):
            continue
        pending.extend(reversed(list(ast.iter_child_nodes(node))))
    return nodes


def _is_unconditional_assert(node: ast.Assert) -> bool:
    expression = node.test
    if isinstance(expression, ast.Constant):
        return bool(expression.value)
    return False


def _subscript_base_name(node: ast.expr) -> str:
    while isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id.lower()
    if isinstance(node, ast.Attribute):
        return node.attr.lower()
    if isinstance(node, ast.Call):
        return _call_name(node).rsplit(".", 1)[-1].lower()
    return ""


def _is_numeric_tool_lookup(node: ast.Subscript) -> bool:
    if not isinstance(node.slice, ast.Constant) or not isinstance(
        node.slice.value, int
    ):
        return False
    base = _subscript_base_name(node.value)
    return (
        base in {"catalog", "catalogs", "tool", "tools", "tool_list"}
        or base.endswith("_tools")
        or base in {"build_tools", "build_piazza_tools", "list_registered_tools"}
    )


def _imported_helper_names(tree: ast.AST, helper_name: str) -> set[str]:
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "tests.support":
            for imported in node.names:
                if imported.name == helper_name:
                    imported_names.add(imported.asname or imported.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "tests":
            for imported in node.names:
                if imported.name == "support":
                    prefix = imported.asname or imported.name
                    imported_names.add(f"{prefix}.{helper_name}")
        elif isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name == "tests.support":
                    prefix = imported.asname or imported.name
                    imported_names.add(f"{prefix}.{helper_name}")
    return imported_names


def _uses_imported_helper(
    nodes: Iterable[ast.AST],
    imported_names: set[str],
) -> bool:
    for node in nodes:
        if isinstance(node, ast.Call) and _call_name(node) in imported_names:
            return True
    return False


def _suppressed(
    suppressions: dict[int, set[str]],
    code: str,
    line: int,
) -> bool:
    return code in suppressions.get(line, set()) or code in suppressions.get(
        line - 1, set()
    )


def _find_suppressions(source: str) -> dict[int, set[str]]:
    suppressions: dict[int, set[str]] = {}
    for line_number, line in enumerate(source.splitlines(), start=1):
        match = _ALLOW_RE.search(line)
        if match:
            suppressions.setdefault(line_number, set()).add(
                match.group(1).upper()
            )
    return suppressions


def check_file(path: Path) -> list[Finding]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        return [
            Finding(
                path,
                error.lineno or 1,
                "TQ000",
                "<module>",
                error.msg,
            )
        ]

    suppressions = _find_suppressions(source)
    sensitive_helpers = _imported_helper_names(
        tree,
        "assert_sensitive_value_absent",
    )
    clean_process_helpers = _imported_helper_names(
        tree,
        "run_python_in_clean_process",
    )
    findings: list[Finding] = []
    test_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]

    for function in test_functions:
        nodes = _walk_executed_test_body(function)
        if not any(_is_assertion_mechanism(node) for node in nodes):
            if not _suppressed(suppressions, "TQ002", function.lineno):
                findings.append(
                    Finding(
                        path,
                        function.lineno,
                        "TQ002",
                        function.name,
                        "test has no observable assertion or expected failure",
                    )
                )

        for node in nodes:
            if isinstance(node, ast.Assert) and _is_unconditional_assert(node):
                if not _suppressed(suppressions, "TQ001", node.lineno):
                    findings.append(
                        Finding(
                            path,
                            node.lineno,
                            "TQ001",
                            function.name,
                            "assertion is unconditionally true",
                        )
                    )
            if isinstance(node, ast.ExceptHandler) and all(
                isinstance(statement, ast.Pass) for statement in node.body
            ):
                if not _suppressed(suppressions, "TQ003", node.lineno):
                    findings.append(
                        Finding(
                            path,
                            node.lineno,
                            "TQ003",
                            function.name,
                            "exception is swallowed without an assertion",
                        )
                    )
            if isinstance(node, ast.Subscript) and _is_numeric_tool_lookup(node):
                if not _suppressed(suppressions, "TQ004", node.lineno):
                    findings.append(
                        Finding(
                            path,
                            node.lineno,
                            "TQ004",
                            function.name,
                            "tool catalog entry is selected by numeric position",
                        )
                    )

        if _SENSITIVE_CLAIM_RE.search(function.name) and not (
            _uses_imported_helper(nodes, sensitive_helpers)
            or _suppressed(suppressions, "TQ005", function.lineno)
        ):
            findings.append(
                Finding(
                    path,
                    function.lineno,
                    "TQ005",
                    function.name,
                    "privacy claim lacks a negative sentinel assertion",
                )
            )

        if _IMPORT_ISOLATION_RE.search(function.name) and not (
            _uses_imported_helper(nodes, clean_process_helpers)
            or _suppressed(suppressions, "TQ006", function.lineno)
        ):
            findings.append(
                Finding(
                    path,
                    function.lineno,
                    "TQ006",
                    function.name,
                    "import-isolation claim is not exercised in a subprocess",
                )
            )

    return findings


def _python_files(paths: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(
                candidate
                for candidate in path.rglob("*.py")
                if candidate.name.startswith("test_")
                or candidate.stem.endswith("_test")
            )
        elif path.suffix == ".py":
            files.add(path)
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Test files or directories to scan",
    )
    arguments = parser.parse_args(argv)

    files = _python_files(arguments.paths)
    findings = sorted(
        finding for path in files for finding in check_file(path)
    )
    for finding in findings:
        print(finding.render())

    if findings:
        print(f"Found {len(findings)} objective test-quality issue(s).")
        return 1
    print(f"Checked {len(files)} test file(s); no objective issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
