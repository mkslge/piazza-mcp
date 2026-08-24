from piazza_mcp.mcp_tools.piazza import build_piazza_tools


def build_tools():
    """Build the complete Piazza MCP tool catalog."""
    return build_piazza_tools()


__all__ = [
    "build_piazza_tools",
    "build_tools",
]
