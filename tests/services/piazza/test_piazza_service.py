import asyncio
from types import MappingProxyType

import pytest

from piazza_mcp.config import PiazzaConfig
from piazza_mcp.services.piazza import PiazzaClientError, PiazzaNormalizer
from piazza_mcp.services.piazza.service import (
    MAX_PIAZZA_FILTER_FEED_SCAN,
    PiazzaService,
)
from tests.support import assert_sensitive_value_absent


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
        self.filtered_results = {
            "updated": [[{"id": 1, "subject": "Updated exam post"}]],
            "following": [[{"id": 1, "subject": "Followed exam post"}]],
            "folder": [[{"id": 1, "subject": "Folder exam post"}]],
        }

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

    async def list_filtered_posts(self, course_id, filter_name, folder_name):
        self.calls.append(("filtered", course_id, filter_name, folder_name))
        return self._next(self.filtered_results[filter_name])


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


def test_get_post_history_returns_normalized_history_and_uses_exact_cache_key():
    client = FakeClient()
    client.thread_results = [
        {
            "history": [
                {
                    "subject": "<b>Original</b>",
                    "content": "First body",
                    "created": "2026-08-20T14:00:00Z",
                },
                {
                    "subject": "Revised",
                    "content": "Second body",
                    "created": "2026-08-20T15:00:00Z",
                },
            ]
        }
    ]
    service, _ = make_service(client)

    first = asyncio.run(service.get_post_history("abc123", 1, 2))
    second = asyncio.run(service.get_post_history("abc123", 1, 2))

    assert first == second
    assert client.calls == [("post", "abc123", 1)]
    assert list(service._cache) == ["history:abc123:1:2"]
    assert first["course_id"] == "abc123"
    assert first["post_number"] == 1
    assert first["history_available"] is True
    assert first["ordering"] == "chronological"
    assert first["returned_count"] == 2
    assert first["returned_count"] == len(first["revisions"])
    assert first["revisions"][0]["subject"] == "Original"


def test_post_history_cache_does_not_leak_raw_identity_fields():
    sentinel = "SENSITIVE_CACHED_HISTORY_SENTINEL_91BC"
    client = FakeClient()
    client.thread_results = [
        {
            "history": [
                {
                    "subject": "Visible subject",
                    "content": "Visible body",
                    "uid": sentinel,
                    "name": sentinel,
                    "anon": sentinel,
                    "change_log": {"private": sentinel},
                }
            ]
        }
    ]
    service, _ = make_service(client)

    result = asyncio.run(service.get_post_history("abc123", 1))

    assert client.calls == [("post", "abc123", 1)]
    assert result["revisions"][0]["subject"] == "Visible subject"
    assert_sensitive_value_absent(result, sentinel)
    assert_sensitive_value_absent(service._cache, sentinel)


def test_get_post_history_returns_unavailable_when_piazza_omits_history():
    service, client = make_service()

    result = asyncio.run(service.get_post_history("abc123", 1))

    assert client.calls == [("post", "abc123", 1)]
    assert result["history_available"] is False
    assert result["ordering"] == "unavailable"
    assert result["returned_count"] == 0
    assert result["revisions"] == []


def test_get_post_history_returns_stale_normalized_cache_after_failure():
    clock = FakeClock()
    client = FakeClient()
    client.thread_results = [
        {"history": [{"subject": "Original"}]},
        PiazzaClientError("safe upstream failure"),
    ]
    service, _ = make_service(client, clock)

    fresh = asyncio.run(service.get_post_history("abc123", 1))
    clock.advance(61)
    stale = asyncio.run(service.get_post_history("abc123", 1))

    assert fresh["stale"] is False
    assert stale["stale"] is True
    assert stale["revisions"] == fresh["revisions"]
    assert client.calls == [
        ("post", "abc123", 1),
        ("post", "abc123", 1),
    ]


def test_search_bounds_results_and_normalizes_query():
    service, client = make_service()

    result = asyncio.run(service.search_posts("abc123", "  exam  ", 1))

    assert client.calls == [("search", "abc123", "exam")]
    assert result["query"] == "exam"
    assert result["returned_count"] == 1
    assert result["truncated"] is True
    assert result["posts"][0]["folders"] == ["exam"]
    assert type(result["posts"][0]["folders"]) is list


