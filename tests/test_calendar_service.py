import asyncio
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from course_mcp.models.calendar_item import CalendarItem, CalendarParseResult
from course_mcp.services.calendar import (
    CalendarFeedError,
    CalendarFeedPayload,
    CalendarParseError,
    CalendarService,
)


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
    def __init__(self, items, skipped_event_count=0):
        self.items = tuple(items)
        self.skipped_event_count = skipped_event_count

    def parse(self, content):
        assert content == b"calendar"
        return CalendarParseResult(
            items=self.items,
            total_event_count=len(self.items) + self.skipped_event_count,
            skipped_event_count=self.skipped_event_count,
        )


class SequencedParser:
    def __init__(self, results):
        self.results = list(results)

    def parse(self, content):
        assert content == b"calendar"
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def item(
    uid,
    title,
    starts_at,
    *,
    ends_at=None,
    all_day=False,
    description=None,
    sequence=0,
    last_modified=None,
    dtstamp=None,
    recurrence_id=None,
):
    return CalendarItem(
        uid=uid,
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
        all_day=all_day,
        description=description,
        sequence=sequence,
        last_modified=last_modified,
        dtstamp=dtstamp,
        recurrence_id=recurrence_id,
    )


def payload(*, not_modified=False):
    return CalendarFeedPayload(
        content=None if not_modified else b"calendar",
        source="canvas_ical",
        fetched_at=FETCHED_AT,
        not_modified=not_modified,
    )


