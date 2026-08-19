import importlib
import sys
from zoneinfo import ZoneInfo

import pytest


def reload_config(monkeypatch, root_dir=None, root_dir_fallback=None):
    if root_dir is None:
        monkeypatch.delenv("ROOT_DIR", raising=False)
    else:
        monkeypatch.setenv("ROOT_DIR", str(root_dir))

    if root_dir_fallback is None:
        monkeypatch.delenv("ROOT_DIR_", raising=False)
    else:
        monkeypatch.setenv("ROOT_DIR_", str(root_dir_fallback))

    sys.modules.pop("course_mcp.config", None)
    sys.modules.pop("course_mcp.config.config", None)

    return importlib.import_module("course_mcp.config.config")


def test_root_dir_uses_root_dir_environment_value(monkeypatch, tmp_path):
    config = reload_config(monkeypatch, root_dir=tmp_path)

    assert config.ROOT_DIR == tmp_path.resolve()


def test_root_dir_falls_back_to_root_dir_underscore(monkeypatch, tmp_path):
    config = reload_config(monkeypatch, root_dir=tmp_path)
    monkeypatch.delenv("ROOT_DIR", raising=False)
    monkeypatch.setenv("ROOT_DIR_", str(tmp_path))
    monkeypatch.setattr(config, "_load_env_file", lambda env_path: None)

    assert config._get_root_dir() == tmp_path.resolve()


def test_root_dir_must_exist(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing"

    with pytest.raises(RuntimeError, match="ROOT_DIR does not exist"):
        reload_config(monkeypatch, root_dir=missing_path)


def prepare_calendar_config(config, monkeypatch):
    monkeypatch.setattr(config, "_load_env_file", lambda env_path: None)
    monkeypatch.delenv("CANVAS_ICAL_URL", raising=False)
    monkeypatch.delenv("CANVAS_ICAL_PATH", raising=False)
    monkeypatch.delenv("CALENDAR_TIMEZONE", raising=False)


def test_calendar_config_normalizes_webcal_url(monkeypatch, tmp_path):
    config = reload_config(monkeypatch, root_dir=tmp_path)
    prepare_calendar_config(config, monkeypatch)
    monkeypatch.setenv(
        "CANVAS_ICAL_URL",
        "webcal://umd.instructure.com/feeds/calendars/user_test.ics",
    )

    calendar_config = config.get_calendar_config()

    assert calendar_config.url == (
        "https://umd.instructure.com/feeds/calendars/user_test.ics"
    )
    assert calendar_config.path is None
    assert calendar_config.timezone == ZoneInfo("America/New_York")


def test_calendar_config_accepts_local_snapshot(monkeypatch, tmp_path):
    config = reload_config(monkeypatch, root_dir=tmp_path)
    prepare_calendar_config(config, monkeypatch)
    snapshot = tmp_path / "calendar.ics"
    snapshot.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    monkeypatch.setenv("CANVAS_ICAL_PATH", str(snapshot))
    monkeypatch.setenv("CALENDAR_TIMEZONE", "America/Los_Angeles")

    calendar_config = config.get_calendar_config()

    assert calendar_config.url is None
    assert calendar_config.path == snapshot.resolve()
    assert calendar_config.timezone == ZoneInfo("America/Los_Angeles")


def test_calendar_config_is_optional_until_requested(monkeypatch, tmp_path):
    config = reload_config(monkeypatch, root_dir=tmp_path)
    prepare_calendar_config(config, monkeypatch)

    assert config.ROOT_DIR == tmp_path.resolve()
    with pytest.raises(RuntimeError, match="Canvas calendar is not configured"):
        config.get_calendar_config()


def test_calendar_config_rejects_multiple_sources(monkeypatch, tmp_path):
    config = reload_config(monkeypatch, root_dir=tmp_path)
    prepare_calendar_config(config, monkeypatch)
    snapshot = tmp_path / "calendar.ics"
    snapshot.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    monkeypatch.setenv(
        "CANVAS_ICAL_URL",
        "https://umd.instructure.com/feeds/calendars/user_test.ics",
    )
    monkeypatch.setenv("CANVAS_ICAL_PATH", str(snapshot))

    with pytest.raises(RuntimeError, match="Configure only one"):
        config.get_calendar_config()


@pytest.mark.parametrize(
    "url",
    [
        "http://umd.instructure.com/feeds/calendars/user_test.ics",
        "https://example.com/feeds/calendars/user_test.ics",
        "https://umd.instructure.com/courses/123",
    ],
)
def test_calendar_config_rejects_invalid_live_url(monkeypatch, tmp_path, url):
    config = reload_config(monkeypatch, root_dir=tmp_path)
    prepare_calendar_config(config, monkeypatch)
    monkeypatch.setenv("CANVAS_ICAL_URL", url)

    with pytest.raises(RuntimeError, match="CANVAS_ICAL_URL"):
        config.get_calendar_config()


def test_calendar_config_rejects_invalid_timezone(monkeypatch, tmp_path):
    config = reload_config(monkeypatch, root_dir=tmp_path)
    prepare_calendar_config(config, monkeypatch)
    monkeypatch.setenv(
        "CANVAS_ICAL_URL",
        "https://umd.instructure.com/feeds/calendars/user_test.ics",
    )
    monkeypatch.setenv("CALENDAR_TIMEZONE", "not-a-timezone")

    with pytest.raises(RuntimeError, match="valid IANA timezone"):
        config.get_calendar_config()