def test_filtered_posts_intersects_feeds_in_canonical_order_and_caches():
    client = FakeClient()
    client.filtered_results["following"] = [[
        {"id": 3, "subject": "Third"},
        {"id": 2, "subject": "Second"},
        {"id": 1, "subject": "First"},
    ]]
    client.filtered_results["folder"] = [[
        {"id": 2, "subject": "Folder second"},
        {"id": 3, "subject": "Folder third"},
    ]]
    service, _ = make_service(client)

    first = asyncio.run(
        service.list_filtered_posts(
            "abc123",
            ["folder", "following"],
            "  Exam Review  ",
        )
    )
    second = asyncio.run(
        service.list_filtered_posts(
            "abc123",
            ["following", "folder"],
            "Exam Review",
        )
    )

    assert client.calls == [
        ("filtered", "abc123", "following", None),
        ("filtered", "abc123", "folder", "Exam Review"),
    ]
    assert first == second
    assert first["filters"] == ["following", "folder"]
    assert first["match_mode"] == "all"
    assert first["folder_name"] == "Exam Review"
    assert first["upstream_request_count"] == 2
    assert [post["post_number"] for post in first["posts"]] == [3, 2]
    assert first["posts"][0]["subject"] == "Third"


def test_filtered_posts_computes_three_way_intersection():
    client = FakeClient()
    client.filtered_results = {
        "updated": [[
            {"id": 4, "subject": "Fourth"},
            {"id": 3, "subject": "Third"},
            {"id": 2, "subject": "Second"},
        ]],
        "following": [[
            {"id": 3, "subject": "Third"},
            {"id": 2, "subject": "Second"},
        ]],
        "folder": [[
            {"id": 2, "subject": "Second"},
            {"id": 3, "subject": "Third"},
            {"id": 1, "subject": "First"},
        ]],
    }
    service, _ = make_service(client)

    result = asyncio.run(
        service.list_filtered_posts(
            "abc123",
            ["folder", "updated", "following"],
            "exam",
        )
    )

    assert [call[2] for call in client.calls] == [
        "updated",
        "following",
        "folder",
    ]
    assert [post["post_number"] for post in result["posts"]] == [3, 2]
    assert result["upstream_request_count"] == 3


def test_filtered_posts_caps_results_and_keeps_first_duplicate():
    client = FakeClient()
    client.filtered_results["following"] = [[
        {"id": 1, "subject": "First copy"},
        {"id": 1, "subject": "Second copy"},
        {"id": 2, "subject": "Second"},
        {"id": 3, "subject": "Third"},
    ]]
    service, _ = make_service(client)

    result = asyncio.run(
        service.list_filtered_posts("abc123", ["following"], max_results=2)
    )

    assert result["returned_count"] == 2
    assert result["truncated"] is True
    assert [post["post_number"] for post in result["posts"]] == [1, 2]
    assert result["posts"][0]["subject"] == "First copy"


def test_filtered_posts_reports_scan_bound_and_malformed_entries():
    client = FakeClient()
    client.filtered_results["following"] = [[
        *(
            {"id": number, "subject": f"Post {number}"}
            for number in range(1, MAX_PIAZZA_FILTER_FEED_SCAN + 2)
        ),
        {},
    ]]
    client.filtered_results["folder"] = [[
        {"id": MAX_PIAZZA_FILTER_FEED_SCAN, "subject": "Last scanned"},
        {"id": 0, "subject": "Invalid"},
    ]]
    service, _ = make_service(client)

    result = asyncio.run(
        service.list_filtered_posts(
            "abc123",
            ["following", "folder"],
            "exam",
        )
    )

    assert result["truncated"] is True
    assert result["skipped_post_count"] == 1
    assert [post["post_number"] for post in result["posts"]] == [
        MAX_PIAZZA_FILTER_FEED_SCAN
    ]


