import asyncio
import importlib
import json
import sys

import pytest
import mcp.types as types

from course_mcp.mcp_tools import build_tools


def load_server(monkeypatch, root_dir):
    monkeypatch.setenv("ROOT_DIR", str(root_dir))
    monkeypatch.delenv("ROOT_DIR_", raising=False)

    sys.modules.pop("course_mcp.config", None)
    sys.modules.pop("course_mcp.config.config", None)
    sys.modules.pop("course_mcp.services.file_service", None)
    sys.modules.pop("course_mcp.server", None)

    return importlib.import_module("course_mcp.server")


def call_registered_tool(server_module, name, arguments):
    request = types.CallToolRequest(
        params=types.CallToolRequestParams(
            name=name,
            arguments=arguments,
        )
    )
    handler = server_module.server.request_handlers[types.CallToolRequest]
    return asyncio.run(handler(request)).root


def list_registered_tools(server_module):
    request = types.ListToolsRequest()
    handler = server_module.server.request_handlers[types.ListToolsRequest]
    return asyncio.run(handler(request)).root.tools


class FakeCourseService:
    def __init__(self):
        self.search_arguments = None
        self.course_search_arguments = None

    def get_courses(self):
        return ["CMSC132"]

    def get_files(self, course_title):
        assert course_title == "CMSC132"
        return ["CMSC132/syllabus.pdf", "CMSC132/project1.md"]

    def search_file(
        self,
        course_title,
        file_path,
        keyword,
        context_lines,
        max_results,
    ):
        self.search_arguments = (
            course_title,
            file_path,
            keyword,
            context_lines,
            max_results,
        )
        return {
            "course_title": course_title,
            "file_path": file_path,
            "keyword": keyword,
            "match_count": 0,
            "truncated": False,
            "excerpts": [],
        }

    def search_course(
        self,
        course_title,
        keyword,
        context_lines,
        max_results,
    ):
        self.course_search_arguments = (
            course_title,
            keyword,
            context_lines,
            max_results,
        )
        return {
            "course_title": course_title,
            "keyword": keyword,
            "matching_file_count": 0,
            "match_count": 0,
            "files": [],
        }


class FakeCalendarService:
    def __init__(self):
        self.arguments = None

    async def get_upcoming_work(
        self,
        start_date=None,
        end_date=None,
        query=None,
        max_results=50,
    ):
        self.arguments = (start_date, end_date, query, max_results)
        return {
            "source": "canvas_ical",
            "fetched_at": "2026-08-19T12:00:00Z",
            "stale": False,
            "returned_count": 1,
            "truncated": False,
            "limitations": [
                "completion_status_unavailable",
                "canvas_todo_items_unavailable",
            ],
            "items": [
                {
                    "uid": "event-one",
                    "title": "Project 1",
                    "starts_at": "2026-08-21T23:59:00-04:00",
                    "ends_at": None,
                    "all_day": False,
                    "description": None,
                    "location": None,
                    "item_url": None,
                    "course_hint": None,
                    "item_kind": "unknown",
                }
            ],
        }


def test_registered_server_exposes_tool_catalog(monkeypatch, tmp_path):
    server = load_server(monkeypatch, tmp_path)

    tools = list_registered_tools(server)

    assert tools == build_tools()


def test_get_upcoming_work_returns_result_and_uses_defaults(monkeypatch, tmp_path):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakeCalendarService()
    monkeypatch.setattr(server, "get_calendar_service", lambda: fake_service)

    result = asyncio.run(server.handle_call_tool("get-upcoming-work", {}))

    assert fake_service.arguments == (None, None, None, 50)
    assert result["items"][0]["uid"] == "event-one"


def test_registered_get_upcoming_work_returns_structured_content(
    monkeypatch,
    tmp_path,
):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakeCalendarService()
    monkeypatch.setattr(server, "get_calendar_service", lambda: fake_service)

    result = call_registered_tool(
        server,
        "get-upcoming-work",
        {
            "start_date": "2026-08-20",
            "end_date": "2026-08-22",
            "query": "project",
            "max_results": 10,
        },
    )

    assert result.isError is False
    assert result.structuredContent["items"][0]["uid"] == "event-one"
    assert json.loads(result.content[0].text) == result.structuredContent
    assert fake_service.arguments == (
        "2026-08-20",
        "2026-08-22",
        "project",
        10,
    )


def test_registered_get_upcoming_work_rejects_unknown_argument(
    monkeypatch,
    tmp_path,
):
    server = load_server(monkeypatch, tmp_path)

    result = call_registered_tool(
        server,
        "get-upcoming-work",
        {"course": "CMSC430"},
    )

    assert result.isError is True
    assert "Input validation error" in result.content[0].text


def test_list_course_files_returns_files(monkeypatch, tmp_path):
    server = load_server(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "course_service", FakeCourseService())

    result = asyncio.run(
        server.handle_call_tool(
            "list-course-files",
            {"course_title": "CMSC132"},
        )
    )

    assert result[0].text == "CMSC132/syllabus.pdf\nCMSC132/project1.md"


def test_list_course_files_requires_course_title(monkeypatch, tmp_path):
    server = load_server(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="Missing required argument: course_title"):
        asyncio.run(server.handle_call_tool("list-course-files", {}))


