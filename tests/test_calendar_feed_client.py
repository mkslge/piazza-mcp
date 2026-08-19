import asyncio
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from course_mcp.config import CalendarConfig
from course_mcp.services.calendar_feed_client import (
    CalendarFeedClient,
    CalendarFeedError,
)


TEST_URL = (
    "https://umd.instructure.com/feeds/calendars/user_test_secret.ics"
)
CALENDAR_BYTES = b"BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"


def live_config() -> CalendarConfig:
    return CalendarConfig(
        url=TEST_URL,
        path=None,
        timezone=ZoneInfo("America/New_York"),
    )


def test_client_fetches_live_calendar_without_authentication_headers():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") is None
        assert request.headers.get("Cookie") is None
        return httpx.Response(
            200,
            headers={"Content-Type": "text/calendar"},
            content=CALENDAR_BYTES,
        )

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(client.fetch())

    assert result.content == CALENDAR_BYTES
    assert result.source == "canvas_ical"
    assert result.not_modified is False


def test_client_uses_conditional_request_headers():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "text/calendar",
                    "ETag": '"calendar-version"',
                    "Last-Modified": "Wed, 19 Aug 2026 12:00:00 GMT",
                },
                content=CALENDAR_BYTES,
            )
        assert request.headers["If-None-Match"] == '"calendar-version"'
        assert request.headers["If-Modified-Since"] == (
            "Wed, 19 Aug 2026 12:00:00 GMT"
        )
        return httpx.Response(304)

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(client.fetch())
    result = asyncio.run(client.fetch())

    assert result.not_modified is True
    assert result.content is None


def test_client_rejects_cross_host_redirect_without_leaking_url():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://example.com/feed"})

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CalendarFeedError) as error:
        asyncio.run(client.fetch())

    assert "cross-host redirect" in str(error.value)
    assert "user_test_secret" not in str(error.value)


def test_client_rejects_oversized_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/calendar"},
            content=b"123456",
        )

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
        max_bytes=5,
    )

    with pytest.raises(CalendarFeedError, match="exceeds 5 MB"):
        asyncio.run(client.fetch())


def test_client_redacts_transport_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("failure", request=request)

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CalendarFeedError) as error:
        asyncio.run(client.fetch())

    assert str(error.value) == "Canvas calendar feed request timed out"
    assert "user_test_secret" not in str(error.value)


def test_client_reads_local_snapshot(tmp_path: Path):
    snapshot_path = tmp_path / "calendar.ics"
    snapshot_path.write_bytes(CALENDAR_BYTES)
    config = CalendarConfig(
        url=None,
        path=snapshot_path,
        timezone=ZoneInfo("America/New_York"),
    )
    client = CalendarFeedClient(config)

    result = asyncio.run(client.fetch())

    assert result.content == CALENDAR_BYTES
    assert result.source == "local_ical_snapshot"
