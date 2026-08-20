from datetime import date, datetime
from urllib.parse import unquote, urlsplit

from icalendar import Calendar

from course_mcp.config import CANVAS_CALENDAR_HOST

from .parser import CalendarParseError, ICalendarParser


_PROFILED_FIELDS = (
    ("categories", "CATEGORIES"),
    ("location", "LOCATION"),
    ("url", "URL"),
    ("rrule", "RRULE"),
    ("rdate", "RDATE"),
    ("exdate", "EXDATE"),
    ("recurrence_id", "RECURRENCE-ID"),
    ("status", "STATUS"),
)


class CalendarFeedProfiler:
    """Summarize calendar structure without returning event values."""

    def __init__(self, parser: ICalendarParser):
        self.parser = parser

    def profile(self, content: bytes) -> dict[str, object]:
        """Return aggregate event and field-shape counts for calendar bytes."""
        try:
            calendar = Calendar.from_ical(content)
        except (TypeError, ValueError):
            raise CalendarParseError("Canvas calendar feed is malformed") from None

        components = calendar.walk("VEVENT")
        parsed = self.parser.parse(content, allow_no_usable_events=True)

        field_presence = {
            output_name: sum(
                component.get(calendar_name) is not None
                for component in components
            )
            for output_name, calendar_name in _PROFILED_FIELDS
        }
        start_shapes = {
            "date": 0,
            "floating_datetime": 0,
            "timezone_aware_datetime": 0,
            "missing_or_invalid": 0,
        }
        url_shapes = {
            "canvas_assignment": 0,
            "canvas_other": 0,
            "external_or_invalid": 0,
            "missing": 0,
        }

        for component in components:
            start_shapes[self._start_shape(component)] += 1
            url_shapes[self._url_shape(component.get("URL"))] += 1

        return {
            "total_event_count": parsed.total_event_count,
            "usable_event_count": len(parsed.items),
            "skipped_event_count": parsed.skipped_event_count,
            "normalized_event_shapes": {
                "all_day": sum(item.all_day for item in parsed.items),
                "timed": sum(not item.all_day for item in parsed.items),
            },
            "start_shapes": start_shapes,
            "field_presence": field_presence,
            "url_shapes": url_shapes,
        }

    @staticmethod
    def _start_shape(component) -> str:
        if component.get("DTSTART") is None:
            return "missing_or_invalid"
        try:
            value = component.decoded("DTSTART")
        except (KeyError, TypeError, ValueError):
            return "missing_or_invalid"

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return "floating_datetime"
            return "timezone_aware_datetime"
        if isinstance(value, date):
            return "date"
        return "missing_or_invalid"

    @staticmethod
    def _url_shape(value) -> str:
        if value is None or not str(value).strip():
            return "missing"

        try:
            parsed = urlsplit(str(value).strip())
            port = parsed.port
        except ValueError:
            return "external_or_invalid"

        if (
            parsed.scheme != "https"
            or parsed.hostname != CANVAS_CALENDAR_HOST
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
        ):
            return "external_or_invalid"

        path_segments = {
            unquote(segment).casefold()
            for segment in parsed.path.split("/")
            if segment
        }
        if "assignments" in path_segments:
            return "canvas_assignment"
        return "canvas_other"
