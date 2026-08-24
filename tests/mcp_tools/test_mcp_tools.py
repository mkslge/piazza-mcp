from piazza_mcp.mcp_tools import build_piazza_tools, build_tools
from tests.support import find_named_item


def test_catalog_contains_only_piazza_tools():
    tools = build_tools()

    assert tools == build_piazza_tools()
    assert [tool.name for tool in tools] == [
        "list-piazza-courses",
        "list-piazza-posts",
        "list-piazza-filtered-posts",
        "get-piazza-post",
        "get-piazza-post-history",
        "search-piazza-posts",
    ]


def test_post_history_tool_has_exact_input_and_read_only_contract():
    tool = find_named_item(
        build_piazza_tools(),
        "get-piazza-post-history",
    )

    assert tool.inputSchema == {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "A course ID returned by list-piazza-courses."
                ),
            },
            "post_number": {"type": "integer", "minimum": 1},
            "max_revisions": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "default": 10,
            },
        },
        "required": ["course_id", "post_number"],
        "additionalProperties": False,
    }
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.destructiveHint is False
    assert tool.annotations.idempotentHint is True
    assert tool.annotations.openWorldHint is True
    assert "not a stable revision ID" in tool.description
    assert "untrusted user-generated text" in tool.description
    assert "identities and audit metadata are omitted" in tool.description
