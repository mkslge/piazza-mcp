import asyncio
import importlib
import json
import sys

import pytest
import mcp.types as types

from course_mcp.mcp_tools import build_tools
from course_mcp.services.calendar import CalendarFeedError, CalendarParseError


def load_server(monkeypatch, root_dir):
    monkeypatch.setenv("ROOT_DIR", str(root_dir))
    monkeypatch.delenv("ROOT_DIR_", raising=False)

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
            "skipped_event_count": 0,
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


class FakePiazzaService:
    def __init__(self):
        self.arguments = None

    @staticmethod
    def metadata():
        return {
            "source": "piazza",
            "content_trust": "untrusted_user_generated",
            "fetched_at": "2026-08-19T12:00:00Z",
            "stale": False,
            "limitations": [
                "unofficial_internal_api",
                "write_actions_unavailable",
                "attachments_unavailable",
            ],
        }

    async def list_courses(self):
        self.arguments = ("courses",)
        return {
            **self.metadata(),
            "returned_count": 1,
            "courses": [
                {
                    "course_id": "abc123",
                    "name": "CMSC 132",
                    "course_number": "CMSC 132",
                    "term": "Fall 2026",
                    "is_ta": False,
                }
            ],
        }

    async def list_posts(self, course_id, limit=10, offset=0):
        self.arguments = ("list", course_id, limit, offset)
        return {
            **self.metadata(),
            "course_id": course_id,
            "returned_count": 1,
            "skipped_post_count": 0,
            "truncated": False,
            "posts": [self.summary(course_id)],
        }

    async def get_post(self, course_id, post_number):
        self.arguments = ("get", course_id, post_number)
        return {
            **self.metadata(),
            "thread": {
                "post_number": post_number,
                "course_id": course_id,
                "kind": "question",
                "subject": "Exam question",
                "body": "When is the exam?",
                "folders": ["exam"],
                "created_at": "2026-08-19T10:00:00Z",
                "updated_at": None,
                "resolved": False,
                "instructor_answer": None,
                "student_answer": None,
                "followups": [],
                "source_url": (
                    f"https://piazza.com/class/{course_id}/post/{post_number}"
                ),
                "truncated": False,
                "skipped_child_count": 0,
            },
        }

    async def search_posts(self, course_id, query, max_results=10):
        self.arguments = ("search", course_id, query, max_results)
        return {
            **self.metadata(),
            "course_id": course_id,
            "query": query,
            "returned_count": 1,
            "skipped_post_count": 0,
            "truncated": False,
            "posts": [self.summary(course_id)],
        }

    @staticmethod
    def summary(course_id):
        return {
            "post_number": 7,
            "course_id": course_id,
            "kind": "question",
            "subject": "Exam question",
            "snippet": "When is the exam?",
            "folders": ["exam"],
            "created_at": "2026-08-19T10:00:00Z",
            "updated_at": None,
            "resolved": False,
            "source_url": f"https://piazza.com/class/{course_id}/post/7",
            "truncated": False,
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
    assert result.structuredContent["skipped_event_count"] == 0
    assert result.structuredContent["items"][0]["uid"] == "event-one"
    assert json.loads(result.content[0].text) == result.structuredContent
    assert fake_service.arguments == (
        "2026-08-20",
        "2026-08-22",
        "project",
        10,
    )


def test_piazza_handlers_dispatch_defaults(monkeypatch, tmp_path):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakePiazzaService()
    monkeypatch.setattr(server, "get_piazza_service", lambda: fake_service)

    courses = asyncio.run(server.handle_call_tool("list-piazza-courses", {}))
    posts = asyncio.run(
        server.handle_call_tool(
            "list-piazza-posts",
            {"course_id": "abc123"},
        )
    )
    thread = asyncio.run(
        server.handle_call_tool(
            "get-piazza-post",
            {"course_id": "abc123", "post_number": 7},
        )
    )
    search = asyncio.run(
        server.handle_call_tool(
            "search-piazza-posts",
            {"course_id": "abc123", "query": "exam"},
        )
    )

    assert courses["courses"][0]["course_id"] == "abc123"
    assert posts["posts"][0]["post_number"] == 7
    assert thread["thread"]["post_number"] == 7
    assert search["query"] == "exam"
    assert fake_service.arguments == ("search", "abc123", "exam", 10)


def test_registered_piazza_tool_returns_structured_content(monkeypatch, tmp_path):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakePiazzaService()
    monkeypatch.setattr(server, "get_piazza_service", lambda: fake_service)

    result = call_registered_tool(
        server,
        "list-piazza-posts",
        {"course_id": "abc123", "limit": 5, "offset": 2},
    )

    assert result.isError is False
    assert result.structuredContent["posts"][0]["post_number"] == 7
    assert json.loads(result.content[0].text) == result.structuredContent
    assert fake_service.arguments == ("list", "abc123", 5, 2)


@pytest.mark.parametrize(
    ("tool_name", "arguments", "missing"),
    [
        ("list-piazza-posts", {}, "course_id"),
        ("get-piazza-post", {"course_id": "abc123"}, "post_number"),
        ("search-piazza-posts", {"course_id": "abc123"}, "query"),
    ],
)
def test_piazza_handlers_require_arguments(
    monkeypatch,
    tmp_path,
    tool_name,
    arguments,
    missing,
):
    server = load_server(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match=f"Missing required argument: {missing}"):
        asyncio.run(server.handle_call_tool(tool_name, arguments))


def test_registered_get_upcoming_work_accepts_date_only_item(
    monkeypatch,
    tmp_path,
):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakeCalendarService()
    original = fake_service.get_upcoming_work

    async def all_day_result(**arguments):
        result = await original(**arguments)
        result["skipped_event_count"] = 1
        result["items"][0]["starts_at"] = "2026-08-21"
        result["items"][0]["ends_at"] = "2026-08-22"
        result["items"][0]["all_day"] = True
        return result

    fake_service.get_upcoming_work = all_day_result
    monkeypatch.setattr(server, "get_calendar_service", lambda: fake_service)

    result = call_registered_tool(server, "get-upcoming-work", {})

    assert result.isError is False
    assert result.structuredContent["skipped_event_count"] == 1
    assert result.structuredContent["items"][0]["starts_at"] == "2026-08-21"


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


def test_registered_get_upcoming_work_rejects_invalid_temporal_output(
    monkeypatch,
    tmp_path,
):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakeCalendarService()

    original = fake_service.get_upcoming_work

    async def malformed_result(**arguments):
        result = await original(**arguments)
        result["items"][0]["starts_at"] = "not-a-date"
        return result

    fake_service.get_upcoming_work = malformed_result
    monkeypatch.setattr(server, "get_calendar_service", lambda: fake_service)

    result = call_registered_tool(server, "get-upcoming-work", {})

    assert result.isError is True
    assert result.structuredContent is None
    assert "Output validation error" in result.content[0].text


def test_registered_get_upcoming_work_rejects_oversized_output(
    monkeypatch,
    tmp_path,
):
    server = load_server(monkeypatch, tmp_path)
    fake_service = FakeCalendarService()

    original = fake_service.get_upcoming_work

    async def oversized_result(**arguments):
        result = await original(**arguments)
        result["items"][0]["title"] = "t" * 501
        return result

    fake_service.get_upcoming_work = oversized_result
    monkeypatch.setattr(server, "get_calendar_service", lambda: fake_service)

    result = call_registered_tool(server, "get-upcoming-work", {})

    assert result.isError is True
    assert result.structuredContent is None
    assert "Output validation error" in result.content[0].text


def test_registered_get_upcoming_work_reports_missing_configuration(
    monkeypatch,
    tmp_path,
):
    server = load_server(monkeypatch, tmp_path)

    def missing_service():
        raise RuntimeError(
            "Canvas calendar is not configured; set CANVAS_ICAL_URL or "
            "CANVAS_ICAL_PATH"
        )

    monkeypatch.setattr(server, "get_calendar_service", missing_service)

    result = call_registered_tool(server, "get-upcoming-work", {})

    assert result.isError is True
    assert result.structuredContent is None
    assert result.content[0].text == (
        "Canvas calendar is not configured; set CANVAS_ICAL_URL or "
        "CANVAS_ICAL_PATH"
    )


@pytest.mark.parametrize(
    "service_error",
    [
        CalendarFeedError("Unable to load Canvas calendar feed"),
        CalendarParseError("Canvas calendar feed contains no usable events"),
    ],
)
def test_registered_get_upcoming_work_reports_safe_calendar_errors(
    monkeypatch,
    tmp_path,
    service_error,
):
    server = load_server(monkeypatch, tmp_path)

    class FailingCalendarService:
        async def get_upcoming_work(self, **arguments):
            raise service_error

    monkeypatch.setattr(
        server,
        "get_calendar_service",
        lambda: FailingCalendarService(),
    )

    result = call_registered_tool(server, "get-upcoming-work", {})

    assert result.isError is True
    assert result.structuredContent is None
    assert result.content[0].text == str(service_error)
    assert "user_test_secret" not in result.content[0].text


def test_list_course_files_returns_files(monkeypatch, tmp_path):
    server = load_server(monkeypatch, tmp_path)
    monkeypatch.setattr(
        server,
        "get_course_service",
        lambda: FakeCourseService(),
    )

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
    monkeypatch.setattr(server, "get_course_service", lambda: fake_service)

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
    monkeypatch.setattr(server, "get_course_service", lambda: fake_service)

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
    monkeypatch.setattr(
        server,
        "get_course_service",
        lambda: FakeCourseService(),
    )

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
    monkeypatch.setattr(server, "get_course_service", lambda: fake_service)

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
    monkeypatch.setattr(server, "get_course_service", lambda: fake_service)

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
