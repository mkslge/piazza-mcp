from course_mcp.config import get_calendar_config

from .feed_client import CalendarFeedClient
from .parser import ICalendarParser
from .service import CalendarService


_calendar_service: CalendarService | None = None


def get_calendar_service() -> CalendarService:
    """Return the lazily initialized configured calendar service."""
    global _calendar_service

    if _calendar_service is None:
        config = get_calendar_config()
        _calendar_service = CalendarService(
            CalendarFeedClient(config),
            ICalendarParser(config.timezone),
            config.timezone,
        )
    return _calendar_service
