from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import time
from typing import Any

from course_mcp.config import PiazzaConfig
from course_mcp.models.piazza import (
    PiazzaMessage,
    PiazzaPostSummary,
    PiazzaThread,
)

from .client import PiazzaClientError, PiazzaClientProtocol
from .normalizer import PiazzaNormalizationError, PiazzaNormalizer


PIAZZA_CACHE_SECONDS = 60
PIAZZA_LIMITATIONS = [
    "unofficial_internal_api",
    "write_actions_unavailable",
    "attachments_unavailable",
]


class PiazzaService:
    def __init__(
        self,
        config: PiazzaConfig,
        client: PiazzaClientProtocol,
        normalizer: PiazzaNormalizer,
        *,
        monotonic_provider: Callable[[], float] | None = None,
    ):
        self.config = config
        self.client = client
        self.normalizer = normalizer
        self.monotonic_provider = monotonic_provider or time.monotonic
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def list_courses(self) -> dict[str, Any]:
        async def load() -> dict[str, Any]:
            raw_courses = await self.client.list_courses()
            courses = []
            for raw in raw_courses:
                course_id = raw.get("nid")
                if (
                    not isinstance(course_id, str)
                    or course_id not in self.config.courses
                ):
                    continue
                try:
                    course = self.normalizer.normalize_course(
                        raw,
                        self.config.courses[course_id],
                    )
                except PiazzaNormalizationError:
                    continue
                courses.append(asdict(course))
            courses.sort(key=lambda course: course["name"].casefold())
            if not courses:
                raise PiazzaClientError(
                    "No configured Piazza courses are accessible"
                )
            return self._response(courses=courses, returned_count=len(courses))

        return await self._cached("courses", load)

    async def list_posts(
        self,
        course_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        self._validate_course(course_id)
        self._validate_integer(limit, "limit", 1, 25)
        self._validate_integer(offset, "offset", 0, 500)

        async def load() -> dict[str, Any]:
            raw_posts = await self.client.list_posts(course_id, limit, offset)
            posts, skipped = self._normalize_summaries(raw_posts, course_id, limit)
            return self._response(
                course_id=course_id,
                returned_count=len(posts),
                skipped_post_count=skipped,
                truncated=len(raw_posts) >= limit,
                posts=posts,
            )

        return await self._cached(f"feed:{course_id}:{limit}:{offset}", load)

    async def get_post(
        self,
        course_id: str,
        post_number: int,
    ) -> dict[str, Any]:
        self._validate_course(course_id)
        self._validate_integer(post_number, "post_number", 1, 1_000_000_000)

        async def load() -> dict[str, Any]:
            raw_post = await self.client.get_post(course_id, post_number)
            try:
                thread = self.normalizer.normalize_thread(raw_post, course_id)
            except PiazzaNormalizationError:
                raise PiazzaClientError("Piazza returned an unusable post") from None
            return self._response(thread=self._serialize_thread(thread))

        return await self._cached(f"post:{course_id}:{post_number}", load)

    async def search_posts(
        self,
        course_id: str,
        query: str,
        max_results: int = 10,
    ) -> dict[str, Any]:
        self._validate_course(course_id)
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")
        if len(normalized_query) > 200:
            raise ValueError("query cannot exceed 200 characters")
        self._validate_integer(max_results, "max_results", 1, 25)

        async def load() -> dict[str, Any]:
            raw_posts = await self.client.search_posts(course_id, normalized_query)
            posts, skipped = self._normalize_summaries(
                raw_posts,
                course_id,
                max_results,
            )
            return self._response(
                course_id=course_id,
                query=normalized_query,
                returned_count=len(posts),
                skipped_post_count=skipped,
                truncated=len(raw_posts) > max_results,
                posts=posts,
            )

        cache_query = normalized_query.casefold()
        return await self._cached(
            f"search:{course_id}:{cache_query}:{max_results}",
            load,
        )

    async def _cached(
        self,
        key: str,
        loader: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        now = self.monotonic_provider()
        cached = self._cache.get(key)
        if cached is not None and now - cached[0] < PIAZZA_CACHE_SECONDS:
            return deepcopy(cached[1])
        try:
            result = await loader()
        except PiazzaClientError:
            if cached is None:
                raise
            result = deepcopy(cached[1])
            result["stale"] = True
            return result
        self._cache[key] = (now, deepcopy(result))
        return result

    def _normalize_summaries(
        self,
        raw_posts: list[dict[str, Any]],
        course_id: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        posts = []
        skipped = 0
        for raw in raw_posts:
            if len(posts) >= limit:
                break
            try:
                summary = self.normalizer.normalize_summary(raw, course_id)
            except PiazzaNormalizationError:
                skipped += 1
                continue
            posts.append(self._serialize_summary(summary))
        return posts, skipped

    def _validate_course(self, course_id: str) -> None:
        if not isinstance(course_id, str):
            raise ValueError("course_id must be a string")
        if course_id not in self.config.courses:
            raise ValueError("course_id is not a configured Piazza course")

    @staticmethod
    def _validate_integer(
        value: int,
        name: str,
        minimum: int,
        maximum: int,
    ) -> None:
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(
                f"{name} must be an integer from {minimum} to {maximum}"
            )

    @staticmethod
    def _response(**values: Any) -> dict[str, Any]:
        return {
            "source": "piazza",
            "content_trust": "untrusted_user_generated",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "stale": False,
            "limitations": list(PIAZZA_LIMITATIONS),
            **values,
        }

    @classmethod
    def _serialize_message(cls, message: PiazzaMessage) -> dict[str, Any]:
        return {
            "kind": message.kind,
            "body": message.body,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "children": [
                cls._serialize_message(child) for child in message.children
            ],
            "truncated": message.truncated,
        }

    @staticmethod
    def _serialize_summary(summary: PiazzaPostSummary) -> dict[str, Any]:
        return {
            "post_number": summary.post_number,
            "course_id": summary.course_id,
            "kind": summary.kind,
            "subject": summary.subject,
            "snippet": summary.snippet,
            "folders": list(summary.folders),
            "created_at": summary.created_at,
            "updated_at": summary.updated_at,
            "resolved": summary.resolved,
            "source_url": summary.source_url,
            "truncated": summary.truncated,
        }

    @classmethod
    def _serialize_thread(cls, thread: PiazzaThread) -> dict[str, Any]:
        return {
            "post_number": thread.post_number,
            "course_id": thread.course_id,
            "kind": thread.kind,
            "subject": thread.subject,
            "body": thread.body,
            "folders": list(thread.folders),
            "created_at": thread.created_at,
            "updated_at": thread.updated_at,
            "resolved": thread.resolved,
            "instructor_answer": (
                cls._serialize_message(thread.instructor_answer)
                if thread.instructor_answer is not None
                else None
            ),
            "student_answer": (
                cls._serialize_message(thread.student_answer)
                if thread.student_answer is not None
                else None
            ),
            "followups": [
                cls._serialize_message(message) for message in thread.followups
            ],
            "source_url": thread.source_url,
            "truncated": thread.truncated,
            "skipped_child_count": thread.skipped_child_count,
        }
