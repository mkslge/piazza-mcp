from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .env import load_project_env


MAX_CALENDAR_BYTES = 5 * 1024 * 1024
CANVAS_CALENDAR_HOST = "umd.instructure.com"


@dataclass(frozen=True)
class CalendarConfig:
    """Configuration for one private Canvas calendar source."""

    url: str | None
    path: Path | None
    timezone: ZoneInfo


def get_calendar_config() -> CalendarConfig:
    """Load and validate optional Canvas calendar configuration on demand."""
    load_project_env()

    raw_url = os.environ.get("CANVAS_ICAL_URL", "").strip()
    raw_path = os.environ.get("CANVAS_ICAL_PATH", "").strip()
    if raw_url and raw_path:
        raise RuntimeError(
            "Configure only one of CANVAS_ICAL_URL or CANVAS_ICAL_PATH"
        )
    if not raw_url and not raw_path:
        raise RuntimeError(
            "Canvas calendar is not configured; set CANVAS_ICAL_URL or "
            "CANVAS_ICAL_PATH"
        )

    calendar_url = _validate_calendar_url(raw_url) if raw_url else None
    calendar_path = _validate_calendar_path(raw_path) if raw_path else None

    timezone_name = os.environ.get(
        "CALENDAR_TIMEZONE",
        "America/New_York",
    ).strip()
    try:
        calendar_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        raise RuntimeError("CALENDAR_TIMEZONE is not a valid IANA timezone") from None

    return CalendarConfig(
        url=calendar_url,
        path=calendar_path,
        timezone=calendar_timezone,
    )


def _validate_calendar_url(raw_url: str) -> str:
    """Normalize a Canvas feed URL without exposing its secret path."""
    if raw_url.lower().startswith("webcal://"):
        raw_url = "https://" + raw_url[len("webcal://") :]

    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError:
        raise RuntimeError("CANVAS_ICAL_URL is not a valid URL") from None

    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname != CANVAS_CALENDAR_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise RuntimeError(
            "CANVAS_ICAL_URL must be an HTTPS URL on the configured Canvas host"
        )
    if not parsed.path.startswith("/feeds/calendars/"):
        raise RuntimeError("CANVAS_ICAL_URL is not a Canvas calendar feed URL")

    return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))


def _validate_calendar_path(raw_path: str) -> Path:
    """Resolve and validate a local iCalendar snapshot path."""
    path = Path(raw_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise RuntimeError("CANVAS_ICAL_PATH must reference an existing file")
    if path.stat().st_size > MAX_CALENDAR_BYTES:
        raise RuntimeError("CANVAS_ICAL_PATH exceeds the 5 MB size limit")
    return path
