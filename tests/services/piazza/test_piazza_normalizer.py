from dataclasses import asdict

import pytest

from piazza_mcp.models.piazza import (
    MAX_PIAZZA_BODY_LENGTH,
    MAX_PIAZZA_HISTORY_SCAN,
    MAX_PIAZZA_MESSAGE_LENGTH,
    MAX_PIAZZA_REVISION_BODY_LENGTH,
    MAX_PIAZZA_REVISION_TOTAL_LENGTH,
    MAX_PIAZZA_SUBJECT_LENGTH,
)
from piazza_mcp.services.piazza.normalizer import (
    PiazzaNormalizationError,
    PiazzaNormalizer,
)
from tests.support import assert_sensitive_value_absent


def test_normalizes_course_with_configured_name():
    course = PiazzaNormalizer().normalize_course(
        {
            "nid": "abc123",
            "name": "Untrusted upstream name",
            "num": "CMSC 132",
            "term": "Fall 2026",
            "is_ta": False,
        },
        "Local CMSC 132",
    )

    assert course.course_id == "abc123"
    assert course.name == "Local CMSC 132"
    assert course.course_number == "CMSC 132"
    assert course.is_ta is False


def test_normalizes_thread_answers_followups_and_nested_feedback():
    thread = PiazzaNormalizer().normalize_thread(
        {
            "nr": 42,
            "type": "question",
            "history": [
                {"subject": "Question", "content": "<p>Main body</p>"}
            ],
            "children": [
                {"type": "i_answer", "content": "Instructor response"},
                {"type": "s_answer", "content": "Student response"},
                {
                    "type": "followup",
                    "subject": "Follow-up text",
                    "children": [
                        {"type": "feedback", "subject": "Nested reply"}
                    ],
                },
            ],
        },
        "abc123",
    )

    assert thread.subject == "Question"
    assert thread.body == "Main body"
    assert thread.instructor_answer.body == "Instructor response"
    assert thread.student_answer.body == "Student response"
    assert thread.followups[0].body == "Follow-up text"
    assert thread.followups[0].children[0].body == "Nested reply"


def test_reply_without_history_preserves_subject_text():
    thread = PiazzaNormalizer().normalize_thread(
        {
            "nr": 7,
            "subject": "Question",
            "children": [{"type": "followup", "subject": "Still here"}],
        },
        "abc123",
    )

    assert thread.followups[0].body == "Still here"


def test_normalizer_bounds_text_and_reports_truncation():
    thread = PiazzaNormalizer().normalize_thread(
        {
            "nr": 3,
            "subject": "Question",
            "content": "x" * (MAX_PIAZZA_BODY_LENGTH + 1),
            "children": [
                {
                    "type": "followup",
                    "subject": "y" * (MAX_PIAZZA_MESSAGE_LENGTH + 1),
                }
            ],
        },
        "abc123",
    )

    assert len(thread.body) == MAX_PIAZZA_BODY_LENGTH
    assert len(thread.followups[0].body) == MAX_PIAZZA_MESSAGE_LENGTH
    assert thread.truncated is True


def test_history_sanitizes_fields_and_sorts_timestamps():
    history = PiazzaNormalizer().normalize_history(
        {
            "history": [
                {
                    "subject": "<b>Later</b><script>ignore me</script>",
                    "content": "<p>Revised <em>body</em></p>",
                    "created": "2026-08-20T10:00:00-05:00",
                },
                {
                    "subject": "Earlier",
                    "content": "Original body",
                    "created": "2026-08-20T14:00:00Z",
                },
            ]
        },
        "abc123",
        42,
        10,
    )

    assert history.ordering == "chronological"
    assert [revision.subject for revision in history.revisions] == [
        "Earlier",
        "Later",
    ]
    assert history.revisions[1].body == "Revised body"
    assert [revision.sequence for revision in history.revisions] == [1, 2]


def test_history_does_not_leak_identity_or_audit_fields():
    sentinel = "SENSITIVE_HISTORY_IDENTITY_SENTINEL_7D4A"
    history = PiazzaNormalizer().normalize_history(
        {
            "history": [
                {
                    "subject": "Visible subject",
                    "content": "Visible body",
                    "uid": sentinel,
                    "name": sentinel,
                    "anon": sentinel,
                    "change_log": {"private": sentinel},
                    "unknown": sentinel,
                }
            ]
        },
        "abc123",
        42,
        10,
    )

    assert_sensitive_value_absent(asdict(history), sentinel)
    assert set(asdict(history.revisions[0])) == {
        "sequence",
        "subject",
        "body",
        "created_at",
        "truncated",
    }


