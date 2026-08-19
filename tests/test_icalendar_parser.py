from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from course_mcp.services.icalendar_parser import (
    CalendarParseError,
    ICalendarParser,
)


FIXTURE = Path(__file__).parent / "fixtures" / "calendar.ics"


def test_parser_normalizes_timed_all_day_and_recurring_events():
    parser = ICalendarParser(ZoneInfo("America/New_York"))

    items = parser.parse(FIXTURE.read_bytes())

    assert len(items) == 3
    timed, all_day, recurring = items
    assert timed.uid == "timed-project"
    assert timed.starts_at == datetime(2026, 8, 20, 3, 59, tzinfo=timezone.utc)
    assert timed.all_day is False
    assert timed.description == "Read chapter, one and bring your notes"
    assert timed.item_url == (
        "https://umd.instructure.com/courses/100/assignments/200"
    )
    assert timed.course_hint is None
    assert timed.item_kind == "unknown"

    assert all_day.starts_at == date(2026, 8, 21)
    assert all_day.ends_at == date(2026, 8, 22)
    assert all_day.all_day is True
    assert all_day.description is None

    assert recurring.starts_at == datetime(
        2026,
        8,
        22,
        10,
        0,
        tzinfo=ZoneInfo("America/New_York"),
    )
    assert recurring.recurrence_id == "2026-08-22T10:00:00-04:00"


def test_parser_resolves_floating_times_in_configured_timezone():
    parser = ICalendarParser(ZoneInfo("America/New_York"))
    content = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:floating
DTSTART:20260822T100000
SUMMARY:Floating event
END:VEVENT
END:VCALENDAR
"""

    item = parser.parse(content)[0]

    assert item.starts_at == datetime(
        2026,
        8,
        22,
        10,
        0,
        tzinfo=ZoneInfo("America/New_York"),
    )


def test_parser_does_not_return_the_private_feed_as_an_item_url():
    parser = ICalendarParser(ZoneInfo("America/New_York"))
    content = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:unsafe-url
DTSTART:20260822T100000Z
SUMMARY:Unsafe URL
URL:https://umd.instructure.com/feeds/calendars/user_secret.ics
END:VEVENT
END:VCALENDAR
"""

    item = parser.parse(content)[0]

    assert item.item_url is None


def test_parser_rejects_malformed_calendar():
    parser = ICalendarParser(ZoneInfo("America/New_York"))

    with pytest.raises(CalendarParseError, match="malformed"):
        parser.parse(b"not an iCalendar document")
