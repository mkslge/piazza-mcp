import asyncio
from typing import Any

from course_mcp.mcp_tools import build_tools
from course_mcp.services.calendar import get_calendar_service
from course_mcp.services.course import get_course_service
from course_mcp.services.piazza import get_piazza_service
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

notes: dict[str, str] = {}

server = Server("course-mcp")


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """Expose the currently stored internal notes as MCP resources."""
    return [
        types.Resource(
            uri=AnyUrl(f"note://internal/{name}"),
            name=f"Note: {name}",
            description=f"A simple note named {name}",
            mimeType="text/plain",
        )
        for name in notes
    ]


@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """Return the text for a note resource identified by its MCP URI."""
    if uri.scheme != "note":
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    name = uri.path
    if name is not None:
        name = name.lstrip("/")
        return notes[name]
    raise ValueError(f"Note not found: {name}")


@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """Report that this server does not currently provide MCP prompts."""
    return []


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Describe the available tools and their input schemas to MCP clients."""
    return build_tools()


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict[str, Any] | None,
) -> dict[str, Any] | list[
    types.TextContent | types.ImageContent | types.EmbeddedResource
]:
    """Dispatch an MCP tool call to the appropriate course service operation."""
    if name == "list-courses":
        courses = get_course_service().get_courses()
        return [
            types.TextContent(
                type="text",
                text="\n".join(courses),
            )
        ]

    if name == "list-course-files":
        if arguments is None or "course_title" not in arguments:
            raise ValueError("Missing required argument: course_title")

        files = get_course_service().get_files(arguments["course_title"])
        return [
            types.TextContent(
                type="text",
                text="\n".join(files),
            )
        ]

    if name == "search-course-file":
        required_arguments = ("course_title", "file_path", "keyword")
        for argument in required_arguments:
            if arguments is None or argument not in arguments:
                raise ValueError(f"Missing required argument: {argument}")

        return get_course_service().search_file(
            arguments["course_title"],
            arguments["file_path"],
            arguments["keyword"],
            arguments.get("context_lines", 3),
            arguments.get("max_results", 20),
        )

    if name == "search-course":
        required_arguments = ("course_title", "keyword")
        for argument in required_arguments:
            if arguments is None or argument not in arguments:
                raise ValueError(f"Missing required argument: {argument}")

        return get_course_service().search_course(
            arguments["course_title"],
            arguments["keyword"],
            arguments.get("context_lines", 3),
            arguments.get("max_results", 20),
        )

    if name == "get-upcoming-work":
        arguments = arguments or {}
        return await get_calendar_service().get_upcoming_work(
            start_date=arguments.get("start_date"),
            end_date=arguments.get("end_date"),
            query=arguments.get("query"),
            max_results=arguments.get("max_results", 50),
        )

    if name == "list-piazza-courses":
        return await get_piazza_service().list_courses()

    if name == "list-piazza-posts":
        if arguments is None or "course_id" not in arguments:
            raise ValueError("Missing required argument: course_id")
        return await get_piazza_service().list_posts(
            arguments["course_id"],
            arguments.get("limit", 10),
            arguments.get("offset", 0),
        )

    if name == "get-piazza-post":
        required_arguments = ("course_id", "post_number")
        for argument in required_arguments:
            if arguments is None or argument not in arguments:
                raise ValueError(f"Missing required argument: {argument}")
        return await get_piazza_service().get_post(
            arguments["course_id"],
            arguments["post_number"],
        )

    if name == "search-piazza-posts":
        required_arguments = ("course_id", "query")
        for argument in required_arguments:
            if arguments is None or argument not in arguments:
                raise ValueError(f"Missing required argument: {argument}")
        return await get_piazza_service().search_posts(
            arguments["course_id"],
            arguments["query"],
            arguments.get("max_results", 10),
        )

    raise ValueError(f"Unknown tool: {name}")


async def main():
    """Run the MCP server over standard input and output streams."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="course-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
