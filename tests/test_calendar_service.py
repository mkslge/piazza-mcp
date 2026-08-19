import asyncio
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from course_mcp.models.calendar_item import CalendarItem
from course_mcp.services import calendar_service as calendar_service_module
from course_mcp.services.calendar_feed_client import (
    CalendarFeedError,
    CalendarFeedPayload,
)
from course_mcp.services.calendar_service import CalendarService


EASTERN = ZoneInfo("America/New_York")
FETCHED_AT = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


class FakeFeedClient:
    def __init__(self, results):
        self.results = list(results)
        self.call_count = 0

    async def fetch(self):
        self.call_count += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeParser:
    def __init__(self, items):
        self.items = tuple(items)

    def parse(self, content):
        assert content == b"calendar"
        return self.items


def item(
    uid,
    title,
    starts_at,
    *,
    ends_at=None,
    all_day=False,
    description=None,
):
    return CalendarItem(
        uid=uid,
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
        all_day=all_day,
        description=description,
    )


def payload(*, not_modified=False):
    return CalendarFeedPayload(
        content=None if not_modified else b"calendar",
        source="canvas_ical",
        fetched_at=FETCHED_AT,
        not_modified=not_modified,
    )


def make_service(items, results=None):
    client = FakeFeedClient(results or [payload()])
    service = CalendarService(
        client,
        FakeParser(items),
        EASTERN,
        today_provider=lambda: date(2026, 8, 19),
    )
    return service, client


def test_service_defaults_to_seven_dates_and_sorts_items():
    service, _ = make_service(
        [
            item("later", "Beta", datetime(2026, 8, 25, 23, 59, tzinfo=EASTERN)),
            item("earlier", "Alpha", datetime(2026, 8, 19, 0, 0, tzinfo=EASTERN)),
            item("outside", "Later", datetime(2026, 8, 26, 0, 0, tzinfo=EASTERN)),
        ]
    )

    result = asyncio.run(service.get_upcoming_work())

    assert [entry["uid"] for entry in result["items"]] == ["earlier", "later"]
    assert result["returned_count"] == 2
    assert result["fetched_at"] == "2026-08-19T12:00:00Z"
    assert result["stale"] is False


def test_service_includes_overlapping_timed_and_all_day_events():
    service, _ = make_service(
        [
            item(
                "timed",
                "Overnight",
                datetime(2026, 8, 18, 23, 0, tzinfo=EASTERN),
                ends_at=datetime(2026, 8, 19, 1, 0, tzinfo=EASTERN),
            ),
            item(
                "all-day",
                "Study",
                date(2026, 8, 19),
                ends_at=date(2026, 8, 20),
                all_day=True,
            ),
        ]
    )

    result = asyncio.run(
        service.get_upcoming_work(
            start_date="2026-08-19",
            end_date="2026-08-19",
        )
    )

    assert [entry["uid"] for entry in result["items"]] == ["timed", "all-day"]
    assert result["items"][1]["starts_at"] == "2026-08-19"


def test_service_filters_query_deduplicates_and_truncates():
    service, _ = make_service(
        [
            item(
                "duplicate",
                "Old project title",
                datetime(2026, 8, 20, 10, 0, tzinfo=EASTERN),
            ),
            item(
                "duplicate",
                "Project Alpha",
                datetime(2026, 8, 20, 11, 0, tzinfo=EASTERN),
            ),
            item(
                "second",
                "Reading",
                datetime(2026, 8, 21, 10, 0, tzinfo=EASTERN),
                description="PROJECT notes",
            ),
        ]
    )

    result = asyncio.run(
        service.get_upcoming_work(query="project", max_results=1)
    )

    assert result["returned_count"] == 1
    assert result["truncated"] is True
    assert result["items"][0]["title"] == "Project Alpha"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"start_date": "08/19/2026"}, "start_date must use YYYY-MM-DD"),
        (
            {"start_date": "2026-08-20", "end_date": "2026-08-19"},
            "end_date must be on or after start_date",
        ),
        (
            {"start_date": "2026-01-01", "end_date": "2027-01-02"},
            "Date range cannot exceed 366 calendar days",
        ),
        ({"query": "  "}, "query must not be empty"),
        ({"query": 123}, "query must be a string"),
        ({"max_results": 0}, "max_results must be between 1 and 100"),
    ],
)
def test_service_validates_arguments(arguments, message):
    service, _ = make_service([])

    with pytest.raises(ValueError, match=message):
        asyncio.run(service.get_upcoming_work(**arguments))


def test_service_uses_cache_and_handles_not_modified_response(monkeypatch):
    service, client = make_service(
        [item("one", "One", datetime(2026, 8, 20, tzinfo=EASTERN))],
        [payload(), payload(not_modified=True)],
    )
    monkeypatch.setattr(calendar_service_module, "CACHE_SECONDS", 0)

    asyncio.run(service.get_upcoming_work())
    result = asyncio.run(service.get_upcoming_work())

    assert client.call_count == 2
    assert result["items"][0]["uid"] == "one"
    assert result["stale"] is False


def test_service_returns_marked_stale_cache_after_refresh_failure(monkeypatch):
    service, _ = make_service(
        [item("one", "One", datetime(2026, 8, 20, tzinfo=EASTERN))],
        [payload(), CalendarFeedError("temporary failure")],
    )
    monkeypatch.setattr(calendar_service_module, "CACHE_SECONDS", 0)

    asyncio.run(service.get_upcoming_work())
    result = asyncio.run(service.get_upcoming_work())

    assert result["stale"] is True
    assert result["items"][0]["uid"] == "one"
