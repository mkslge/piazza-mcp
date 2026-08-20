from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx

from course_mcp.config import (
    CANVAS_CALENDAR_HOST,
    MAX_CALENDAR_BYTES,
    CalendarConfig,
)


FeedSource = Literal["canvas_ical", "local_ical_snapshot"]
ACCEPTED_CONTENT_TYPES = {
    "application/octet-stream",
    "text/calendar",
    "text/plain",
}


class CalendarFeedError(RuntimeError):
    """Raised when a calendar source cannot be loaded safely."""


@dataclass(frozen=True)
class CalendarFeedPayload:
    """Raw feed bytes and transport metadata for one load."""

    content: bytes | None
    source: FeedSource
    fetched_at: datetime
    not_modified: bool = False


class CalendarFeedClient:
    def __init__(
        self,
        config: CalendarConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_bytes: int = MAX_CALENDAR_BYTES,
    ):
        """Create a bounded loader for the configured calendar source."""
        self.config = config
        self.transport = transport
        self.max_bytes = max_bytes
        self._etag: str | None = None
        self._last_modified: str | None = None

    async def fetch(self) -> CalendarFeedPayload:
        """Load a live feed or local snapshot without exposing its location."""
        if self.config.path is not None:
            return self._read_snapshot(self.config.path)
        if self.config.url is None:
            raise CalendarFeedError("Canvas calendar source is not configured")
        return await self._fetch_url(self.config.url)

    def _read_snapshot(self, path: Path) -> CalendarFeedPayload:
        try:
            if path.stat().st_size > self.max_bytes:
                raise CalendarFeedError("Canvas calendar feed exceeds 5 MB")
            content = path.read_bytes()
            if len(content) > self.max_bytes:
                raise CalendarFeedError("Canvas calendar feed exceeds 5 MB")
        except CalendarFeedError:
            raise
        except OSError:
            raise CalendarFeedError(
                "Unable to read the configured Canvas calendar snapshot"
            ) from None

        return CalendarFeedPayload(
            content=content,
            source="local_ical_snapshot",
            fetched_at=datetime.now(timezone.utc),
        )

    async def _fetch_url(self, url: str) -> CalendarFeedPayload:
        headers = {"Accept": "text/calendar, text/plain;q=0.9"}
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self._last_modified:
            headers["If-Modified-Since"] = self._last_modified

        timeout = httpx.Timeout(10.0, connect=5.0)
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=timeout,
                follow_redirects=False,
            ) as client:
                current_url = url
                for _ in range(4):
                    async with client.stream(
                        "GET",
                        current_url,
                        headers=headers,
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("Location")
                            if not location:
                                raise CalendarFeedError(
                                    "Canvas calendar feed returned an invalid redirect"
                                )
                            next_url = urljoin(current_url, location)
                            self._validate_redirect(next_url)
                            current_url = next_url
                            continue

                        fetched_at = datetime.now(timezone.utc)
                        if response.status_code == 304:
                            return CalendarFeedPayload(
                                content=None,
                                source="canvas_ical",
                                fetched_at=fetched_at,
                                not_modified=True,
                            )
                        if not 200 <= response.status_code < 300:
                            raise CalendarFeedError(
                                "Canvas calendar feed returned HTTP "
                                f"{response.status_code}"
                            )

                        self._validate_content_type(response)
                        content = await self._read_bounded(response)
                        self._etag = response.headers.get("ETag")
                        self._last_modified = response.headers.get("Last-Modified")
                        return CalendarFeedPayload(
                            content=content,
                            source="canvas_ical",
                            fetched_at=fetched_at,
                        )
                raise CalendarFeedError(
                    "Canvas calendar feed redirected too many times"
                )
        except CalendarFeedError:
            raise
        except httpx.TimeoutException:
            raise CalendarFeedError("Canvas calendar feed request timed out") from None
        except httpx.HTTPError:
            raise CalendarFeedError("Unable to load Canvas calendar feed") from None

    @staticmethod
    def _validate_redirect(url: str) -> None:
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise CalendarFeedError(
                "Canvas calendar feed returned an invalid redirect"
            ) from None
        try:
            port = parsed.port
        except ValueError:
            port = -1
        if (
            parsed.scheme != "https"
            or parsed.hostname != CANVAS_CALENDAR_HOST
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
        ):
            raise CalendarFeedError(
                "Canvas calendar feed attempted a cross-host redirect"
            )

    def _validate_content_type(self, response: httpx.Response) -> None:
        content_type = response.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type and media_type not in ACCEPTED_CONTENT_TYPES:
            raise CalendarFeedError(
                "Canvas calendar feed returned an unsupported content type"
            )

        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    raise CalendarFeedError("Canvas calendar feed exceeds 5 MB")
            except ValueError:
                pass

    async def _read_bounded(self, response: httpx.Response) -> bytes:
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > self.max_bytes:
                raise CalendarFeedError("Canvas calendar feed exceeds 5 MB")
        return bytes(content)
