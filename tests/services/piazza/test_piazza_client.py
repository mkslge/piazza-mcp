import asyncio
import json
from types import MappingProxyType, SimpleNamespace

from piazza_api.exceptions import NotAuthenticatedError
import pytest

from piazza_mcp.config import PiazzaConfig
from piazza_mcp.services.piazza.client import (
    PiazzaClient,
    PiazzaAuthenticationError,
    PiazzaResponseError,
)
from tests.support import assert_sensitive_value_absent


def config():
    return PiazzaConfig(
        email="student@example.edu",
        password="private-password",
        courses=MappingProxyType({"abc123": "CMSC 132"}),
    )


class FakeNetwork:
    def __init__(self):
        self.filtered_calls = []
        self.feed_filters = SimpleNamespace(
            unread=lambda: ("updated", None),
            following=lambda: ("following", None),
            folder=lambda folder_name: ("folder", folder_name),
        )

    def get_feed(self, limit, offset):
        assert (limit, offset) == (10, 0)
        return {"feed": [{"id": 1}]}

    def get_post(self, post_number):
        return {"nr": post_number, "subject": "Question"}

    def search_feed(self, query):
        assert query == "exam"
        return {"results": [{"id": 2}]}

    def get_filtered_feed(self, feed_filter):
        self.filtered_calls.append(feed_filter)
        return {"posts": [{"id": 3}]}


class FakePiazza:
    def __init__(self):
        self.fake_network = FakeNetwork()

    def get_user_classes(self):
        return [{"nid": "abc123"}]

    def network(self, course_id):
        assert course_id == "abc123"
        return self.fake_network


def test_client_adapts_supported_read_operations_without_live_requests():
    client = PiazzaClient(config())
    client._piazza = FakePiazza()

    assert asyncio.run(client.list_courses()) == [{"nid": "abc123"}]
    assert asyncio.run(client.list_posts("abc123", 10, 0)) == [{"id": 1}]
    assert asyncio.run(client.get_post("abc123", 7))["nr"] == 7
    assert asyncio.run(client.search_posts("abc123", "exam")) == [{"id": 2}]


@pytest.mark.parametrize(
    ("filter_name", "folder_name", "expected_filter"),
    [
        ("updated", None, ("updated", None)),
        ("following", None, ("following", None)),
        ("folder", "Exam Review", ("folder", "Exam Review")),
    ],
)
def test_client_adapts_one_filtered_feed_per_call(
    filter_name,
    folder_name,
    expected_filter,
):
    piazza = FakePiazza()
    client = PiazzaClient(config())
    client._piazza = piazza

    result = asyncio.run(
        client.list_filtered_posts("abc123", filter_name, folder_name)
    )

    assert result == [{"id": 3}]
    assert piazza.fake_network.filtered_calls == [expected_filter]


@pytest.mark.parametrize(
    "payload",
    [
        [{"id": 3}],
        {"feed": [{"id": 3}]},
        {"posts": [{"id": 3}]},
        {"results": [{"id": 3}]},
    ],
)
def test_client_accepts_filtered_feed_envelopes(payload):
    class FilteredNetwork(FakeNetwork):
        def get_filtered_feed(self, feed_filter):
            return payload

    piazza = FakePiazza()
    piazza.fake_network = FilteredNetwork()
    client = PiazzaClient(config())
    client._piazza = piazza

    assert asyncio.run(
        client.list_filtered_posts("abc123", "following", None)
    ) == [{"id": 3}]


def test_client_rejects_malformed_filtered_feed_shape():
    class InvalidFilteredNetwork(FakeNetwork):
        def get_filtered_feed(self, feed_filter):
            return {"unexpected": []}

    piazza = FakePiazza()
    piazza.fake_network = InvalidFilteredNetwork()
    client = PiazzaClient(config())
    client._piazza = piazza

    with pytest.raises(PiazzaResponseError, match="invalid filtered Piazza feed"):
        asyncio.run(client.list_filtered_posts("abc123", "following", None))


def test_client_reauthenticates_once_after_recognized_session_failure(
    monkeypatch,
):
    class ExpiredPiazza:
        def get_user_classes(self):
            raise NotAuthenticatedError("expired")

    client = PiazzaClient(config())
    client._piazza = ExpiredPiazza()
    authentications = []

    def authenticate():
        authentications.append(True)
        client._piazza = FakePiazza()

    monkeypatch.setattr(client, "_authenticate", authenticate)

    assert asyncio.run(client.list_courses()) == [{"nid": "abc123"}]
    assert len(authentications) == 1


def test_client_limits_failed_authentication_to_two_attempts(monkeypatch):
    client = PiazzaClient(config())
    attempts = []

    def fail_authentication():
        attempts.append(True)
        raise NotAuthenticatedError("private upstream detail")

    monkeypatch.setattr(client, "_authenticate", fail_authentication)

    with pytest.raises(
        PiazzaAuthenticationError,
        match="Unable to authenticate with Piazza",
    ) as error:
        asyncio.run(client.list_courses())

    assert len(attempts) == 2
    assert_sensitive_value_absent(error.value, "private upstream detail")


def test_client_rejects_malformed_feed_shape():
    class InvalidNetwork(FakeNetwork):
        def get_feed(self, limit, offset):
            return {"unexpected": []}

    class InvalidPiazza(FakePiazza):
        def network(self, course_id):
            return InvalidNetwork()

    client = PiazzaClient(config())
    client._piazza = InvalidPiazza()

    with pytest.raises(PiazzaResponseError, match="invalid Piazza feed"):
        asyncio.run(client.list_posts("abc123", 10, 0))



def test_client_discards_session_after_invalid_json():
    class InvalidJsonPiazza:
        def get_user_classes(self):
            raise json.JSONDecodeError("invalid", "", 0)

    client = PiazzaClient(config())
    client._piazza = InvalidJsonPiazza()

    with pytest.raises(PiazzaResponseError, match="invalid response"):
        asyncio.run(client.list_courses())

    assert client._piazza is None
