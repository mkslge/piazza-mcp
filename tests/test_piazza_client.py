import asyncio
from types import MappingProxyType

from piazza_api.exceptions import NotAuthenticatedError
import pytest
import requests

from course_mcp.config import PiazzaConfig
from course_mcp.services.piazza.client import (
    PiazzaClient,
    PiazzaAuthenticationError,
    PiazzaResponseError,
    PiazzaTimeoutError,
)


def config():
    return PiazzaConfig(
        email="student@example.edu",
        password="private-password",
        courses=MappingProxyType({"abc123": "CMSC 132"}),
    )


class FakeNetwork:
    def get_feed(self, limit, offset):
        assert (limit, offset) == (10, 0)
        return {"feed": [{"id": 1}]}

    def get_post(self, post_number):
        return {"nr": post_number, "subject": "Question"}

    def search_feed(self, query):
        assert query == "exam"
        return {"results": [{"id": 2}]}


class FakePiazza:
    def get_user_classes(self):
        return [{"nid": "abc123"}]

    def network(self, course_id):
        assert course_id == "abc123"
        return FakeNetwork()


def test_client_adapts_supported_read_operations_without_live_requests():
    client = PiazzaClient(config())
    client._piazza = FakePiazza()

    assert asyncio.run(client.list_courses()) == [{"nid": "abc123"}]
    assert asyncio.run(client.list_posts("abc123", 10, 0)) == [{"id": 1}]
    assert asyncio.run(client.get_post("abc123", 7))["nr"] == 7
    assert asyncio.run(client.search_posts("abc123", "exam")) == [{"id": 2}]


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
    assert "private upstream detail" not in str(error.value)


def test_client_translates_timeout_without_upstream_details():
    class TimeoutPiazza:
        def get_user_classes(self):
            raise requests.Timeout("private URL")

    client = PiazzaClient(config())
    client._piazza = TimeoutPiazza()

    with pytest.raises(PiazzaTimeoutError, match="Piazza request timed out"):
        asyncio.run(client.list_courses())


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
