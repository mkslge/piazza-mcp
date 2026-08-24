import importlib
import sys


def test_piazza_schemas_are_exported_without_importing_server():
    sys.modules.pop("piazza_mcp.server", None)

    schemas = importlib.import_module("piazza_mcp.mcp_schemas")

    assert schemas.__all__ == [
        "GET_PIAZZA_POST_OUTPUT_SCHEMA",
        "LIST_PIAZZA_COURSES_OUTPUT_SCHEMA",
        "LIST_PIAZZA_POSTS_OUTPUT_SCHEMA",
        "SEARCH_PIAZZA_POSTS_OUTPUT_SCHEMA",
    ]
    assert schemas.GET_PIAZZA_POST_OUTPUT_SCHEMA["type"] == "object"
    assert schemas.LIST_PIAZZA_COURSES_OUTPUT_SCHEMA["type"] == "object"
    assert schemas.LIST_PIAZZA_POSTS_OUTPUT_SCHEMA["type"] == "object"
    assert schemas.SEARCH_PIAZZA_POSTS_OUTPUT_SCHEMA["type"] == "object"
    assert "piazza_mcp.server" not in sys.modules
