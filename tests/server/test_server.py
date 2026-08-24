import asyncio
import importlib
import json
import sys

import mcp.types as types
import pytest

from piazza_mcp.mcp_tools import build_tools


def load_server():
    sys.modules.pop("piazza_mcp.server", None)
    return importlib.import_module("piazza_mcp.server")


def call_registered_tool(server_module, name, arguments):
    request = types.CallToolRequest(
        params=types.CallToolRequestParams(name=name, arguments=arguments)
    )
    handler = server_module.server.request_handlers[types.CallToolRequest]
    return asyncio.run(handler(request)).root


def list_registered_tools(server_module):
    request = types.ListToolsRequest()
    handler = server_module.server.request_handlers[types.ListToolsRequest]
    return asyncio.run(handler(request)).root.tools


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

    async def get_post_history(
        self,
        course_id,
        post_number,
        max_revisions=10,
    ):
        self.arguments = (
            "history",
            course_id,
            post_number,
            max_revisions,
        )
        return {
            **self.metadata(),
            "course_id": course_id,
            "post_number": post_number,
            "history_available": True,
            "ordering": "chronological",
            "returned_count": 1,
            "skipped_revision_count": 0,
            "truncated": False,
            "revisions": [
                {
                    "sequence": 1,
                    "subject": "Exam question",
                    "body": "When is the exam?",
                    "created_at": "2026-08-19T10:00:00Z",
                    "truncated": False,
                }
            ],
        }

    async def list_filtered_posts(
        self,
        course_id,
        filters,
        folder_name=None,
        max_results=10,
    ):
        self.arguments = (
            "filtered",
            course_id,
            filters,
            folder_name,
            max_results,
        )
        return {
            **self.metadata(),
            "course_id": course_id,
            "filters": filters,
            "match_mode": "all",
            "folder_name": folder_name,
            "upstream_request_count": len(filters),
            "returned_count": 1,
            "skipped_post_count": 0,
            "truncated": False,
            "posts": [self.summary(course_id)],
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


def test_registered_server_exposes_only_piazza_tools():
    server = load_server()

    assert list_registered_tools(server) == build_tools()


@pytest.mark.parametrize(
    ("tool_name", "arguments", "result_key"),
    [
        ("list-piazza-courses", {}, "courses"),
        (
            "list-piazza-posts",
            {"course_id": "abc123", "limit": 5, "offset": 2},
            "posts",
        ),
        (
            "list-piazza-filtered-posts",
            {
                "course_id": "abc123",
                "filters": ["following", "folder"],
                "folder_name": "exam",
            },
            "posts",
        ),
        (
            "get-piazza-post",
            {"course_id": "abc123", "post_number": 7},
            "thread",
        ),
        (
            "get-piazza-post-history",
            {"course_id": "abc123", "post_number": 7},
            "revisions",
        ),
        (
            "search-piazza-posts",
            {"course_id": "abc123", "query": "exam"},
            "posts",
        ),
    ],
)
def test_registered_tools_return_valid_structured_content(
    monkeypatch,
    tool_name,
    arguments,
    result_key,
):
    server = load_server()
    fake_service = FakePiazzaService()
    monkeypatch.setattr(server, "get_piazza_service", lambda: fake_service)

    result = call_registered_tool(server, tool_name, arguments)

    assert result.isError is False
    assert result_key in result.structuredContent
    assert json.loads(result.content[0].text) == result.structuredContent


@pytest.mark.parametrize(
    ("arguments", "expected_max_revisions"),
    [
        ({"course_id": "abc123", "post_number": 7}, 10),
        (
            {
                "course_id": "abc123",
                "post_number": 7,
                "max_revisions": 4,
            },
            4,
        ),
    ],
)
def test_post_history_dispatch_forwards_default_and_explicit_revision_limit(
    monkeypatch,
    arguments,
    expected_max_revisions,
):
    server = load_server()
    fake_service = FakePiazzaService()
    monkeypatch.setattr(server, "get_piazza_service", lambda: fake_service)

    result = asyncio.run(
        server.handle_call_tool("get-piazza-post-history", arguments)
    )

    assert result["revisions"]
    assert fake_service.arguments == (
        "history",
        "abc123",
        7,
        expected_max_revisions,
    )


@pytest.mark.parametrize(
    ("tool_name", "arguments", "missing"),
    [
        ("list-piazza-posts", {}, "course_id"),
        ("list-piazza-filtered-posts", {}, "course_id"),
        (
            "list-piazza-filtered-posts",
            {"course_id": "abc123"},
            "filters",
        ),
        ("get-piazza-post", {"course_id": "abc123"}, "post_number"),
        ("get-piazza-post-history", {}, "course_id"),
        (
            "get-piazza-post-history",
            {"course_id": "abc123"},
            "post_number",
        ),
        ("search-piazza-posts", {"course_id": "abc123"}, "query"),
    ],
)
def test_handlers_require_arguments(tool_name, arguments, missing):
    server = load_server()

    with pytest.raises(ValueError, match=f"Missing required argument: {missing}"):
        asyncio.run(server.handle_call_tool(tool_name, arguments))


def test_handler_rejects_unknown_tool():
    server = load_server()

    with pytest.raises(ValueError, match="Unknown tool: get-upcoming-work"):
        asyncio.run(server.handle_call_tool("get-upcoming-work", {}))
