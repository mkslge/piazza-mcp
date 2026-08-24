"""Print privacy-safe aggregate diagnostics for configured Piazza data."""

import asyncio
import json
import sys

from piazza_mcp.config import get_piazza_config
from piazza_mcp.services.piazza import (
    PiazzaClient,
    PiazzaClientError,
    PiazzaShapeProfiler,
)


async def inspect_piazza() -> dict[str, object]:
    """Load a small sample without printing course or post values."""
    config = get_piazza_config()
    course_id = next(iter(config.courses))
    client = PiazzaClient(config)
    summaries = await client.list_posts(course_id, limit=5, offset=0)

    thread = None
    if summaries:
        post_number = summaries[0].get("nr", summaries[0].get("id"))
        if type(post_number) in {int, str}:
            try:
                normalized_number = int(post_number)
            except ValueError:
                normalized_number = 0
            if normalized_number > 0:
                thread = await client.get_post(course_id, normalized_number)

    return {
        "source": "piazza_unofficial_internal_api",
        **PiazzaShapeProfiler().profile(summaries, thread),
    }


def main() -> int:
    try:
        profile = asyncio.run(inspect_piazza())
    except (RuntimeError, PiazzaClientError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1

    print(json.dumps(profile, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
