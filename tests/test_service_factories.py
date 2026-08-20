import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

import course_mcp.config.calendar as calendar_config_module
import course_mcp.config.filesystem as filesystem_config_module
from course_mcp.config import CalendarConfig
from course_mcp.services.calendar import factory as calendar_factory
from course_mcp.services.course import factory as course_factory
from course_mcp.services.file import factory as file_factory


CONFIG_ENV_VARS = (
    "ROOT_DIR",
    "ROOT_DIR_",
    "CANVAS_ICAL_URL",
    "CANVAS_ICAL_PATH",
    "CALENDAR_TIMEZONE",
)


def clear_service_config(monkeypatch):
    """Disable project dotenv loading and clear every service variable."""
    monkeypatch.setattr(calendar_config_module, "load_project_env", lambda: None)
    monkeypatch.setattr(filesystem_config_module, "load_project_env", lambda: None)
    for name in CONFIG_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_service_packages_and_server_import_without_loading_config(tmp_path):
    source_root = Path(__file__).resolve().parents[1] / "src"
    environment = os.environ.copy()
    for name in CONFIG_ENV_VARS:
        environment.pop(name, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(source_root)

    code = """
import course_mcp.config.env as config_env

class ForbiddenEnvPath:
    def exists(self):
        raise AssertionError("dotenv was accessed during import")

config_env.PROJECT_ENV_PATH = ForbiddenEnvPath()

import course_mcp.services.calendar
import course_mcp.services.course
import course_mcp.services.file
import course_mcp.server
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


def test_file_factory_reports_missing_root_only_when_requested(monkeypatch):
    clear_service_config(monkeypatch)
    monkeypatch.setattr(file_factory, "_file_service", None)

    with pytest.raises(RuntimeError, match="Missing ROOT_DIR"):
        file_factory.get_file_service()


def test_calendar_factory_reports_missing_source_only_when_requested(monkeypatch):
    clear_service_config(monkeypatch)
    monkeypatch.setattr(calendar_factory, "_calendar_service", None)

    with pytest.raises(RuntimeError, match="Canvas calendar is not configured"):
        calendar_factory.get_calendar_service()


def test_file_factory_reuses_one_instance(monkeypatch, tmp_path):
    monkeypatch.setattr(file_factory, "_file_service", None)
    monkeypatch.setattr(file_factory, "get_root_dir", lambda: tmp_path)

    first = file_factory.get_file_service()
    second = file_factory.get_file_service()

    assert first is second


def test_calendar_factory_reuses_one_instance(monkeypatch, tmp_path):
    config = CalendarConfig(
        url=None,
        path=tmp_path / "calendar.ics",
        timezone=ZoneInfo("America/New_York"),
    )
    monkeypatch.setattr(calendar_factory, "_calendar_service", None)
    monkeypatch.setattr(calendar_factory, "get_calendar_config", lambda: config)

    first = calendar_factory.get_calendar_service()
    second = calendar_factory.get_calendar_service()

    assert first is second


def test_course_factory_injects_configured_file_service(monkeypatch):
    configured_file_service = object()
    monkeypatch.setattr(course_factory, "_course_service", None)
    monkeypatch.setattr(
        course_factory,
        "get_file_service",
        lambda: configured_file_service,
    )

    first = course_factory.get_course_service()
    second = course_factory.get_course_service()

    assert first is second
    assert first.file_service is configured_file_service


def test_course_helpers_delegate_through_lazy_factory(monkeypatch):
    class FakeCourseService:
        def get_courses(self):
            return ["CMSC132"]

    fake_service = FakeCourseService()
    monkeypatch.setattr(course_factory, "get_course_service", lambda: fake_service)

    assert course_factory.get_courses() == ["CMSC132"]
