import os
from pathlib import Path
import subprocess
import sys

import pytest

import piazza_mcp.config.piazza as piazza_config_module
from piazza_mcp.services.piazza import factory as piazza_factory


PIAZZA_ENV_VARS = ("PIAZZA_EMAIL", "PIAZZA_PASSWORD", "PIAZZA_COURSES")


def clear_piazza_config(monkeypatch):
    monkeypatch.setattr(piazza_config_module, "load_project_env", lambda: None)
    for name in PIAZZA_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_package_and_server_import_without_loading_config(tmp_path):
    source_root = Path(__file__).resolve().parents[2] / "src"
    environment = os.environ.copy()
    for name in PIAZZA_ENV_VARS:
        environment.pop(name, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(source_root)

    code = """
import piazza_mcp.config.env as config_env

class ForbiddenEnvPath:
    def exists(self):
        raise AssertionError("dotenv was accessed during import")

config_env.PROJECT_ENV_PATH = ForbiddenEnvPath()

import piazza_mcp.services.piazza
import piazza_mcp.server
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_factory_reports_missing_credentials_only_when_requested(monkeypatch):
    clear_piazza_config(monkeypatch)
    monkeypatch.setattr(piazza_factory, "_piazza_service", None)

    with pytest.raises(RuntimeError, match="Missing PIAZZA_EMAIL"):
        piazza_factory.get_piazza_service()


def test_factory_reuses_one_instance(monkeypatch):
    configured = piazza_config_module.PiazzaConfig(
        email="student@example.edu",
        password="private-password",
        courses={"abc123": "CMSC 132"},
    )
    monkeypatch.setattr(piazza_factory, "_piazza_service", None)
    monkeypatch.setattr(piazza_factory, "get_piazza_config", lambda: configured)

    first = piazza_factory.get_piazza_service()
    second = piazza_factory.get_piazza_service()

    assert first is second