def make_service(
    items,
    results=None,
    *,
    skipped_event_count=0,
    parser=None,
    monotonic_provider=None,
):
    client = FakeFeedClient(results or [payload()])
    service = CalendarService(
        client,
        parser or FakeParser(items, skipped_event_count),
        EASTERN,
        today_provider=lambda: date(2026, 8, 19),
        monotonic_provider=monotonic_provider,
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
    assert result["skipped_event_count"] == 0


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


def test_service_prefers_higher_sequence_regardless_of_feed_order():
    service, _ = make_service(
        [
            item(
                "duplicate",
                "Current deadline",
                datetime(2026, 8, 20, 12, 0, tzinfo=EASTERN),
                sequence=2,
            ),
            item(
                "duplicate",
                "Old deadline",
                datetime(2026, 8, 20, 10, 0, tzinfo=EASTERN),
                sequence=1,
            ),
        ]
    )

    result = asyncio.run(service.get_upcoming_work())

    assert result["items"][0]["title"] == "Current deadline"


def test_service_uses_revision_timestamps_after_sequence():
    newer = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    older = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    service, _ = make_service(
        [
            item(
                "last-modified",
                "New last modified",
                datetime(2026, 8, 20, 12, 0, tzinfo=EASTERN),
                last_modified=newer,
                dtstamp=older,
            ),
            item(
                "last-modified",
                "Old last modified",
                datetime(2026, 8, 20, 10, 0, tzinfo=EASTERN),
                last_modified=older,
                dtstamp=newer,
            ),
            item(
                "dtstamp",
                "New stamp",
                datetime(2026, 8, 21, 12, 0, tzinfo=EASTERN),
                dtstamp=newer,
            ),
            item(
                "dtstamp",
                "Old stamp",
                datetime(2026, 8, 21, 10, 0, tzinfo=EASTERN),
                dtstamp=older,
            ),
        ]
    )

    result = asyncio.run(service.get_upcoming_work())

    assert [entry["title"] for entry in result["items"]] == [
        "New last modified",
        "New stamp",
    ]


def test_service_uses_feed_order_only_for_exact_revision_ties():
    service, _ = make_service(
        [
            item(
                "same",
                "First",
                datetime(2026, 8, 20, 10, 0, tzinfo=EASTERN),
            ),
            item(
                "same",
                "Second",
                datetime(2026, 8, 20, 11, 0, tzinfo=EASTERN),
            ),
            item(
                "same",
                "Other recurrence",
                datetime(2026, 8, 21, 11, 0, tzinfo=EASTERN),
                recurrence_id="2026-08-21T11:00:00-04:00",
            ),
        ]
    )

    result = asyncio.run(service.get_upcoming_work())

    assert [entry["title"] for entry in result["items"]] == [
        "Second",
        "Other recurrence",
    ]


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


def test_service_uses_cache_without_refetching_inside_ttl():
    service, client = make_service(
        [item("one", "One", datetime(2026, 8, 20, tzinfo=EASTERN))]
    )

    first = asyncio.run(service.get_upcoming_work())
    second = asyncio.run(service.get_upcoming_work())

    assert client.call_count == 1
    assert second == first


def test_service_refreshes_after_ttl_and_handles_not_modified():
    clock = FakeClock()
    service, client = make_service(
        [item("one", "One", datetime(2026, 8, 20, tzinfo=EASTERN))],
        [payload(), payload(not_modified=True)],
        skipped_event_count=2,
        monotonic_provider=clock,
    )

    asyncio.run(service.get_upcoming_work())
    clock.advance(301)
    result = asyncio.run(service.get_upcoming_work())

    assert client.call_count == 2
    assert result["items"][0]["uid"] == "one"
    assert result["stale"] is False
    assert result["skipped_event_count"] == 2


def test_service_returns_marked_stale_cache_after_refresh_failure():
    clock = FakeClock()
    service, _ = make_service(
        [item("one", "One", datetime(2026, 8, 20, tzinfo=EASTERN))],
        [payload(), CalendarFeedError("temporary failure")],
        skipped_event_count=1,
        monotonic_provider=clock,
    )

    asyncio.run(service.get_upcoming_work())
    clock.advance(301)
    result = asyncio.run(service.get_upcoming_work())

    assert result["stale"] is True
    assert result["items"][0]["uid"] == "one"
    assert result["skipped_event_count"] == 1


def test_service_rejects_first_load_not_modified_response():
    service, _ = make_service([], [payload(not_modified=True)])

    with pytest.raises(CalendarFeedError, match="returned no content"):
        asyncio.run(service.get_upcoming_work())


def test_service_uses_stale_cache_after_parser_failure():
    clock = FakeClock()
    parsed = CalendarParseResult(
        items=(item("one", "One", datetime(2026, 8, 20, tzinfo=EASTERN)),),
        total_event_count=2,
        skipped_event_count=1,
    )
    parser = SequencedParser(
        [
            parsed,
            CalendarParseError("Canvas calendar feed contains no usable events"),
        ]
    )
    service, _ = make_service(
        [],
        [payload(), payload()],
        parser=parser,
        monotonic_provider=clock,
    )

    asyncio.run(service.get_upcoming_work())
    clock.advance(301)
    result = asyncio.run(service.get_upcoming_work())

    assert result["stale"] is True
    assert result["skipped_event_count"] == 1


def test_service_propagates_parser_failure_without_cache():
    parser = SequencedParser(
        [CalendarParseError("Canvas calendar feed contains no usable events")]
    )
    service, _ = make_service([], parser=parser)

    with pytest.raises(CalendarParseError, match="no usable events"):
        asyncio.run(service.get_upcoming_work())


def test_not_modified_response_clears_stale_marker():
    clock = FakeClock()
    service, _ = make_service(
        [item("one", "One", datetime(2026, 8, 20, tzinfo=EASTERN))],
        [
            payload(),
            CalendarFeedError("temporary failure"),
            payload(not_modified=True),
        ],
        monotonic_provider=clock,
    )

    asyncio.run(service.get_upcoming_work())
    clock.advance(301)
    stale = asyncio.run(service.get_upcoming_work())
    clock.advance(301)
    current = asyncio.run(service.get_upcoming_work())

    assert stale["stale"] is True
    assert current["stale"] is False
