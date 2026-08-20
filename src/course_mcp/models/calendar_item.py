from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal


CalendarValue = date | datetime
CalendarSource = Literal["canvas_ical", "local_ical_snapshot"]
CalendarItemKind = Literal["assignment", "event", "unknown"]
MAX_UID_LENGTH = 512
MAX_TITLE_LENGTH = 500
MAX_DESCRIPTION_LENGTH = 1_000
MAX_LOCATION_LENGTH = 500
MAX_ITEM_URL_LENGTH = 2_048
MAX_COURSE_HINT_LENGTH = 200


@dataclass(frozen=True)
class CalendarItem:
    """A normalized event read from an iCalendar feed."""

    uid: str
    title: str
    starts_at: CalendarValue
    ends_at: CalendarValue | None = None
    all_day: bool = False
    description: str | None = None
    location: str | None = None
    item_url: str | None = None
    course_hint: str | None = None
    item_kind: CalendarItemKind = "unknown"
    sequence: int = 0
    last_modified: datetime | None = None
    dtstamp: datetime | None = None
    recurrence_id: str | None = None


@dataclass(frozen=True)
class CalendarParseResult:
    """Normalized events and safe diagnostics from one parse operation."""

    items: tuple[CalendarItem, ...]
    total_event_count: int
    skipped_event_count: int


@dataclass(frozen=True)
class CalendarSnapshot:
    """A parsed calendar and metadata describing its freshness."""

    items: tuple[CalendarItem, ...]
    source: CalendarSource
    fetched_at: datetime
    stale: bool = False
    skipped_event_count: int = 0
