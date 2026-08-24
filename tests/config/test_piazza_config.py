import pytest

import piazza_mcp.config.piazza as piazza_config_module


PIAZZA_ENV_VARS = ("PIAZZA_EMAIL", "PIAZZA_PASSWORD", "PIAZZA_COURSES")


def isolate_config(monkeypatch):
    monkeypatch.setattr(piazza_config_module, "load_project_env", lambda: None)
    for name in PIAZZA_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def configure(monkeypatch):
    monkeypatch.setenv("PIAZZA_EMAIL", "student@example.edu")
    monkeypatch.setenv("PIAZZA_PASSWORD", "private-password")
    monkeypatch.setenv(
        "PIAZZA_COURSES",
        '{"abc123":"CMSC 132","xyz_789":"CMSC 216"}',
    )


def test_piazza_config_loads_credentials_and_course_allowlist(monkeypatch):
    isolate_config(monkeypatch)
    configure(monkeypatch)

    config = piazza_config_module.get_piazza_config()

    assert config.email == "student@example.edu"
    assert config.password == "private-password"
    assert dict(config.courses) == {
        "abc123": "CMSC 132",
        "xyz_789": "CMSC 216",
    }


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("PIAZZA_EMAIL", "Missing PIAZZA_EMAIL"),
        ("PIAZZA_PASSWORD", "Missing PIAZZA_PASSWORD"),
        ("PIAZZA_COURSES", "Missing PIAZZA_COURSES"),
    ],
)
def test_piazza_config_requires_every_value(monkeypatch, missing, message):
    isolate_config(monkeypatch)
    configure(monkeypatch)
    monkeypatch.delenv(missing)

    with pytest.raises(RuntimeError, match=message):
        piazza_config_module.get_piazza_config()


@pytest.mark.parametrize(
    "value",
    [
        "not-json",
        "[]",
        "{}",
        '{"":"Course"}',
        '{"bad/id":"Course"}',
        '{"abc123":""}',
        '{"abc123":4}',
        '{"abc123":"' + "x" * 201 + '"}',
    ],
)
def test_piazza_config_rejects_invalid_course_maps(monkeypatch, value):
    isolate_config(monkeypatch)
    configure(monkeypatch)
    monkeypatch.setenv("PIAZZA_COURSES", value)

    with pytest.raises(RuntimeError, match="PIAZZA_COURSES"):
        piazza_config_module.get_piazza_config()


def test_piazza_config_rejects_duplicate_course_ids(monkeypatch):
    isolate_config(monkeypatch)
    configure(monkeypatch)
    monkeypatch.setenv(
        "PIAZZA_COURSES",
        '{"abc123":"First","abc123":"Second"}',
    )

    with pytest.raises(RuntimeError, match="duplicate course ID"):
        piazza_config_module.get_piazza_config()
