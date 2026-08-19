import mcp.types as types

from course_mcp.mcp_schemas import GET_UPCOMING_WORK_OUTPUT_SCHEMA


def build_calendar_tools() -> list[types.Tool]:
    """Build MCP definitions for read-only calendar operations."""
    return [
        types.Tool(
            name="get-upcoming-work",
            description=(
                "List assignments and events from the user's private Canvas "
                "calendar feed. This cannot determine submission status, "
                "grades, or Canvas To Do items."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "format": "date",
                        "description": (
                            "First included calendar date in YYYY-MM-DD format; "
                            "defaults to today."
                        ),
                    },
                    "end_date": {
                        "type": "string",
                        "format": "date",
                        "description": (
                            "Last included calendar date in YYYY-MM-DD format; "
                            "defaults to six days after start_date."
                        ),
                    },
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Optional case-insensitive literal text filter."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 50,
                        "description": "Maximum calendar items to return.",
                    },
                },
                "additionalProperties": False,
            },
            outputSchema=GET_UPCOMING_WORK_OUTPUT_SCHEMA,
        )
    ]