def test_filtered_posts_counts_malformed_entries_across_feeds():
    client = FakeClient()
    client.filtered_results["following"] = [[
        {},
        {"id": 1, "subject": "Valid"},
    ]]
    client.filtered_results["folder"] = [[
        {"id": 0, "subject": "Invalid"},
        {"id": 1, "subject": "Valid"},
    ]]
    service, _ = make_service(client)

    result = asyncio.run(
        service.list_filtered_posts(
            "abc123",
            ["following", "folder"],
            "exam",
        )
    )

    assert result["skipped_post_count"] == 2
    assert result["returned_count"] == 1
    assert result["truncated"] is False


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda service: service.list_posts("unknown"), "not a configured"),
        (lambda service: service.list_posts("abc123", 0), "limit"),
        (lambda service: service.list_posts("abc123", True), "limit"),
        (lambda service: service.list_posts("abc123", offset=501), "offset"),
        (lambda service: service.get_post("abc123", 0), "post_number"),
        (
            lambda service: service.get_post_history("unknown", 1),
            "not a configured",
        ),
        (
            lambda service: service.get_post_history("abc123", 0),
            "post_number",
        ),
        (
            lambda service: service.get_post_history(
                "abc123", 1, max_revisions=0
            ),
            "max_revisions",
        ),
        (
            lambda service: service.get_post_history(
                "abc123", 1, max_revisions=21
            ),
            "max_revisions",
        ),
        (
            lambda service: service.get_post_history(
                "abc123", 1, max_revisions=True
            ),
            "max_revisions",
        ),
        (lambda service: service.search_posts("abc123", "  "), "query"),
        (lambda service: service.search_posts("abc123", "x" * 201), "query"),
        (lambda service: service.search_posts("abc123", "x", 26), "max_results"),
        (lambda service: service.list_filtered_posts("abc123", []), "filters"),
        (
            lambda service: service.list_filtered_posts(
                "abc123", "following"
            ),
            "filters",
        ),
        (
            lambda service: service.list_filtered_posts(
                "abc123",
                ["updated", "following", "folder", "updated"],
                "exam",
            ),
            "filters",
        ),
        (
            lambda service: service.list_filtered_posts(
                "abc123", ["following", "following"]
            ),
            "filters",
        ),
        (
            lambda service: service.list_filtered_posts("abc123", ["other"]),
            "filters",
        ),
        (
            lambda service: service.list_filtered_posts("abc123", [True]),
            "filters",
        ),
        (
            lambda service: service.list_filtered_posts("abc123", ["folder"]),
            "folder_name",
        ),
        (
            lambda service: service.list_filtered_posts(
                "abc123", ["folder"], "x" * 101
            ),
            "folder_name",
        ),
        (
            lambda service: service.list_filtered_posts(
                "abc123", ["following"], "exam"
            ),
            "folder_name",
        ),
        (
            lambda service: service.list_filtered_posts(
                "abc123", ["following"], max_results=True
            ),
            "max_results",
        ),
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


def test_filtered_posts_returns_only_a_cached_complete_intersection_as_stale():
    clock = FakeClock()
    client = FakeClient()
    client.filtered_results["following"] = [
        [{"id": 1, "subject": "Followed"}],
        [{"id": 1, "subject": "Followed refresh"}],
    ]
    client.filtered_results["folder"] = [
        [{"id": 1, "subject": "Folder"}],
        PiazzaClientError("safe component failure"),
    ]
    service, _ = make_service(client, clock)

    first = asyncio.run(
        service.list_filtered_posts(
            "abc123", ["following", "folder"], "exam"
        )
    )
    clock.advance(61)
    stale = asyncio.run(
        service.list_filtered_posts(
            "abc123", ["folder", "following"], "exam"
        )
    )

    assert first["stale"] is False
    assert stale["stale"] is True
    assert stale["posts"] == first["posts"]
    assert len(client.calls) == 4


def test_filtered_posts_does_not_return_partial_initial_intersection():
    client = FakeClient()
    client.filtered_results["following"] = [[{"id": 1, "subject": "Post"}]]
    client.filtered_results["folder"] = [
        PiazzaClientError("safe component failure")
    ]
    service, _ = make_service(client)

    with pytest.raises(PiazzaClientError, match="safe component failure"):
        asyncio.run(
            service.list_filtered_posts(
                "abc123", ["following", "folder"], "exam"
            )
        )
