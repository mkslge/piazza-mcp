from copy import deepcopy

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pytest

from piazza_mcp.mcp_schemas import GET_PIAZZA_POST_HISTORY_OUTPUT_SCHEMA


def metadata():
    return {
        "source": "piazza",
        "content_trust": "untrusted_user_generated",
        "fetched_at": "2026-08-20T15:00:00Z",
        "stale": False,
        "limitations": ["unofficial_internal_api"],
    }


def revision(sequence):
    return {
        "sequence": sequence,
        "subject": "Exam location",
        "body": "The exam is in the lecture hall.",
        "created_at": "2026-08-20T14:00:00Z",
        "truncated": False,
    }


def available_history():
    return {
        **metadata(),
        "course_id": "abc123",
        "post_number": 42,
        "history_available": True,
        "ordering": "chronological",
        "returned_count": 1,
        "skipped_revision_count": 0,
        "truncated": False,
        "revisions": [revision(1)],
    }


def unavailable_history():
    return {
        **metadata(),
        "course_id": "abc123",
        "post_number": 42,
        "history_available": False,
        "ordering": "unavailable",
        "returned_count": 0,
        "skipped_revision_count": 0,
        "truncated": False,
        "revisions": [],
    }


def validate(value):
    Draft202012Validator(
        GET_PIAZZA_POST_HISTORY_OUTPUT_SCHEMA,
        format_checker=FormatChecker(),
    ).validate(value)


# test-quality: allow TQ002 - schema validation succeeds by not raising
def test_history_schema_accepts_available_and_unavailable_responses():
    validate(available_history())
    validate(unavailable_history())


def test_history_schema_rejects_more_than_twenty_revisions():
    value = available_history()
    value["revisions"] = [
        revision((index % 20) + 1) for index in range(21)
    ]
    value["returned_count"] = 20

    with pytest.raises(ValidationError):
        validate(value)


def test_history_schema_rejects_unknown_ordering():
    value = available_history()
    value["ordering"] = "newest-first"

    with pytest.raises(ValidationError):
        validate(value)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("ordering", "piazza"),
        ("returned_count", 1),
        ("revisions", [revision(1)]),
    ],
)
def test_history_schema_enforces_unavailable_invariants(field, invalid_value):
    value = deepcopy(unavailable_history())
    value[field] = invalid_value

    with pytest.raises(ValidationError):
        validate(value)


def test_history_schema_rejects_revision_without_subject_or_body():
    value = available_history()
    value["revisions"][0]["subject"] = None
    value["revisions"][0]["body"] = None

    with pytest.raises(ValidationError):
        validate(value)
