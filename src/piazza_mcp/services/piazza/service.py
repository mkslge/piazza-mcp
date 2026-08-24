from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import time
from typing import Any

from piazza_mcp.config import PiazzaConfig
from piazza_mcp.models.piazza import (
    MAX_PIAZZA_REVISIONS,
    PiazzaMessage,
    PiazzaPostHistory,
    PiazzaPostSummary,
    PiazzaRevision,
    PiazzaThread,
)

from .client import PiazzaClientError, PiazzaClientProtocol
from .normalizer import PiazzaNormalizationError, PiazzaNormalizer


PIAZZA_CACHE_SECONDS = 60
MAX_PIAZZA_FILTER_FEED_SCAN = 500
PIAZZA_FILTER_ORDER = ("updated", "following", "folder")
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
                raise PiazzaClientError(
                    "Piazza returned an unusable post"
                ) from None
            return self._response(thread=self._serialize_thread(thread))

        return await self._cached(f"post:{course_id}:{post_number}", load)

    async def get_post_history(
        self,
        course_id: str,
        post_number: int,
        max_revisions: int = 10,
    ) -> dict[str, Any]:
        self._validate_course(course_id)
        self._validate_integer(post_number, "post_number", 1, 1_000_000_000)
        self._validate_integer(
            max_revisions,
            "max_revisions",
            1,
            MAX_PIAZZA_REVISIONS,
        )

        async def load() -> dict[str, Any]:
            raw_post = await self.client.get_post(course_id, post_number)
            try:
                history = self.normalizer.normalize_history(
                    raw_post,
                    course_id,
                    post_number,
                    max_revisions,
                )
            except PiazzaNormalizationError:
                raise PiazzaClientError("Piazza returned an unusable post") from None
            return self._response(**self._serialize_post_history(history))

        return await self._cached(
            f"history:{course_id}:{post_number}:{max_revisions}",
            load,
        )

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

    async def list_filtered_posts(
        self,
        course_id: str,
        filters: list[str],
        folder_name: str | None = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        self._validate_course(course_id)
        canonical_filters = self._validate_filters(filters)
        self._validate_integer(max_results, "max_results", 1, 25)
        normalized_folder = self._validate_filter_folder(
            canonical_filters,
            folder_name,
        )

        async def load() -> dict[str, Any]:
            feed_maps: list[dict[int, PiazzaPostSummary]] = []
            skipped = 0
            scan_truncated = False

            for filter_name in canonical_filters:
                raw_posts = await self.client.list_filtered_posts(
                    course_id,
                    filter_name,
                    normalized_folder if filter_name == "folder" else None,
                )
                scan_truncated = (
                    scan_truncated
                    or len(raw_posts) > MAX_PIAZZA_FILTER_FEED_SCAN
                )
                normalized_posts: dict[int, PiazzaPostSummary] = {}
                for raw in raw_posts[:MAX_PIAZZA_FILTER_FEED_SCAN]:
                    try:
                        summary = self.normalizer.normalize_summary(
                            raw,
                            course_id,
                        )
                    except PiazzaNormalizationError:
                        skipped += 1
                        continue
                    normalized_posts.setdefault(summary.post_number, summary)
                feed_maps.append(normalized_posts)

            matching_post_numbers = set(feed_maps[0])
            for feed_map in feed_maps[1:]:
                matching_post_numbers.intersection_update(feed_map)

            matched_posts = [
                self._serialize_summary(summary)
                for post_number, summary in feed_maps[0].items()
                if post_number in matching_post_numbers
            ]
            return self._response(
                course_id=course_id,
                filters=list(canonical_filters),
                match_mode="all",
                folder_name=normalized_folder,
                upstream_request_count=len(canonical_filters),
                returned_count=min(len(matched_posts), max_results),
                skipped_post_count=skipped,
                truncated=(
                    scan_truncated or len(matched_posts) > max_results
                ),
                posts=matched_posts[:max_results],
            )

        cache_filters = ",".join(canonical_filters)
        cache_folder = normalized_folder or ""
        return await self._cached(
            (
                f"filtered-feed:{course_id}:{cache_filters}:"
                f"{cache_folder}:{max_results}"
            ),
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
    def _validate_filters(filters: object) -> tuple[str, ...]:
        valid_filters = set(PIAZZA_FILTER_ORDER)
        if (
            type(filters) is not list
            or not 1 <= len(filters) <= len(PIAZZA_FILTER_ORDER)
            or any(type(value) is not str for value in filters)
            or any(value not in valid_filters for value in filters)
            or len(set(filters)) != len(filters)
        ):
            raise ValueError(
                "filters must contain 1 to 3 unique values from updated, "
                "following, or folder"
            )
        return tuple(value for value in PIAZZA_FILTER_ORDER if value in filters)

    @staticmethod
    def _validate_filter_folder(
        filters: tuple[str, ...],
        folder_name: object,
    ) -> str | None:
        if "folder" not in filters:
            if folder_name is not None:
                raise ValueError(
                    "folder_name is only valid for the folder filter"
                )
            return None
        if type(folder_name) is not str or not folder_name.strip():
            raise ValueError(
                "folder_name is required for the folder filter"
            )
        normalized_folder = folder_name.strip()
        if len(normalized_folder) > 100:
            raise ValueError("folder_name cannot exceed 100 characters")
        return normalized_folder

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

    @staticmethod
    def _serialize_revision(revision: PiazzaRevision) -> dict[str, Any]:
        return {
            "sequence": revision.sequence,
            "subject": revision.subject,
            "body": revision.body,
            "created_at": revision.created_at,
            "truncated": revision.truncated,
        }

    @classmethod
    def _serialize_post_history(
        cls,
        history: PiazzaPostHistory,
    ) -> dict[str, Any]:
        return {
            "course_id": history.course_id,
            "post_number": history.post_number,
            "history_available": history.history_available,
            "ordering": history.ordering,
            "returned_count": len(history.revisions),
            "skipped_revision_count": history.skipped_revision_count,
            "truncated": history.truncated,
            "revisions": [
                cls._serialize_revision(revision)
                for revision in history.revisions
            ],
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
