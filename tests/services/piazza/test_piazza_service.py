import asyncio
from types import MappingProxyType

import pytest

from piazza_mcp.config import PiazzaConfig
from piazza_mcp.services.piazza import PiazzaClientError, PiazzaNormalizer
from piazza_mcp.services.piazza.service import PiazzaService


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeClient:
    def __init__(self):
        self.calls = []
        self.course_results = [[
            {"nid": "abc123", "num": "CMSC 132", "term": "Fall 2026"},
            {"nid": "not-allowed", "num": "OTHER"},
        ]]
        self.post_results = [[
            {
                "id": 1,
                "type": "question",
                "subject": "Exam",
                "content_snip": "When is it?",
                "folders": ["exam"],
            }
        ]]
        self.thread_results = [{
            "nr": 1,
            "type": "question",
            "subject": "Exam",
            "content": "When is it?",
        }]
        self.search_results = [[
            {"id": 1, "subject": "Exam", "folders": ["exam"]},
            {"id": 2, "subject": "Exam review"},
        ]]

    @staticmethod
    def _next(results):
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def list_courses(self):
        self.calls.append(("courses",))
        return self._next(self.course_results)

    async def list_posts(self, course_id, limit, offset):
        self.calls.append(("posts", course_id, limit, offset))
        return self._next(self.post_results)

    async def get_post(self, course_id, post_number):
        self.calls.append(("post", course_id, post_number))
        return self._next(self.thread_results)

    async def search_posts(self, course_id, query):
        self.calls.append(("search", course_id, query))
        return self._next(self.search_results)


def make_service(client=None, clock=None):
    config = PiazzaConfig(
        email="student@example.edu",
        password="private-password",
        courses=MappingProxyType({"abc123": "CMSC 132"}),
    )
    client = client or FakeClient()
    return (
        PiazzaService(
            config,
            client,
            PiazzaNormalizer(),
            monotonic_provider=clock,
        ),
        client,
    )


def test_lists_only_configured_accessible_courses():
    service, _ = make_service()

    result = asyncio.run(service.list_courses())

    assert result["returned_count"] == 1
    assert result["courses"][0]["course_id"] == "abc123"
    assert result["courses"][0]["name"] == "CMSC 132"
    assert result["content_trust"] == "untrusted_user_generated"


def test_lists_summaries_without_fetching_full_posts():
    service, client = make_service()

    result = asyncio.run(service.list_posts("abc123"))

    assert client.calls == [("posts", "abc123", 10, 0)]
    assert result["posts"][0]["subject"] == "Exam"
    assert result["posts"][0]["folders"] == ["exam"]
    assert type(result["posts"][0]["folders"]) is list
    assert result["returned_count"] == 1


@pytest.mark.parametrize("folders", [[], ["project"], ["project", "exam"]])
def test_list_posts_serializes_folders_as_json_arrays(folders):
    client = FakeClient()
    client.post_results = [[
        {"id": 1, "subject": "Project", "folders": folders}
    ]]
    service, _ = make_service(client)

    result = asyncio.run(service.list_posts("abc123"))

    assert result["posts"][0]["folders"] == folders
    assert type(result["posts"][0]["folders"]) is list


def test_get_post_returns_normalized_thread():
    service, client = make_service()

    result = asyncio.run(service.get_post("abc123", 1))

    assert client.calls == [("post", "abc123", 1)]
    assert result["thread"]["body"] == "When is it?"
    assert result["thread"]["source_url"].endswith("/abc123/post/1")


def test_search_bounds_results_and_normalizes_query():
    service, client = make_service()

    result = asyncio.run(service.search_posts("abc123", "  exam  ", 1))

    assert client.calls == [("search", "abc123", "exam")]
    assert result["query"] == "exam"
    assert result["returned_count"] == 1
    assert result["truncated"] is True
    assert result["posts"][0]["folders"] == ["exam"]
    assert type(result["posts"][0]["folders"]) is list


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda service: service.list_posts("unknown"), "not a configured"),
        (lambda service: service.list_posts("abc123", 0), "limit"),
        (lambda service: service.list_posts("abc123", True), "limit"),
        (lambda service: service.list_posts("abc123", offset=501), "offset"),
        (lambda service: service.get_post("abc123", 0), "post_number"),
        (lambda service: service.search_posts("abc123", "  "), "query"),
        (lambda service: service.search_posts("abc123", "x" * 201), "query"),
        (lambda service: service.search_posts("abc123", "x", 26), "max_results"),
    ],
)
def test_invalid_inputs_fail_before_network_call(operation, message):
    service, client = make_service()

    with pytest.raises(ValueError, match=message):
        asyncio.run(operation(service))

    assert client.calls == []


def test_cache_reuses_fresh_result_and_returns_stale_after_failure():
    clock = FakeClock()
    client = FakeClient()
    client.post_results.append(PiazzaClientError("safe upstream failure"))
    service, _ = make_service(client, clock)

    first = asyncio.run(service.list_posts("abc123"))
    second = asyncio.run(service.list_posts("abc123"))
    clock.advance(61)
    stale = asyncio.run(service.list_posts("abc123"))

    assert first == second
    assert stale["stale"] is True
    assert len(client.calls) == 2


def test_initial_client_failure_is_not_hidden():
    client = FakeClient()
    client.post_results = [PiazzaClientError("Unable to reach Piazza")]
    service, _ = make_service(client)

    with pytest.raises(PiazzaClientError, match="Unable to reach Piazza"):
        asyncio.run(service.list_posts("abc123"))
