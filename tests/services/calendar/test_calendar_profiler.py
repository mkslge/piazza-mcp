import json
from zoneinfo import ZoneInfo

import pytest

from course_mcp.services.calendar import (
    CalendarFeedProfiler,
    CalendarParseError,
    ICalendarParser,
)


SYNTHETIC_CALENDAR = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:PRIVATE_UID_ASSIGNMENT
DTSTART:20260820T120000Z
SUMMARY:PRIVATE_ASSIGNMENT_TITLE
DESCRIPTION:PRIVATE_ASSIGNMENT_DESCRIPTION
LOCATION:PRIVATE_ASSIGNMENT_LOCATION
CATEGORIES:PRIVATE_COURSE_LABEL
URL:https://umd.instructure.com/courses/111/assignments/222?token=PRIVATE_URL_QUERY
RRULE:FREQ=WEEKLY;COUNT=2
RDATE:20260827T120000Z
EXDATE:20260903T120000Z
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
UID:PRIVATE_UID_ALL_DAY
DTSTART;VALUE=DATE:20260821
SUMMARY:PRIVATE_ALL_DAY_TITLE
URL:https://example.com/events/PRIVATE_EXTERNAL_PATH
END:VEVENT
BEGIN:VEVENT
UID:PRIVATE_UID_FLOATING
DTSTART:20260822T100000
SUMMARY:PRIVATE_FLOATING_TITLE
URL:https://umd.instructure.com/courses/111/pages/PRIVATE_CANVAS_PATH
RECURRENCE-ID:20260822T100000
END:VEVENT
BEGIN:VEVENT
UID:PRIVATE_UID_SKIPPED
DTSTART;TZID=America/New_York:20260823T090000
LOCATION:PRIVATE_SKIPPED_LOCATION
END:VEVENT
END:VCALENDAR
"""


def profiler() -> CalendarFeedProfiler:
    parser = ICalendarParser(ZoneInfo("America/New_York"))
    return CalendarFeedProfiler(parser)


def test_profiler_reports_only_aggregate_calendar_shapes():
    profile = profiler().profile(SYNTHETIC_CALENDAR)

    assert profile == {
        "total_event_count": 4,
        "usable_event_count": 3,
        "skipped_event_count": 1,
        "normalized_event_shapes": {"all_day": 1, "timed": 2},
        "start_shapes": {
            "date": 1,
            "floating_datetime": 1,
            "timezone_aware_datetime": 2,
            "missing_or_invalid": 0,
        },
        "field_presence": {
            "categories": 1,
            "location": 2,
            "url": 3,
            "rrule": 1,
            "rdate": 1,
            "exdate": 1,
            "recurrence_id": 1,
            "status": 1,
        },
        "url_shapes": {
            "canvas_assignment": 1,
            "canvas_other": 1,
            "external_or_invalid": 1,
            "missing": 1,
        },
    }


def test_profiler_never_serializes_private_event_values():
    serialized = json.dumps(profiler().profile(SYNTHETIC_CALENDAR))

    for private_marker in (
        "PRIVATE_UID",
        "PRIVATE_ASSIGNMENT",
        "PRIVATE_COURSE_LABEL",
        "PRIVATE_URL_QUERY",
        "PRIVATE_EXTERNAL_PATH",
        "PRIVATE_CANVAS_PATH",
        "PRIVATE_SKIPPED_LOCATION",
        "/courses/111",
    ):
        assert private_marker not in serialized


def test_profiler_accepts_calendar_with_no_events():
    content = b"BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"

    profile = profiler().profile(content)

    assert profile["total_event_count"] == 0
    assert profile["usable_event_count"] == 0
    assert profile["skipped_event_count"] == 0
    assert sum(profile["field_presence"].values()) == 0
    assert sum(profile["url_shapes"].values()) == 0


def test_profiler_reports_calendar_when_every_event_is_unusable():
    content = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:PRIVATE_UNUSABLE_UID
DTSTART:20260820T120000Z
END:VEVENT
END:VCALENDAR
"""

    profile = profiler().profile(content)

    assert profile["total_event_count"] == 1
    assert profile["usable_event_count"] == 0
    assert profile["skipped_event_count"] == 1
    assert "PRIVATE_UNUSABLE_UID" not in json.dumps(profile)


def test_profiler_rejects_malformed_content_without_echoing_it():
    private_marker = "PRIVATE_MALFORMED_CONTENT"

    with pytest.raises(CalendarParseError) as error:
        profiler().profile(private_marker.encode())

    assert str(error.value) == "Canvas calendar feed is malformed"
    assert private_marker not in str(error.value)
