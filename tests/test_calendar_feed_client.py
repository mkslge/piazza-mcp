import asyncio
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from course_mcp.config import CalendarConfig
from course_mcp.services.calendar import (
    CalendarFeedClient,
    CalendarFeedError,
)


TEST_URL = (
    "https://umd.instructure.com/feeds/calendars/user_test_secret.ics"
)
CALENDAR_BYTES = b"BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


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


def test_client_follows_same_host_redirect():
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(
                302,
                headers={"Location": "/feeds/calendars/redirected.ics"},
            )
        assert request.url.path == "/feeds/calendars/redirected.ics"
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

    assert request_count == 2
    assert result.content == CALENDAR_BYTES


def test_client_rejects_too_many_redirects():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "/feeds/calendars/again.ics"},
        )

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CalendarFeedError, match="redirected too many times"):
        asyncio.run(client.fetch())


@pytest.mark.parametrize(
    "location",
    [
        "https://user:password@umd.instructure.com/feed.ics",
        "https://umd.instructure.com:444/feed.ics",
        "https://umd.instructure.com:invalid/feed.ics",
    ],
)
def test_client_rejects_unsafe_same_host_redirects(location):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": location})

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CalendarFeedError) as error:
        asyncio.run(client.fetch())

    assert "user_test_secret" not in str(error.value)


def test_client_reports_http_error_without_leaking_url():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CalendarFeedError) as error:
        asyncio.run(client.fetch())

    assert str(error.value) == "Canvas calendar feed returned HTTP 503"
    assert "user_test_secret" not in str(error.value)


def test_client_rejects_unsupported_content_type():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"<html></html>",
        )

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CalendarFeedError, match="unsupported content type"):
        asyncio.run(client.fetch())


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


def test_client_rejects_oversized_content_length_before_reading():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/calendar",
                "Content-Length": "6",
            },
            stream=ChunkedStream([b"1"]),
        )

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
        max_bytes=5,
    )

    with pytest.raises(CalendarFeedError, match="exceeds 5 MB"):
        asyncio.run(client.fetch())


def test_client_ignores_invalid_content_length_for_bounded_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/calendar",
                "Content-Length": "invalid",
            },
            stream=ChunkedStream([b"12345"]),
        )

    client = CalendarFeedClient(
        live_config(),
        transport=httpx.MockTransport(handler),
        max_bytes=5,
    )

    result = asyncio.run(client.fetch())

    assert result.content == b"12345"


def test_client_rejects_oversized_stream_without_content_length():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/calendar"},
            stream=ChunkedStream([b"123", b"456"]),
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


def test_client_reports_local_snapshot_deleted_after_configuration(tmp_path: Path):
    snapshot_path = tmp_path / "calendar.ics"
    snapshot_path.write_bytes(CALENDAR_BYTES)
    client = CalendarFeedClient(
        CalendarConfig(
            url=None,
            path=snapshot_path,
            timezone=ZoneInfo("America/New_York"),
        )
    )
    snapshot_path.unlink()

    with pytest.raises(CalendarFeedError) as error:
        asyncio.run(client.fetch())

    assert str(snapshot_path) not in str(error.value)


def test_client_rejects_local_snapshot_that_grows_past_limit(tmp_path: Path):
    snapshot_path = tmp_path / "calendar.ics"
    snapshot_path.write_bytes(b"12345")
    client = CalendarFeedClient(
        CalendarConfig(
            url=None,
            path=snapshot_path,
            timezone=ZoneInfo("America/New_York"),
        ),
        max_bytes=5,
    )
    snapshot_path.write_bytes(b"123456")

    with pytest.raises(CalendarFeedError, match="exceeds 5 MB"):
        asyncio.run(client.fetch())
