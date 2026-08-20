import html
from hashlib import sha256
from datetime import date, datetime
from html.parser import HTMLParser
import re
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

from icalendar import Calendar

from course_mcp.config import CANVAS_CALENDAR_HOST
from course_mcp.models.calendar_item import (
    CalendarItem,
    CalendarParseResult,
    CalendarValue,
    MAX_DESCRIPTION_LENGTH,
    MAX_ITEM_URL_LENGTH,
    MAX_LOCATION_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_UID_LENGTH,
)


class CalendarParseError(ValueError):
    """Raised when calendar bytes cannot be parsed safely."""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class ICalendarParser:
    def __init__(self, calendar_timezone: ZoneInfo):
        """Create a parser that resolves floating times in one timezone."""
        self.calendar_timezone = calendar_timezone

    def parse(
        self,
        content: bytes,
        *,
        allow_no_usable_events: bool = False,
    ) -> CalendarParseResult:
        """Parse events, optionally retaining all-invalid feed diagnostics."""
        try:
            calendar = Calendar.from_ical(content)
        except (TypeError, ValueError):
            raise CalendarParseError("Canvas calendar feed is malformed") from None

        components = calendar.walk("VEVENT")
        items: list[CalendarItem] = []
        for component in components:
            item = self._parse_event(component)
            if item is not None:
                items.append(item)

        if components and not items and not allow_no_usable_events:
            raise CalendarParseError(
                "Canvas calendar feed contains no usable events"
            )
        return CalendarParseResult(
            items=tuple(items),
            total_event_count=len(components),
            skipped_event_count=len(components) - len(items),
        )

    def _parse_event(self, component) -> CalendarItem | None:
        uid = self._uid(component.get("UID"))
        title = self._bounded_text(component.get("SUMMARY"), MAX_TITLE_LENGTH)
        starts_at = self._calendar_value(component, "DTSTART")
        if not uid or not title or starts_at is None:
            return None

        ends_at = self._calendar_value(component, "DTEND")
        last_modified_value = self._calendar_value(component, "LAST-MODIFIED")
        last_modified = (
            last_modified_value
            if isinstance(last_modified_value, datetime)
            else None
        )
        dtstamp_value = self._calendar_value(component, "DTSTAMP")
        dtstamp = dtstamp_value if isinstance(dtstamp_value, datetime) else None
        recurrence_value = self._calendar_value(component, "RECURRENCE-ID")

        return CalendarItem(
            uid=uid,
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            all_day=not isinstance(starts_at, datetime),
            description=self._description(component.get("DESCRIPTION")),
            location=self._bounded_text(
                component.get("LOCATION"),
                MAX_LOCATION_LENGTH,
            ),
            item_url=self._safe_item_url(component.get("URL")),
            course_hint=None,
            item_kind="unknown",
            sequence=self._sequence(component),
            last_modified=last_modified,
            dtstamp=dtstamp,
            recurrence_id=(
                recurrence_value.isoformat()
                if recurrence_value is not None
                else None
            ),
        )

    @staticmethod
    def _sequence(component) -> int:
        value = component.get("SEQUENCE")
        if value is None:
            return 0
        try:
            sequence = int(value)
        except (TypeError, ValueError):
            return 0
        return max(sequence, 0)

    def _calendar_value(self, component, key: str) -> CalendarValue | None:
        if component.get(key) is None:
            return None
        try:
            value = component.decoded(key)
        except (KeyError, TypeError, ValueError):
            return None

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=self.calendar_timezone)
            return value
        if isinstance(value, date):
            return value
        return None

    @staticmethod
    def _text(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _bounded_text(value, max_length: int) -> str | None:
        text = ICalendarParser._text(value)
        if text is None:
            return None
        normalized = re.sub(r"\s+", " ", text).strip()
        return normalized[:max_length] or None

    @staticmethod
    def _uid(value) -> str | None:
        uid = ICalendarParser._text(value)
        if uid is None or len(uid) <= MAX_UID_LENGTH:
            return uid
        digest = sha256(uid.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @staticmethod
    def _description(value) -> str | None:
        text = ICalendarParser._text(value)
        if text is None:
            return None

        if re.search(r"<[^>]+>", text):
            extractor = _TextExtractor()
            try:
                extractor.feed(text)
                text = " ".join(extractor.parts)
            except ValueError:
                pass
        text = re.sub(r"\s+", " ", html.unescape(text)).strip()
        if not text:
            return None
        return text[:MAX_DESCRIPTION_LENGTH]

    @staticmethod
    def _safe_item_url(value) -> str | None:
        url = ICalendarParser._text(value)
        if url is None or len(url) > MAX_ITEM_URL_LENGTH:
            return None
        try:
            parsed = urlsplit(url)
        except ValueError:
            return None
        try:
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme != "https"
            or parsed.hostname != CANVAS_CALENDAR_HOST
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
            or unquote(parsed.path).casefold().startswith("/feeds/calendars/")
        ):
            return None
        return url
