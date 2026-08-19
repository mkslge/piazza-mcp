import importlib
import sys


def test_search_schemas_are_exported_without_importing_server():
    sys.modules.pop("course_mcp.server", None)

    schemas = importlib.import_module("course_mcp.mcp_schemas")

    assert schemas.__all__ == [
        "GET_UPCOMING_WORK_OUTPUT_SCHEMA",
        "SEARCH_COURSE_FILE_OUTPUT_SCHEMA",
        "SEARCH_COURSE_OUTPUT_SCHEMA",
    ]
    assert schemas.GET_UPCOMING_WORK_OUTPUT_SCHEMA["type"] == "object"
    assert schemas.SEARCH_COURSE_FILE_OUTPUT_SCHEMA["type"] == "object"
    assert schemas.SEARCH_COURSE_OUTPUT_SCHEMA["type"] == "object"
    assert "course_mcp.server" not in sys.modules
