from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal


CalendarValue = date | datetime
CalendarSource = Literal["canvas_ical", "local_ical_snapshot"]
CalendarItemKind = Literal["assignment", "event", "unknown"]


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
    last_modified: datetime | None = None
    recurrence_id: str | None = None


@dataclass(frozen=True)
class CalendarSnapshot:
    """A parsed calendar and metadata describing its freshness."""

    items: tuple[CalendarItem, ...]
    source: CalendarSource
    fetched_at: datetime
    stale: bool = False
