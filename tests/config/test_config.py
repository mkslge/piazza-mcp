from zoneinfo import ZoneInfo

import pytest

import course_mcp.config.calendar as calendar_config_module
import course_mcp.config.filesystem as filesystem_config_module


CONFIG_ENV_VARS = (
    "ROOT_DIR",
    "ROOT_DIR_",
    "CANVAS_ICAL_URL",
    "CANVAS_ICAL_PATH",
    "CALENDAR_TIMEZONE",
)


def isolate_config(monkeypatch):
    """Prevent tests from reading private values from the project dotenv file."""
    monkeypatch.setattr(calendar_config_module, "load_project_env", lambda: None)
    monkeypatch.setattr(filesystem_config_module, "load_project_env", lambda: None)
    for name in CONFIG_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_root_dir_uses_root_dir_environment_value(monkeypatch, tmp_path):
    isolate_config(monkeypatch)
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))

    assert filesystem_config_module.get_root_dir() == tmp_path.resolve()


def test_root_dir_falls_back_to_root_dir_underscore(monkeypatch, tmp_path):
    isolate_config(monkeypatch)
    monkeypatch.setenv("ROOT_DIR_", str(tmp_path))

    assert filesystem_config_module.get_root_dir() == tmp_path.resolve()


def test_root_dir_must_exist(monkeypatch, tmp_path):
    isolate_config(monkeypatch)
    missing_path = tmp_path / "missing"
    monkeypatch.setenv("ROOT_DIR", str(missing_path))

    with pytest.raises(RuntimeError, match="ROOT_DIR does not exist"):
        filesystem_config_module.get_root_dir()


def test_calendar_config_normalizes_webcal_url(monkeypatch):
    isolate_config(monkeypatch)
    monkeypatch.setenv(
        "CANVAS_ICAL_URL",
        "webcal://umd.instructure.com/feeds/calendars/user_test.ics",
    )

    calendar_config = calendar_config_module.get_calendar_config()

    assert calendar_config.url == (
        "https://umd.instructure.com/feeds/calendars/user_test.ics"
    )
    assert calendar_config.path is None
    assert calendar_config.timezone == ZoneInfo("America/New_York")


def test_calendar_config_accepts_local_snapshot(monkeypatch, tmp_path):
    isolate_config(monkeypatch)
    snapshot = tmp_path / "calendar.ics"
    snapshot.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    monkeypatch.setenv("CANVAS_ICAL_PATH", str(snapshot))
    monkeypatch.setenv("CALENDAR_TIMEZONE", "America/Los_Angeles")

    calendar_config = calendar_config_module.get_calendar_config()

    assert calendar_config.url is None
    assert calendar_config.path == snapshot.resolve()
    assert calendar_config.timezone == ZoneInfo("America/Los_Angeles")


def test_calendar_config_is_optional_until_requested(monkeypatch, tmp_path):
    isolate_config(monkeypatch)
    monkeypatch.setenv("ROOT_DIR", str(tmp_path))

    assert filesystem_config_module.get_root_dir() == tmp_path.resolve()
    with pytest.raises(RuntimeError, match="Canvas calendar is not configured"):
        calendar_config_module.get_calendar_config()


def test_calendar_config_rejects_multiple_sources(monkeypatch, tmp_path):
    isolate_config(monkeypatch)
    snapshot = tmp_path / "calendar.ics"
    snapshot.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    monkeypatch.setenv(
        "CANVAS_ICAL_URL",
        "https://umd.instructure.com/feeds/calendars/user_test.ics",
    )
    monkeypatch.setenv("CANVAS_ICAL_PATH", str(snapshot))

    with pytest.raises(RuntimeError, match="Configure only one"):
        calendar_config_module.get_calendar_config()


@pytest.mark.parametrize(
    "url",
    [
        "http://umd.instructure.com/feeds/calendars/user_test.ics",
        "https://example.com/feeds/calendars/user_test.ics",
        "https://umd.instructure.com/courses/123",
        "https://user:password@umd.instructure.com/feeds/calendars/user_test.ics",
        "https://umd.instructure.com:invalid/feeds/calendars/user_test.ics",
    ],
)
def test_calendar_config_rejects_invalid_live_url(monkeypatch, url):
    isolate_config(monkeypatch)
    monkeypatch.setenv("CANVAS_ICAL_URL", url)

    with pytest.raises(RuntimeError, match="CANVAS_ICAL_URL") as error:
        calendar_config_module.get_calendar_config()

    assert url not in str(error.value)


def test_calendar_config_rejects_invalid_timezone(monkeypatch):
    isolate_config(monkeypatch)
    monkeypatch.setenv(
        "CANVAS_ICAL_URL",
        "https://umd.instructure.com/feeds/calendars/user_test.ics",
    )
    monkeypatch.setenv("CALENDAR_TIMEZONE", "not-a-timezone")

    with pytest.raises(RuntimeError, match="valid IANA timezone"):
        calendar_config_module.get_calendar_config()


def test_calendar_config_rejects_missing_snapshot_without_exposing_path(
    monkeypatch,
    tmp_path,
):
    isolate_config(monkeypatch)
    missing_path = tmp_path / "private-calendar-name.ics"
    monkeypatch.setenv("CANVAS_ICAL_PATH", str(missing_path))

    with pytest.raises(RuntimeError, match="existing file") as error:
        calendar_config_module.get_calendar_config()

    assert str(missing_path) not in str(error.value)


def test_calendar_config_rejects_oversized_snapshot(monkeypatch, tmp_path):
    isolate_config(monkeypatch)
    monkeypatch.setattr(calendar_config_module, "MAX_CALENDAR_BYTES", 5)
    snapshot = tmp_path / "calendar.ics"
    snapshot.write_bytes(b"123456")
    monkeypatch.setenv("CANVAS_ICAL_PATH", str(snapshot))

    with pytest.raises(RuntimeError, match="exceeds the 5 MB size limit"):
        calendar_config_module.get_calendar_config()
