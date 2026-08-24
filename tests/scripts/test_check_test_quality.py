from scripts.check_test_quality import check_file, main


def write_test_file(tmp_path, source):
    path = tmp_path / "test_example.py"
    path.write_text(source, encoding="utf-8")
    return path


def finding_codes(path):
    return {finding.code for finding in check_file(path)}


def test_checker_accepts_observable_assertions_and_expected_failures(tmp_path):
    path = write_test_file(
        tmp_path,
        """
import pytest

def test_result():
    assert calculate() == 3

def test_error():
    with pytest.raises(ValueError):
        calculate()
""",
    )

    assert check_file(path) == []


def test_checker_scans_pytest_suffix_filename_convention(tmp_path):
    path = tmp_path / "example_test.py"
    path.write_text(
        "def test_no_oracle():\n    calculate()\n",
        encoding="utf-8",
    )

    assert main([str(tmp_path)]) == 1


def test_checker_rejects_missing_and_unconditional_assertions(tmp_path):
    path = write_test_file(
        tmp_path,
        """
def test_no_oracle():
    calculate()

def test_tautology():
    assert True
""",
    )

    assert finding_codes(path) == {"TQ001", "TQ002"}


def test_checker_does_not_count_an_uncalled_nested_assertion(tmp_path):
    path = write_test_file(
        tmp_path,
        """
def test_no_oracle():
    def never_called():
        assert calculate() == 3
    calculate()
""",
    )

    assert finding_codes(path) == {"TQ002"}


def test_checker_does_not_assume_repeated_calls_are_equal(tmp_path):
    path = write_test_file(
        tmp_path,
        """
def test_factory_results_match():
    assert factory() == factory()
""",
    )

    assert check_file(path) == []


def test_checker_rejects_positional_tool_catalog_access(tmp_path):
    path = write_test_file(
        tmp_path,
        """
def test_schema():
    tools = build_tools()
    assert tools[0].name == "first"
""",
    )

    assert finding_codes(path) == {"TQ004"}


def test_checker_reports_boundary_claim_violations(tmp_path):
    path = write_test_file(
        tmp_path,
        """
def test_response_without_private_values():
    assert response.is_safe

def test_server_import_without_config():
    assert import_server()
""",
    )

    assert finding_codes(path) == {"TQ005", "TQ006"}


def test_checker_requires_dedicated_boundary_helpers(tmp_path):
    path = write_test_file(
        tmp_path,
"""
def test_response_without_private_values():
    fake_assert_sensitive_value_absent(response, sentinel)
    assert response is not None

def test_server_import_without_config():
    result = do_not_run_python_in_clean_process(code, cwd=tmp_path)
    assert result.returncode == 0
""",
    )

    assert finding_codes(path) == {"TQ005", "TQ006"}


def test_checker_accepts_dedicated_boundary_helpers(tmp_path):
    path = write_test_file(
        tmp_path,
        """
from tests.support import (
    assert_sensitive_value_absent,
    run_python_in_clean_process,
)

def test_response_without_private_values():
    assert_sensitive_value_absent(response, sentinel)

def test_server_import_without_config():
    result = run_python_in_clean_process(code, cwd=tmp_path)
    assert result.returncode == 0
""",
    )

    assert check_file(path) == []


def test_checker_accepts_reasoned_line_suppression(tmp_path):
    path = write_test_file(
        tmp_path,
        """
def test_order_is_the_contract():
    tools = build_tools()
    assert tools[0].name == "first"  # test-quality: allow TQ004 - order contract
""",
    )

    assert check_file(path) == []
