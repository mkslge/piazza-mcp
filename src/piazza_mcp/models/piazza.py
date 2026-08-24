from dataclasses import dataclass
from typing import Literal


PiazzaPostKind = Literal["question", "note", "poll", "unknown"]
PiazzaMessageKind = Literal[
    "instructor_answer",
    "student_answer",
    "followup",
    "feedback",
    "unknown",
]
PiazzaHistoryOrdering = Literal["chronological", "piazza", "unavailable"]

MAX_PIAZZA_SUBJECT_LENGTH = 500
MAX_PIAZZA_SNIPPET_LENGTH = 1_000
MAX_PIAZZA_BODY_LENGTH = 20_000
MAX_PIAZZA_MESSAGE_LENGTH = 4_000
MAX_PIAZZA_FOLLOWUPS = 50
MAX_PIAZZA_NESTING_DEPTH = 3
MAX_PIAZZA_MESSAGE_COUNT = 50
MAX_PIAZZA_MESSAGES_TOTAL_LENGTH = 75_000
MAX_PIAZZA_REVISIONS = 20
MAX_PIAZZA_HISTORY_SCAN = 100
MAX_PIAZZA_REVISION_BODY_LENGTH = 10_000
MAX_PIAZZA_REVISION_TOTAL_LENGTH = 40_000


@dataclass(frozen=True)
class PiazzaCourse:
    course_id: str
    name: str
    course_number: str | None = None
    term: str | None = None
    is_ta: bool | None = None


@dataclass(frozen=True)
class PiazzaPostSummary:
    post_number: int
    course_id: str
    kind: PiazzaPostKind
    subject: str
    snippet: str | None
    folders: tuple[str, ...]
    created_at: str | None
    updated_at: str | None
    resolved: bool | None
    source_url: str
    truncated: bool = False


@dataclass(frozen=True)
class PiazzaMessage:
    kind: PiazzaMessageKind
    body: str
    created_at: str | None
    updated_at: str | None
    children: tuple["PiazzaMessage", ...] = ()
    truncated: bool = False


@dataclass(frozen=True)
class PiazzaThread:
    post_number: int
    course_id: str
    kind: PiazzaPostKind
    subject: str
    body: str | None
    folders: tuple[str, ...]
    created_at: str | None
    updated_at: str | None
    resolved: bool | None
    instructor_answer: PiazzaMessage | None
    student_answer: PiazzaMessage | None
    followups: tuple[PiazzaMessage, ...]
    source_url: str
    truncated: bool = False
    skipped_child_count: int = 0


@dataclass(frozen=True)
class PiazzaRevision:
    sequence: int
    subject: str | None
    body: str | None
    created_at: str | None
    truncated: bool


@dataclass(frozen=True)
class PiazzaPostHistory:
    course_id: str
    post_number: int
    history_available: bool
    ordering: PiazzaHistoryOrdering
    revisions: tuple[PiazzaRevision, ...]
    skipped_revision_count: int = 0
    truncated: bool = False
