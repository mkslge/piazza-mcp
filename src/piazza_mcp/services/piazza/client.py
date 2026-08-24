import asyncio
from collections.abc import Callable
import json
from typing import Any, Protocol, TypeVar

from piazza_api import Piazza
from piazza_api.exceptions import AuthenticationError, NotAuthenticatedError
from piazza_api.rpc import PiazzaRPC
import requests

from piazza_mcp.config import PiazzaConfig


class PiazzaClientError(RuntimeError):
    """Base error for safe Piazza transport failures."""


class PiazzaAuthenticationError(PiazzaClientError):
    """Raised when Piazza credentials or session authentication fail."""


class PiazzaTimeoutError(PiazzaClientError):
    """Raised when Piazza does not respond before the configured timeout."""


class PiazzaResponseError(PiazzaClientError):
    """Raised when Piazza returns an unusable response."""


class PiazzaClientProtocol(Protocol):
    async def list_courses(self) -> list[dict[str, Any]]: ...

    async def list_posts(
        self,
        course_id: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]: ...

    async def get_post(
        self,
        course_id: str,
        post_number: int,
    ) -> dict[str, Any]: ...

    async def search_posts(
        self,
        course_id: str,
        query: str,
    ) -> list[dict[str, Any]]: ...


class _TimeoutSession(requests.Session):
    def __init__(self, timeout_seconds: float):
        super().__init__()
        self.timeout_seconds = timeout_seconds

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", self.timeout_seconds)
        return super().request(method, url, **kwargs)


T = TypeVar("T")


class PiazzaClient:
    """Async, bounded adapter around the synchronous unofficial Piazza API."""

    def __init__(self, config: PiazzaConfig):
        self.config = config
        self._piazza: Piazza | None = None
        self._lock = asyncio.Lock()

    async def list_courses(self) -> list[dict[str, Any]]:
        result = await self._run(lambda piazza: piazza.get_user_classes())
        return self._require_dict_list(result, "course list")

    async def list_posts(
        self,
        course_id: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        result = await self._run(
            lambda piazza: piazza.network(course_id).get_feed(limit, offset)
        )
        return self._extract_posts(result, "Piazza feed")

    async def get_post(
        self,
        course_id: str,
        post_number: int,
    ) -> dict[str, Any]:
        result = await self._run(
            lambda piazza: piazza.network(course_id).get_post(post_number)
        )
        if not isinstance(result, dict) or not result:
            raise PiazzaResponseError("Piazza returned an invalid post")
        return result

    async def search_posts(
        self,
        course_id: str,
        query: str,
    ) -> list[dict[str, Any]]:
        result = await self._run(
            lambda piazza: piazza.network(course_id).search_feed(query)
        )
        return self._extract_posts(result, "Piazza search")

    async def _run(self, operation: Callable[[Piazza], T]) -> T:
        async with self._lock:
            return await asyncio.to_thread(self._run_sync, operation)

    def _run_sync(self, operation: Callable[[Piazza], T]) -> T:
        for attempt in range(2):
            try:
                if self._piazza is None:
                    self._authenticate()
                return operation(self._piazza)
            except (AuthenticationError, NotAuthenticatedError):
                self._piazza = None
                if attempt == 1:
                    raise PiazzaAuthenticationError(
                        "Unable to authenticate with Piazza"
                    ) from None
            except requests.Timeout:
                raise PiazzaTimeoutError("Piazza request timed out") from None
            except (json.JSONDecodeError, TypeError, ValueError):
                self._piazza = None
                raise PiazzaResponseError(
                    "Piazza returned an invalid response"
                ) from None
            except requests.RequestException:
                raise PiazzaClientError("Unable to reach Piazza") from None
            except PiazzaClientError:
                raise
            except Exception:
                raise PiazzaClientError("Unable to load Piazza data") from None

        raise PiazzaAuthenticationError("Unable to authenticate with Piazza")

    def _authenticate(self) -> None:
        rpc = PiazzaRPC()
        rpc.session = _TimeoutSession(self.config.request_timeout_seconds)
        rpc.user_login(
            email=self.config.email,
            password=self.config.password,
        )
        self._piazza = Piazza(piazza_rpc=rpc)

    @staticmethod
    def _require_dict_list(value: Any, label: str) -> list[dict[str, Any]]:
        if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value
        ):
            raise PiazzaResponseError(f"Piazza returned an invalid {label}")
        return value

    @classmethod
    def _extract_posts(
        cls,
        value: Any,
        label: str,
    ) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return cls._require_dict_list(value, label)
        if isinstance(value, dict):
            for key in ("feed", "posts", "results"):
                if key in value:
                    return cls._require_dict_list(value[key], label)
        raise PiazzaResponseError(f"Piazza returned an invalid {label}")
