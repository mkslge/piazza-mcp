import pytest

from piazza_mcp.models.piazza import (
    MAX_PIAZZA_BODY_LENGTH,
    MAX_PIAZZA_MESSAGE_LENGTH,
)
from piazza_mcp.services.piazza.normalizer import (
    PiazzaNormalizationError,
    PiazzaNormalizer,
)


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


def test_normalizes_summary_from_feed_shape_and_strips_html():
    summary = PiazzaNormalizer().normalize_summary(
        {
            "id": "42",
            "type": "question",
            "subject": "<b>Homework 1</b>",
            "content_snip": "<p>How does recursion work?</p><script>bad()</script>",
            "folders": ["hw1"],
            "created": "2026-08-19T10:00:00Z",
            "updated": "2026-08-19T11:00:00Z",
            "status": "active",
        },
        "abc123",
    )

    assert summary.post_number == 42
    assert summary.subject == "Homework 1"
    assert summary.snippet == "How does recursion work?"
    assert summary.source_url.endswith("/abc123/post/42")
    assert summary.resolved is False


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


@pytest.mark.parametrize("value", [None, 0, -1, True, "not-a-number"])
def test_normalizer_rejects_invalid_post_numbers(value):
    with pytest.raises(PiazzaNormalizationError):
        PiazzaNormalizer().normalize_summary({"id": value}, "abc123")
