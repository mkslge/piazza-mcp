import mcp.types as types

from course_mcp.mcp_schemas import (
    SEARCH_COURSE_FILE_OUTPUT_SCHEMA,
    SEARCH_COURSE_OUTPUT_SCHEMA,
)


def build_course_tools() -> list[types.Tool]:
    """Build the MCP tool definitions for course operations."""
    return [
        types.Tool(
            name="list-courses",
            description=(
                "List the courses the user is currently taking. "
                "Agents should use this MCP tool whenever they need to check "
                "which courses are available."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="list-course-files",
            description=(
                "List the files in a course. Agents should call list-courses "
                "first, then pass one of the returned course titles as "
                "course_title."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "course_title": {
                        "type": "string",
                        "description": (
                            "The course directory title returned by list-courses."
                        ),
                    },
                },
                "required": ["course_title"],
            },
        ),
        types.Tool(
            name="search-course-file",
            description=(
                "Search for a literal keyword in one UTF-8 text or PDF file "
                "inside a course. Matching is case-insensitive."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "course_title": {
                        "type": "string",
                        "description": (
                            "The course directory title returned by list-courses."
                        ),
                    },
                    "file_path": {
                        "type": "string",
                        "description": "The path relative to the course directory.",
                    },
                    "keyword": {
                        "type": "string",
                        "minLength": 1,
                        "description": "The literal text to search for.",
                    },
                    "context_lines": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 20,
                        "default": 3,
                        "description": (
                            "Lines of context before and after each match."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 20,
                        "description": "Maximum matching lines to return.",
                    },
                },
                "required": ["course_title", "file_path", "keyword"],
            },
            outputSchema=SEARCH_COURSE_FILE_OUTPUT_SCHEMA,
        ),
        types.Tool(
            name="search-course",
            description=(
                "Search recursively for a literal keyword in eligible UTF-8 "
                "text and PDF files within one course."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "course_title": {
                        "type": "string",
                        "description": (
                            "The course directory title returned by list-courses."
                        ),
                    },
                    "keyword": {
                        "type": "string",
                        "minLength": 1,
                        "description": "The literal text to search for.",
                    },
                    "context_lines": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 20,
                        "default": 3,
                        "description": (
                            "Lines of context before and after each match."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 20,
                        "description": (
                            "Maximum matching lines returned from each file."
                        ),
                    },
                },
                "required": ["course_title", "keyword"],
            },
            outputSchema=SEARCH_COURSE_OUTPUT_SCHEMA,
        ),
    ]
