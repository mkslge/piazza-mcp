import asyncio
from typing import Any

from piazza_mcp.mcp_tools import build_tools
from piazza_mcp.services.piazza import get_piazza_service
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

server = Server("piazza-mcp")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Describe the available Piazza tools to MCP clients."""
    return build_tools()


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict[str, Any] | None,
) -> dict[str, Any] | list[
    types.TextContent | types.ImageContent | types.EmbeddedResource
]:
    """Dispatch an MCP tool call to the Piazza service."""
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

    if name == "list-piazza-filtered-posts":
        required_arguments = ("course_id", "filters")
        for argument in required_arguments:
            if arguments is None or argument not in arguments:
                raise ValueError(f"Missing required argument: {argument}")
        return await get_piazza_service().list_filtered_posts(
            arguments["course_id"],
            arguments["filters"],
            arguments.get("folder_name"),
            arguments.get("max_results", 10),
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
                server_name="piazza-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
