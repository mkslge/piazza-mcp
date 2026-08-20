from course_mcp.mcp_tools.calendar import build_calendar_tools
from course_mcp.mcp_tools.course import build_course_tools
from course_mcp.mcp_tools.piazza import build_piazza_tools


def build_tools():
    """Build the complete MCP tool catalog."""
    return [
        *build_course_tools(),
        *build_calendar_tools(),
        *build_piazza_tools(),
    ]


__all__ = [
    "build_calendar_tools",
    "build_course_tools",
    "build_piazza_tools",
    "build_tools",
]
