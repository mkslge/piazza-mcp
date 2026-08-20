from course_mcp.mcp_tools import (
    build_calendar_tools,
    build_course_tools,
    build_piazza_tools,
    build_tools,
)


def test_catalog_includes_course_files_tool():
    tools = build_course_tools()

    tool_names = [tool.name for tool in tools]
    assert "list-courses" in tool_names
    assert "list-course-files" in tool_names

    course_files_tool = next(
        tool for tool in tools if tool.name == "list-course-files"
    )
    assert course_files_tool.inputSchema["required"] == ["course_title"]


def test_catalog_includes_search_course_file_tool():
    tools = build_course_tools()

    search_tool = next(tool for tool in tools if tool.name == "search-course-file")
    schema = search_tool.inputSchema
    assert schema["required"] == ["course_title", "file_path", "keyword"]
    assert schema["properties"]["keyword"]["minLength"] == 1
    assert schema["properties"]["context_lines"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 20,
        "default": 3,
        "description": "Lines of context before and after each match.",
    }
    assert schema["properties"]["max_results"]["minimum"] == 1
    assert schema["properties"]["max_results"]["maximum"] == 100
    assert schema["properties"]["max_results"]["default"] == 20
    output_schema = search_tool.outputSchema
    assert output_schema is not None
    assert output_schema["additionalProperties"] is False
    assert output_schema["required"] == [
        "course_title",
        "file_path",
        "keyword",
        "match_count",
        "truncated",
        "excerpts",
    ]
    excerpt_schema = output_schema["properties"]["excerpts"]["items"]
    assert "page" in excerpt_schema["properties"]
    assert "page" not in excerpt_schema["required"]
    assert excerpt_schema["additionalProperties"] is False
    assert (
        excerpt_schema["properties"]["lines"]["items"]["additionalProperties"]
        is False
    )


def test_catalog_includes_search_course_tool():
    tools = build_course_tools()

    search_tool = next(tool for tool in tools if tool.name == "search-course")
    schema = search_tool.inputSchema
    assert schema["required"] == ["course_title", "keyword"]
    assert schema["properties"]["keyword"]["minLength"] == 1
    assert schema["properties"]["context_lines"]["default"] == 3
    assert schema["properties"]["context_lines"]["maximum"] == 20
    assert schema["properties"]["max_results"]["default"] == 20
    assert schema["properties"]["max_results"]["maximum"] == 100
    output_schema = search_tool.outputSchema
    assert output_schema is not None
    assert output_schema["additionalProperties"] is False
    assert output_schema["required"] == [
        "course_title",
        "keyword",
        "matching_file_count",
        "match_count",
        "files",
    ]
    file_schema = output_schema["properties"]["files"]["items"]
    assert file_schema["additionalProperties"] is False
    assert file_schema["required"] == [
        "file_path",
        "match_count",
        "truncated",
        "excerpts",
    ]


def test_catalog_includes_get_upcoming_work_tool():
    calendar_tool = build_calendar_tools()[0]

    assert calendar_tool.name == "get-upcoming-work"
    assert "required" not in calendar_tool.inputSchema
    assert calendar_tool.inputSchema["additionalProperties"] is False
    assert calendar_tool.inputSchema["properties"]["max_results"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "default": 50,
        "description": "Maximum calendar items to return.",
    }
    assert calendar_tool.outputSchema["additionalProperties"] is False
    assert calendar_tool.outputSchema["properties"]["items"]["maxItems"] == 100
    assert calendar_tool.outputSchema["properties"]["skipped_event_count"] == {
        "type": "integer",
        "minimum": 0,
    }
    item_schema = calendar_tool.outputSchema["properties"]["items"]["items"]
    assert item_schema["properties"]["starts_at"]["anyOf"][0]["format"] == (
        "date"
    )
    assert item_schema["properties"]["starts_at"]["anyOf"][1]["format"] == (
        "date-time"
    )
    assert item_schema["properties"]["uid"]["maxLength"] == 512
    assert item_schema["properties"]["title"]["maxLength"] == 500
    assert calendar_tool.outputSchema["properties"]["returned_count"][
        "maximum"
    ] == 100


def test_complete_catalog_contains_all_service_tools():
    tools = build_tools()

    assert tools == [
        *build_course_tools(),
        *build_calendar_tools(),
        *build_piazza_tools(),
    ]


def test_piazza_tools_are_read_only_bounded_and_schema_backed():
    tools = build_piazza_tools()

    assert [tool.name for tool in tools] == [
        "list-piazza-courses",
        "list-piazza-posts",
        "get-piazza-post",
        "search-piazza-posts",
    ]
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

    search = tools[3]
    assert search.inputSchema["properties"]["query"]["maxLength"] == 200
    assert search.inputSchema["properties"]["max_results"]["maximum"] == 25
