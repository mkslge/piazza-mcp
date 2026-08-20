"""Print privacy-safe aggregate diagnostics for a configured Canvas feed."""

import asyncio
import json
import sys

from course_mcp.config import get_calendar_config
from course_mcp.services.calendar import (
    CalendarFeedClient,
    CalendarFeedError,
    CalendarFeedProfiler,
    CalendarParseError,
    ICalendarParser,
)


async def inspect_calendar() -> dict[str, object]:
    """Load and profile the configured feed without exposing event values."""
    config = get_calendar_config()
    payload = await CalendarFeedClient(config).fetch()
    if payload.content is None:
        raise CalendarFeedError("Canvas calendar feed returned no content")

    profiler = CalendarFeedProfiler(ICalendarParser(config.timezone))
    return {"source": payload.source, **profiler.profile(payload.content)}


def main() -> int:
    try:
        profile = asyncio.run(inspect_calendar())
    except (RuntimeError, CalendarFeedError, CalendarParseError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1

    print(json.dumps(profile, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
