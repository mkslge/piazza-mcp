from piazza_mcp.models.piazza import (
    MAX_PIAZZA_BODY_LENGTH,
    MAX_PIAZZA_FOLLOWUPS,
    MAX_PIAZZA_MESSAGE_LENGTH,
    MAX_PIAZZA_SNIPPET_LENGTH,
    MAX_PIAZZA_SUBJECT_LENGTH,
)


_NULLABLE_TEXT = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_NULLABLE_TIMESTAMP = {
    "anyOf": [
        {"type": "string", "format": "date-time", "maxLength": 100},
        {"type": "null"},
    ]
}
_NULLABLE_BOOLEAN = {
    "anyOf": [{"type": "boolean"}, {"type": "null"}]
}
_POST_KIND = {
    "type": "string",
    "enum": ["question", "note", "poll", "unknown"],
}
_MESSAGE_KIND = {
    "type": "string",
    "enum": [
        "instructor_answer",
        "student_answer",
        "followup",
        "feedback",
        "unknown",
    ],
}


def _metadata_properties() -> dict:
    return {
        "source": {"type": "string", "enum": ["piazza"]},
        "content_trust": {
            "type": "string",
            "enum": ["untrusted_user_generated"],
        },
        "fetched_at": {"type": "string", "format": "date-time"},
        "stale": {"type": "boolean"},
        "limitations": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
    }


_METADATA_REQUIRED = [
    "source",
    "content_trust",
    "fetched_at",
    "stale",
    "limitations",
]

_COURSE_SCHEMA = {
    "type": "object",
    "properties": {
        "course_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "name": {"type": "string", "minLength": 1, "maxLength": 200},
        "course_number": _NULLABLE_TEXT,
        "term": _NULLABLE_TEXT,
        "is_ta": _NULLABLE_BOOLEAN,
    },
    "required": ["course_id", "name", "course_number", "term", "is_ta"],
    "additionalProperties": False,
}

_POST_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "post_number": {"type": "integer", "minimum": 1},
        "course_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "kind": _POST_KIND,
        "subject": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_PIAZZA_SUBJECT_LENGTH,
        },
        "snippet": {
            "anyOf": [
                {"type": "string", "maxLength": MAX_PIAZZA_SNIPPET_LENGTH},
                {"type": "null"},
            ]
        },
        "folders": {
            "type": "array",
            "items": {"type": "string", "maxLength": 100},
            "maxItems": 20,
        },
        "created_at": _NULLABLE_TIMESTAMP,
        "updated_at": _NULLABLE_TIMESTAMP,
        "resolved": _NULLABLE_BOOLEAN,
        "source_url": {"type": "string", "format": "uri", "maxLength": 500},
        "truncated": {"type": "boolean"},
    },
    "required": [
        "post_number",
        "course_id",
        "kind",
        "subject",
        "snippet",
        "folders",
        "created_at",
        "updated_at",
        "resolved",
        "source_url",
        "truncated",
    ],
    "additionalProperties": False,
}


def _message_schema(depth: int = 0) -> dict:
    children = {
        "type": "array",
        "items": (
            _message_schema(depth + 1)
            if depth < 2
            else {"type": "object", "maxProperties": 0}
        ),
        "maxItems": MAX_PIAZZA_FOLLOWUPS,
    }
    return {
        "type": "object",
        "properties": {
            "kind": _MESSAGE_KIND,
            "body": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_PIAZZA_MESSAGE_LENGTH,
            },
            "created_at": _NULLABLE_TIMESTAMP,
            "updated_at": _NULLABLE_TIMESTAMP,
            "children": children,
            "truncated": {"type": "boolean"},
        },
        "required": [
            "kind",
            "body",
            "created_at",
            "updated_at",
            "children",
            "truncated",
        ],
        "additionalProperties": False,
    }


_MESSAGE_SCHEMA = _message_schema()
_NULLABLE_MESSAGE = {"anyOf": [_MESSAGE_SCHEMA, {"type": "null"}]}

