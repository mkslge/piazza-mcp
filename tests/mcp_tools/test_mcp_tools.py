from piazza_mcp.mcp_tools import build_piazza_tools, build_tools


def test_catalog_contains_only_piazza_tools():
    tools = build_tools()

    assert tools == build_piazza_tools()
    assert [tool.name for tool in tools] == [
        "list-piazza-courses",
        "list-piazza-posts",
        "get-piazza-post",
        "search-piazza-posts",
    ]


def test_piazza_tools_are_read_only_bounded_and_schema_backed():
    tools = build_piazza_tools()

    for tool in tools:
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is True
        assert tool.inputSchema["additionalProperties"] is False
        assert tool.outputSchema["additionalProperties"] is False

    list_posts = tools[1]
    assert list_posts.inputSchema["properties"]["limit"]["maximum"] == 25
    assert list_posts.outputSchema["properties"]["posts"]["maxItems"] == 25
    assert "maximum limit is 25" in list_posts.description
    assert "request one page at a time" in list_posts.description
    assert "Stop when truncated=false" in list_posts.description
    assert "do not prefetch speculative offsets" in list_posts.description

    search = tools[3]
    assert search.inputSchema["properties"]["query"]["maxLength"] == 200
    assert search.inputSchema["properties"]["max_results"]["maximum"] == 25
