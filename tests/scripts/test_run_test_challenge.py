from scripts.run_test_challenge import run_challenge


def write_test_project(tmp_path):
    source_root = tmp_path / "src"
    tests_root = tmp_path / "tests"
    source_root.mkdir()
    tests_root.mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["src"]\n',
        encoding="utf-8",
    )
    (source_root / "example.py").write_text(
        "def answer():\n    return 1\n",
        encoding="utf-8",
    )
    (tests_root / "test_example.py").write_text(
        "from example import answer\n\n"
        "def test_answer():\n"
        "    assert answer() == 1\n",
        encoding="utf-8",
    )


def test_challenge_confirms_baseline_and_detects_mutation(tmp_path):
    write_test_project(tmp_path)

    result = run_challenge(
        tmp_path,
        target="src/example.py",
        old="return 1",
        new="return 2",
        test_targets=["tests/test_example.py::test_answer"],
    )

    assert result == 0


def test_challenge_rejects_collection_errors_as_invalid(tmp_path):
    write_test_project(tmp_path)
    target = tmp_path / "src" / "example.py"
    target.write_text(
        "VALUE = 1\n\ndef answer():\n    return VALUE\n",
        encoding="utf-8",
    )

    result = run_challenge(
        tmp_path,
        target="src/example.py",
        old="VALUE = 1",
        new="VALUE = missing_name",
        test_targets=["tests/test_example.py::test_answer"],
    )

    assert result == 2
