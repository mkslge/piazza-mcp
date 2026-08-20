from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
import time as monotonic_time
from typing import Any, Callable
from zoneinfo import ZoneInfo

from course_mcp.models.calendar_item import (
    CalendarItem,
    CalendarSnapshot,
    CalendarValue,
)
from .feed_client import (
    CalendarFeedClient,
    CalendarFeedError,
)
from .parser import (
    CalendarParseError,
    ICalendarParser,
)


CACHE_SECONDS = 300
MAX_DATE_SPAN_DAYS = 366
LIMITATIONS = [
    "completion_status_unavailable",
    "canvas_todo_items_unavailable",
]


class CalendarService:
    def __init__(
        self,
        feed_client: CalendarFeedClient,
        parser: ICalendarParser,
        calendar_timezone: ZoneInfo,
        *,
        today_provider: Callable[[], date] | None = None,
        monotonic_provider: Callable[[], float] | None = None,
    ):
        """Create a calendar query service from injected source components."""
        self.feed_client = feed_client
        self.parser = parser
        self.calendar_timezone = calendar_timezone
        self.today_provider = today_provider or (
            lambda: datetime.now(self.calendar_timezone).date()
        )
        self.monotonic_provider = monotonic_provider or monotonic_time.monotonic
        self._cached_snapshot: CalendarSnapshot | None = None
        self._cache_loaded_at: float | None = None

    async def get_upcoming_work(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        query: str | None = None,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Return upcoming calendar items matching a bounded query."""
        start = self._parse_date(start_date, "start_date")
        if start is None:
            start = self.today_provider()
        end = self._parse_date(end_date, "end_date")
        if end is None:
            end = start + timedelta(days=6)
        if end < start:
            raise ValueError("end_date must be on or after start_date")
        if (end - start).days >= MAX_DATE_SPAN_DAYS:
            raise ValueError("Date range cannot exceed 366 calendar days")

        normalized_query = None
        if query is not None:
            if not isinstance(query, str):
                raise ValueError("query must be a string")
            normalized_query = query.strip().casefold()
            if not normalized_query:
                raise ValueError("query must not be empty")
        if isinstance(max_results, bool) or not isinstance(max_results, int):
            raise ValueError("max_results must be an integer")
        if not 1 <= max_results <= 100:
            raise ValueError("max_results must be between 1 and 100")

        snapshot = await self._get_snapshot()
        items = self._deduplicate(snapshot.items)
        items = [
            item
            for item in items
            if self._overlaps_date_range(item, start, end)
            and self._matches_query(item, normalized_query)
        ]
        items.sort(key=self._sort_key)

        truncated = len(items) > max_results
        returned_items = items[:max_results]
        return {
            "source": snapshot.source,
            "fetched_at": self._datetime_text(snapshot.fetched_at),
            "stale": snapshot.stale,
            "skipped_event_count": snapshot.skipped_event_count,
            "returned_count": len(returned_items),
            "truncated": truncated,
            "limitations": list(LIMITATIONS),
            "items": [self._serialize_item(item) for item in returned_items],
        }

    async def _get_snapshot(self) -> CalendarSnapshot:
        now = self.monotonic_provider()
        if (
            self._cached_snapshot is not None
            and self._cache_loaded_at is not None
            and now - self._cache_loaded_at < CACHE_SECONDS
        ):
            return self._cached_snapshot

        try:
            payload = await self.feed_client.fetch()
            if payload.not_modified:
                if self._cached_snapshot is None:
                    raise CalendarFeedError(
                        "Canvas calendar feed returned no content"
                    )
                snapshot = replace(
                    self._cached_snapshot,
                    fetched_at=payload.fetched_at,
                    stale=False,
                )
            else:
                if payload.content is None:
                    raise CalendarFeedError(
                        "Canvas calendar feed returned no content"
                    )
                parse_result = self.parser.parse(payload.content)
                snapshot = CalendarSnapshot(
                    items=parse_result.items,
                    source=payload.source,
                    fetched_at=payload.fetched_at,
                    skipped_event_count=parse_result.skipped_event_count,
                )
        except (CalendarFeedError, CalendarParseError):
            if self._cached_snapshot is None:
                raise
            snapshot = replace(self._cached_snapshot, stale=True)

        self._cached_snapshot = snapshot
        self._cache_loaded_at = now
        return snapshot

    @staticmethod
    def _parse_date(value: str | None, field_name: str) -> date | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must use YYYY-MM-DD")
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"{field_name} must use YYYY-MM-DD") from None
        if parsed.isoformat() != value:
            raise ValueError(f"{field_name} must use YYYY-MM-DD")
        return parsed

    def _overlaps_date_range(
        self,
        item: CalendarItem,
        start: date,
        end: date,
    ) -> bool:
        range_start = datetime.combine(start, time.min, self.calendar_timezone)
        range_end = datetime.combine(
            end + timedelta(days=1),
            time.min,
            self.calendar_timezone,
        )
        item_start = self._as_datetime(item.starts_at)

        if item.ends_at is not None:
            item_end = self._as_datetime(item.ends_at)
        elif item.all_day:
            item_end = item_start + timedelta(days=1)
        else:
            item_end = item_start

        if item_end <= item_start:
            return range_start <= item_start < range_end
        return item_start < range_end and item_end > range_start

    def _as_datetime(self, value: CalendarValue) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=self.calendar_timezone)
            return value.astimezone(self.calendar_timezone)
        return datetime.combine(value, time.min, self.calendar_timezone)

    @staticmethod
    def _matches_query(item: CalendarItem, query: str | None) -> bool:
        if query is None:
            return True
        values = (
            item.title,
            item.description,
            item.location,
            item.course_hint,
        )
        return any(query in value.casefold() for value in values if value)

    def _deduplicate(self, items: tuple[CalendarItem, ...]) -> list[CalendarItem]:
        unique: dict[tuple[str, str | None], CalendarItem] = {}
        for item in items:
            key = (item.uid, item.recurrence_id)
            existing = unique.get(key)
            if existing is None or self._revision_key(item) >= self._revision_key(
                existing
            ):
                unique[key] = item
        return list(unique.values())

    def _revision_key(self, item: CalendarItem) -> tuple[int, datetime, datetime]:
        return (
            item.sequence,
            self._revision_timestamp(item.last_modified),
            self._revision_timestamp(item.dtstamp),
        )

    def _revision_timestamp(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=self.calendar_timezone)
        return value.astimezone(timezone.utc)

    def _sort_key(self, item: CalendarItem) -> tuple[datetime, str, str]:
        return (
            self._as_datetime(item.starts_at),
            item.title.casefold(),
            item.uid,
        )

    @staticmethod
    def _serialize_item(item: CalendarItem) -> dict[str, Any]:
        return {
            "uid": item.uid,
            "title": item.title,
            "starts_at": item.starts_at.isoformat(),
            "ends_at": (
                item.ends_at.isoformat() if item.ends_at is not None else None
            ),
            "all_day": item.all_day,
            "description": item.description,
            "location": item.location,
            "item_url": item.item_url,
            "course_hint": item.course_hint,
            "item_kind": item.item_kind,
        }

    @staticmethod
    def _datetime_text(value: datetime) -> str:
        normalized = value.astimezone(timezone.utc).isoformat()
        return normalized.replace("+00:00", "Z")