def test_history_preserves_piazza_order_when_a_timestamp_is_invalid():
    history = PiazzaNormalizer().normalize_history(
        {
            "history": [
                {"subject": "First", "created": "not-a-timestamp"},
                {"subject": "Second", "created": "2026-08-20T14:00:00Z"},
                {"subject": "Third", "created": "2026-08-20T15:00:00Z"},
            ]
        },
        "abc123",
        42,
        2,
    )

    assert history.ordering == "piazza"
    assert [revision.subject for revision in history.revisions] == [
        "First",
        "Second",
    ]
    assert history.revisions[0].created_at is None
    assert history.truncated is True


def test_history_keeps_most_recent_chronological_revisions():
    history = PiazzaNormalizer().normalize_history(
        {
            "history": [
                {"subject": "Newest", "created": "2026-08-20T16:00:00Z"},
                {"subject": "Oldest", "created": "2026-08-20T14:00:00Z"},
                {"subject": "Middle", "created": "2026-08-20T15:00:00Z"},
            ]
        },
        "abc123",
        42,
        2,
    )

    assert [revision.subject for revision in history.revisions] == [
        "Middle",
        "Newest",
    ]
    assert [revision.sequence for revision in history.revisions] == [1, 2]
    assert history.truncated is True


@pytest.mark.parametrize(
    "raw_post",
    [
        {},
        {"history": None},
        {"history": {}},
        {"history": []},
    ],
)
def test_history_returns_unavailable_for_missing_or_unusable_history(raw_post):
    history = PiazzaNormalizer().normalize_history(
        raw_post,
        "abc123",
        42,
        10,
    )

    assert history.history_available is False
    assert history.ordering == "unavailable"
    assert history.revisions == ()
    assert history.skipped_revision_count == 0
    assert history.truncated is False


def test_history_skips_malformed_and_empty_entries():
    history = PiazzaNormalizer().normalize_history(
        {
            "history": [
                None,
                {},
                {"subject": "<script>empty</script>"},
                {"content": "<p>Usable</p>"},
            ]
        },
        "abc123",
        42,
        10,
    )

    assert history.history_available is True
    assert history.skipped_revision_count == 3
    assert [revision.body for revision in history.revisions] == ["Usable"]
    assert history.truncated is False


def test_history_caps_scan_count_before_normalizing_entries():
    raw_history = [
        {"subject": f"Revision {index}"}
        for index in range(1, MAX_PIAZZA_HISTORY_SCAN + 1)
    ]
    raw_history.append({})

    history = PiazzaNormalizer().normalize_history(
        {"history": raw_history},
        "abc123",
        42,
        20,
    )

    assert history.truncated is True
    assert history.skipped_revision_count == 0
    assert history.revisions[0].subject == "Revision 1"
    assert history.revisions[-1].subject == "Revision 20"


def test_history_caps_fields_and_aggregate_text():
    history = PiazzaNormalizer().normalize_history(
        {
            "history": [
                {
                    "subject": "s" * (MAX_PIAZZA_SUBJECT_LENGTH + 1),
                    "content": "x" * (MAX_PIAZZA_REVISION_BODY_LENGTH + 1),
                },
                *(
                    {"content": "x" * MAX_PIAZZA_REVISION_BODY_LENGTH}
                    for _ in range(4)
                ),
            ]
        },
        "abc123",
        42,
        20,
    )

    assert len(history.revisions[0].subject) == MAX_PIAZZA_SUBJECT_LENGTH
    assert len(history.revisions[0].body) == MAX_PIAZZA_REVISION_BODY_LENGTH
    assert history.revisions[0].truncated is True
    assert sum(
        len(revision.subject or "") + len(revision.body or "")
        for revision in history.revisions
    ) <= MAX_PIAZZA_REVISION_TOTAL_LENGTH
    assert len(history.revisions) == 3
    assert history.truncated is True


@pytest.mark.parametrize("value", [None, 0, -1, True, "not-a-number"])
def test_normalizer_rejects_invalid_post_numbers(value):
    with pytest.raises(PiazzaNormalizationError):
        PiazzaNormalizer().normalize_summary({"id": value}, "abc123")
