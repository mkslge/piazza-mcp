from piazza_mcp.mcp_tools import build_piazza_tools, build_tools


def test_catalog_contains_only_piazza_tools():
    tools = build_tools()

    assert tools == build_piazza_tools()
    assert [tool.name for tool in tools] == [
        "list-piazza-courses",
        "list-piazza-posts",
        "list-piazza-filtered-posts",
        "get-piazza-post",
        "search-piazza-posts",
    ]