def test_search_course_file_returns_result_and_uses_defaults(monkeypatch, tmp_path):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakeCourseService()
    monkeypatch.setattr(server, "course_service", fake_service)

    result = asyncio.run(
        server.handle_call_tool(
            "search-course-file",
            {
                "course_title": "CMSC132",
                "file_path": "notes/week1.txt",
                "keyword": "recursion",
            },
        )
    )

    assert fake_service.search_arguments == (
        "CMSC132",
        "notes/week1.txt",
        "recursion",
        3,
        20,
    )
    assert result == {
        "course_title": "CMSC132",
        "file_path": "notes/week1.txt",
        "keyword": "recursion",
        "match_count": 0,
        "truncated": False,
        "excerpts": [],
    }


@pytest.mark.parametrize("missing_argument", ["course_title", "file_path", "keyword"])
def test_search_course_file_requires_arguments(
    monkeypatch,
    tmp_path,
    missing_argument,
):
    server = load_server(monkeypatch, tmp_path)
    arguments = {
        "course_title": "CMSC132",
        "file_path": "notes.txt",
        "keyword": "recursion",
    }
    arguments.pop(missing_argument)

    with pytest.raises(
        ValueError,
        match=f"Missing required argument: {missing_argument}",
    ):
        asyncio.run(server.handle_call_tool("search-course-file", arguments))


def test_search_course_returns_result_and_uses_defaults(monkeypatch, tmp_path):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakeCourseService()
    monkeypatch.setattr(server, "course_service", fake_service)

    result = asyncio.run(
        server.handle_call_tool(
            "search-course",
            {"course_title": "CMSC430", "keyword": "compile"},
        )
    )

    assert fake_service.course_search_arguments == (
        "CMSC430",
        "compile",
        3,
        20,
    )
    assert result == {
        "course_title": "CMSC430",
        "keyword": "compile",
        "matching_file_count": 0,
        "match_count": 0,
        "files": [],
    }


@pytest.mark.parametrize("missing_argument", ["course_title", "keyword"])
def test_search_course_requires_arguments(monkeypatch, tmp_path, missing_argument):
    server = load_server(monkeypatch, tmp_path)
    arguments = {"course_title": "CMSC430", "keyword": "compile"}
    arguments.pop(missing_argument)

    with pytest.raises(
        ValueError,
        match=f"Missing required argument: {missing_argument}",
    ):
        asyncio.run(server.handle_call_tool("search-course", arguments))


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected"),
    [
        (
            "search-course-file",
            {
                "course_title": "CMSC132",
                "file_path": "notes.txt",
                "keyword": "recursion",
            },
            {
                "course_title": "CMSC132",
                "file_path": "notes.txt",
                "keyword": "recursion",
                "match_count": 0,
                "truncated": False,
                "excerpts": [],
            },
        ),
        (
            "search-course",
            {"course_title": "CMSC132", "keyword": "recursion"},
            {
                "course_title": "CMSC132",
                "keyword": "recursion",
                "matching_file_count": 0,
                "match_count": 0,
                "files": [],
            },
        ),
    ],
)
def test_registered_search_tools_return_structured_and_compatibility_content(
    monkeypatch,
    tmp_path,
    tool_name,
    arguments,
    expected,
):
    server = load_server(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "course_service", FakeCourseService())

    result = call_registered_tool(server, tool_name, arguments)

    assert result.isError is False
    assert result.structuredContent == expected
    assert len(result.content) == 1
    assert isinstance(result.content[0], types.TextContent)
    assert json.loads(result.content[0].text) == expected


def test_registered_search_tool_reports_input_validation_errors(
    monkeypatch,
    tmp_path,
):
    server = load_server(monkeypatch, tmp_path)

    result = call_registered_tool(
        server,
        "search-course-file",
        {"course_title": "CMSC132", "keyword": "recursion"},
    )

    assert result.isError is True
    assert result.structuredContent is None
    assert "Input validation error" in result.content[0].text
    assert "file_path" in result.content[0].text


def test_registered_search_tool_reports_service_errors(monkeypatch, tmp_path):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakeCourseService()

    def fail_search(*args):
        raise ValueError("Course is not available")

    fake_service.search_file = fail_search
    monkeypatch.setattr(server, "course_service", fake_service)

    result = call_registered_tool(
        server,
        "search-course-file",
        {
            "course_title": "CMSC999",
            "file_path": "notes.txt",
            "keyword": "recursion",
        },
    )

    assert result.isError is True
    assert result.structuredContent is None
    assert result.content[0].text == "Course is not available"


def test_registered_search_tool_rejects_invalid_structured_output(
    monkeypatch,
    tmp_path,
):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakeCourseService()

    def malformed_search(*args):
        return {"course_title": "CMSC132"}

    fake_service.search_file = malformed_search
    monkeypatch.setattr(server, "course_service", fake_service)

    result = call_registered_tool(
        server,
        "search-course-file",
        {
            "course_title": "CMSC132",
            "file_path": "notes.txt",
            "keyword": "recursion",
        },
    )

    assert result.isError is True
    assert result.structuredContent is None
    assert "Output validation error" in result.content[0].text
