from dataclasses import replace
from datetime import datetime
import re
from typing import Any

from bs4 import BeautifulSoup

from piazza_mcp.models.piazza import (
    MAX_PIAZZA_BODY_LENGTH,
    MAX_PIAZZA_FOLLOWUPS,
    MAX_PIAZZA_HISTORY_SCAN,
    MAX_PIAZZA_MESSAGE_LENGTH,
    MAX_PIAZZA_MESSAGE_COUNT,
    MAX_PIAZZA_MESSAGES_TOTAL_LENGTH,
    MAX_PIAZZA_NESTING_DEPTH,
    MAX_PIAZZA_REVISION_BODY_LENGTH,
    MAX_PIAZZA_REVISION_TOTAL_LENGTH,
    MAX_PIAZZA_SNIPPET_LENGTH,
    MAX_PIAZZA_SUBJECT_LENGTH,
    PiazzaCourse,
    PiazzaPostHistory,
    PiazzaMessage,
    PiazzaMessageKind,
    PiazzaPostKind,
    PiazzaPostSummary,
    PiazzaRevision,
    PiazzaThread,
)


_WHITESPACE = re.compile(r"\s+")


class PiazzaNormalizationError(ValueError):
    """Raised when a Piazza object lacks required usable fields."""


class PiazzaNormalizer:
    """Convert irregular Piazza dictionaries into bounded domain models."""

    def normalize_course(
        self,
        raw: dict[str, Any],
        configured_name: str,
    ) -> PiazzaCourse:
        course_id = self._optional_text(raw.get("nid"), 200)
        if course_id is None:
            raise PiazzaNormalizationError("Piazza course has no ID")
        return PiazzaCourse(
            course_id=course_id,
            name=configured_name,
            course_number=self._optional_text(raw.get("num"), 200),
            term=self._optional_text(raw.get("term"), 200),
            is_ta=raw.get("is_ta") if isinstance(raw.get("is_ta"), bool) else None,
        )

    def normalize_summary(
        self,
        raw: dict[str, Any],
        course_id: str,
    ) -> PiazzaPostSummary:
        post_number = self._post_number(raw)
        subject, subject_truncated = self._bounded_field(
            raw,
            "subject",
            MAX_PIAZZA_SUBJECT_LENGTH,
        )
        if not subject:
            subject = f"Piazza post {post_number}"
        snippet, snippet_truncated = self._first_bounded(
            (
                raw.get("content_snip"),
                raw.get("snippet"),
                raw.get("content"),
                self._history_value(raw, "content"),
            ),
            MAX_PIAZZA_SNIPPET_LENGTH,
        )
        return PiazzaPostSummary(
            post_number=post_number,
            course_id=course_id,
            kind=self._post_kind(raw.get("type")),
            subject=subject,
            snippet=snippet,
            folders=self._folders(raw),
            created_at=self._timestamp(raw.get("created")),
            updated_at=self._timestamp(raw.get("updated")),
            resolved=self._resolved(raw),
            source_url=self._source_url(course_id, post_number),
            truncated=subject_truncated or snippet_truncated,
        )

    def normalize_thread(
        self,
        raw: dict[str, Any],
        course_id: str,
    ) -> PiazzaThread:
        post_number = self._post_number(raw)
        subject, subject_truncated = self._bounded_field(
            raw,
            "subject",
            MAX_PIAZZA_SUBJECT_LENGTH,
        )
        if not subject:
            subject = f"Piazza post {post_number}"
        body, body_truncated = self._bounded_field(
            raw,
            "content",
            MAX_PIAZZA_BODY_LENGTH,
        )

        instructor_answer = None
        student_answer = None
        followups: list[PiazzaMessage] = []
        skipped = 0
        message_budget = [
            MAX_PIAZZA_MESSAGE_COUNT,
            MAX_PIAZZA_MESSAGES_TOTAL_LENGTH,
        ]
        children = raw.get("children")
        if not isinstance(children, list):
            children = []

        for child in children:
            if not isinstance(child, dict):
                skipped += 1
                continue
            message, child_skipped = self._normalize_message(
                child,
                depth=1,
                budget=message_budget,
            )
            skipped += child_skipped
            if message is None:
                skipped += 1
                continue
            if message.kind == "instructor_answer" and instructor_answer is None:
                instructor_answer = message
            elif message.kind == "student_answer" and student_answer is None:
                student_answer = message
            elif len(followups) < MAX_PIAZZA_FOLLOWUPS:
                followups.append(message)
            else:
                skipped += 1

        truncated = (
            subject_truncated
            or body_truncated
            or skipped > 0
            or any(message.truncated for message in followups)
            or (instructor_answer is not None and instructor_answer.truncated)
            or (student_answer is not None and student_answer.truncated)
        )
        return PiazzaThread(
            post_number=post_number,
            course_id=course_id,
            kind=self._post_kind(raw.get("type")),
            subject=subject,
            body=body,
            folders=self._folders(raw),
            created_at=self._timestamp(raw.get("created")),
            updated_at=self._timestamp(raw.get("updated")),
            resolved=self._resolved(raw),
            instructor_answer=instructor_answer,
            student_answer=student_answer,
            followups=tuple(followups),
            source_url=self._source_url(course_id, post_number),
            truncated=truncated,
            skipped_child_count=skipped,
        )

    def normalize_history(
        self,
        raw_post: dict[str, Any],
        course_id: str,
        post_number: int,
        max_revisions: int,
    ) -> PiazzaPostHistory:
        history = raw_post.get("history")
        if not isinstance(history, list) or not history:
            return PiazzaPostHistory(
                course_id=course_id,
                post_number=post_number,
                history_available=False,
                ordering="unavailable",
                revisions=(),
            )

        revisions: list[PiazzaRevision] = []
        skipped = 0
        for raw_revision in history[:MAX_PIAZZA_HISTORY_SCAN]:
            if not isinstance(raw_revision, dict):
                skipped += 1
                continue
            subject, subject_truncated = self._first_bounded(
                (raw_revision.get("subject"),),
                MAX_PIAZZA_SUBJECT_LENGTH,
            )
            body, body_truncated = self._first_bounded(
                (raw_revision.get("content"),),
                MAX_PIAZZA_REVISION_BODY_LENGTH,
            )
            if subject is None and body is None:
                skipped += 1
                continue
            revisions.append(
                PiazzaRevision(
                    sequence=0,
                    subject=subject,
                    body=body,
                    created_at=self._timestamp(raw_revision.get("created")),
                    truncated=subject_truncated or body_truncated,
                )
            )

        if revisions and all(
            revision.created_at is not None for revision in revisions
        ):
            ordering = "chronological"
            revisions.sort(
                key=lambda revision: self._parsed_timestamp(
                    revision.created_at
                )
            )
            selected = revisions[-max_revisions:]
        else:
            ordering = "piazza"
            selected = revisions[:max_revisions]

        truncated = (
            len(history) > MAX_PIAZZA_HISTORY_SCAN
            or len(revisions) > len(selected)
        )
        budgeted: list[PiazzaRevision] = []
        total_length = 0
        for revision in selected:
            revision_length = len(revision.subject or "") + len(
                revision.body or ""
            )
            if total_length + revision_length > MAX_PIAZZA_REVISION_TOTAL_LENGTH:
                truncated = True
                break
            budgeted.append(revision)
            total_length += revision_length

        sequenced = tuple(
            replace(revision, sequence=sequence)
            for sequence, revision in enumerate(budgeted, start=1)
        )
        return PiazzaPostHistory(
            course_id=course_id,
            post_number=post_number,
            history_available=True,
            ordering=ordering,
            revisions=sequenced,
            skipped_revision_count=skipped,
            truncated=(
                truncated or any(revision.truncated for revision in sequenced)
            ),
        )

    def _normalize_message(
        self,
        raw: dict[str, Any],
        depth: int,
        budget: list[int],
    ) -> tuple[PiazzaMessage | None, int]:
        if budget[0] <= 0 or budget[1] <= 0:
            return None, 1
        kind = self._message_kind(raw.get("type"))
        field_order = (
            ("subject", "content")
            if kind in {"followup", "feedback"}
            else ("content", "subject")
        )
        body_limit = min(MAX_PIAZZA_MESSAGE_LENGTH, budget[1])
        body, body_truncated = self._first_bounded(
            (
                raw.get(field_order[0]),
                raw.get(field_order[1]),
                self._history_value(raw, field_order[0]),
                self._history_value(raw, field_order[1]),
            ),
            body_limit,
        )
        if not body:
            return None, 0
        budget[0] -= 1
        budget[1] -= len(body)

        children: list[PiazzaMessage] = []
        skipped = 0
        raw_children = raw.get("children")
        if isinstance(raw_children, list):
            if depth >= MAX_PIAZZA_NESTING_DEPTH:
                skipped += len(raw_children)
            else:
                for child in raw_children:
                    if not isinstance(child, dict):
                        skipped += 1
                        continue
                    message, child_skipped = self._normalize_message(
                        child,
                        depth + 1,
                        budget,
                    )
                    skipped += child_skipped
                    if message is None:
                        skipped += 1
                    else:
                        children.append(message)

        return (
            PiazzaMessage(
                kind=kind,
                body=body,
                created_at=self._timestamp(raw.get("created")),
                updated_at=self._timestamp(raw.get("updated")),
                children=tuple(children),
                truncated=body_truncated or skipped > 0,
            ),
            skipped,
        )

    def _bounded_field(
        self,
        raw: dict[str, Any],
        field: str,
        limit: int,
    ) -> tuple[str | None, bool]:
        return self._first_bounded(
            (self._history_value(raw, field), raw.get(field)),
            limit,
        )

    def _first_bounded(
        self,
        values: tuple[Any, ...],
        limit: int,
    ) -> tuple[str | None, bool]:
        for value in values:
            text = self._plain_text(value)
            if text:
                return (text[:limit], len(text) > limit)
        return None, False

    @staticmethod
    def _history_value(raw: dict[str, Any], field: str) -> Any:
        history = raw.get("history")
        if isinstance(history, list):
            for revision in history:
                if isinstance(revision, dict) and revision.get(field):
                    return revision[field]
        return None

    @staticmethod
    def _post_number(raw: dict[str, Any]) -> int:
        value = raw.get("nr", raw.get("id"))
        if isinstance(value, bool):
            raise PiazzaNormalizationError("Piazza post has an invalid number")
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise PiazzaNormalizationError("Piazza post has no number") from None
        if number < 1:
            raise PiazzaNormalizationError("Piazza post has an invalid number")
        return number

    def _folders(self, raw: dict[str, Any]) -> tuple[str, ...]:
        folders = raw.get("folders")
        if not isinstance(folders, list):
            folders = raw.get("tags")
        if not isinstance(folders, list):
            return ()
        normalized = []
        for folder in folders[:20]:
            text = self._optional_text(folder, 100)
            if text:
                normalized.append(text)
        return tuple(normalized)

    @staticmethod
    def _post_kind(value: Any) -> PiazzaPostKind:
        return value if value in {"question", "note", "poll"} else "unknown"

    @staticmethod
    def _message_kind(value: Any) -> PiazzaMessageKind:
        return {
            "i_answer": "instructor_answer",
            "s_answer": "student_answer",
            "followup": "followup",
            "feedback": "feedback",
        }.get(value, "unknown")

    @staticmethod
    def _resolved(raw: dict[str, Any]) -> bool | None:
        value = raw.get("resolved")
        if isinstance(value, bool):
            return value
        status = raw.get("status")
        if status == "resolved":
            return True
        if status == "active":
            return False
        return None

    @staticmethod
    def _timestamp(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.isoformat().replace("+00:00", "Z")[:100]

    @staticmethod
    def _parsed_timestamp(value: str | None) -> datetime:
        if value is None:
            raise ValueError("timestamp is required for chronological ordering")
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _optional_text(self, value: Any, limit: int) -> str | None:
        text = self._plain_text(value)
        return text[:limit] if text else None

    @staticmethod
    def _plain_text(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        soup = BeautifulSoup(value, "html.parser")
        for element in soup(["script", "style"]):
            element.decompose()
        text = _WHITESPACE.sub(" ", soup.get_text(" ", strip=True)).strip()
        return text or None

    @staticmethod
    def _source_url(course_id: str, post_number: int) -> str:
        return f"https://piazza.com/class/{course_id}/post/{post_number}"