_THREAD_SCHEMA = {
    "type": "object",
    "properties": {
        "post_number": {"type": "integer", "minimum": 1},
        "course_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "kind": _POST_KIND,
        "subject": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_PIAZZA_SUBJECT_LENGTH,
        },
        "body": {
            "anyOf": [
                {"type": "string", "maxLength": MAX_PIAZZA_BODY_LENGTH},
                {"type": "null"},
            ]
        },
        "folders": {
            "type": "array",
            "items": {"type": "string", "maxLength": 100},
            "maxItems": 20,
        },
        "created_at": _NULLABLE_TIMESTAMP,
        "updated_at": _NULLABLE_TIMESTAMP,
        "resolved": _NULLABLE_BOOLEAN,
        "instructor_answer": _NULLABLE_MESSAGE,
        "student_answer": _NULLABLE_MESSAGE,
        "followups": {
            "type": "array",
            "items": _MESSAGE_SCHEMA,
            "maxItems": MAX_PIAZZA_FOLLOWUPS,
        },
        "source_url": {"type": "string", "format": "uri", "maxLength": 500},
        "truncated": {"type": "boolean"},
        "skipped_child_count": {"type": "integer", "minimum": 0},
    },
    "required": [
        "post_number",
        "course_id",
        "kind",
        "subject",
        "body",
        "folders",
        "created_at",
        "updated_at",
        "resolved",
        "instructor_answer",
        "student_answer",
        "followups",
        "source_url",
        "truncated",
        "skipped_child_count",
    ],
    "additionalProperties": False,
}


LIST_PIAZZA_COURSES_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        **_metadata_properties(),
        "returned_count": {"type": "integer", "minimum": 1},
        "courses": {"type": "array", "items": _COURSE_SCHEMA, "minItems": 1},
    },
    "required": [*_METADATA_REQUIRED, "returned_count", "courses"],
    "additionalProperties": False,
}


def _post_list_output_schema(*, include_query: bool) -> dict:
    properties = {
        **_metadata_properties(),
        "course_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "returned_count": {"type": "integer", "minimum": 0, "maximum": 25},
        "skipped_post_count": {"type": "integer", "minimum": 0},
        "truncated": {"type": "boolean"},
        "posts": {
            "type": "array",
            "items": _POST_SUMMARY_SCHEMA,
            "maxItems": 25,
        },
    }
    required = [
        *_METADATA_REQUIRED,
        "course_id",
        "returned_count",
        "skipped_post_count",
        "truncated",
        "posts",
    ]
    if include_query:
        properties["query"] = {
            "type": "string",
            "minLength": 1,
            "maxLength": 200,
        }
        required.insert(required.index("returned_count"), "query")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


LIST_PIAZZA_POSTS_OUTPUT_SCHEMA = _post_list_output_schema(include_query=False)
SEARCH_PIAZZA_POSTS_OUTPUT_SCHEMA = _post_list_output_schema(include_query=True)

LIST_PIAZZA_FILTERED_POSTS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        **_metadata_properties(),
        "course_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "filters": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["updated", "following", "folder"],
            },
            "minItems": 1,
            "maxItems": 3,
            "uniqueItems": True,
        },
        "match_mode": {"type": "string", "enum": ["all"]},
        "folder_name": {
            "anyOf": [
                {"type": "string", "minLength": 1, "maxLength": 100},
                {"type": "null"},
            ]
        },
        "upstream_request_count": {
            "type": "integer",
            "minimum": 1,
            "maximum": 3,
        },
        "returned_count": {"type": "integer", "minimum": 0, "maximum": 25},
        "skipped_post_count": {"type": "integer", "minimum": 0},
        "truncated": {"type": "boolean"},
        "posts": {
            "type": "array",
            "items": _POST_SUMMARY_SCHEMA,
            "maxItems": 25,
        },
    },
    "required": [
        *_METADATA_REQUIRED,
        "course_id",
        "filters",
        "match_mode",
        "folder_name",
        "upstream_request_count",
        "returned_count",
        "skipped_post_count",
        "truncated",
        "posts",
    ],
    "additionalProperties": False,
}

GET_PIAZZA_POST_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {**_metadata_properties(), "thread": _THREAD_SCHEMA},
    "required": [*_METADATA_REQUIRED, "thread"],
    "additionalProperties": False,
}
