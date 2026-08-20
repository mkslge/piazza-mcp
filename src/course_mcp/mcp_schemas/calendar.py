from course_mcp.models.calendar_item import (
    MAX_COURSE_HINT_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_ITEM_URL_LENGTH,
    MAX_LOCATION_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_UID_LENGTH,
)


_DATE_SCHEMA = {
    "type": "string",
    "format": "date",
    "pattern": r"^\d{4}-\d{2}-\d{2}$",
}
_DATE_TIME_SCHEMA = {
    "type": "string",
    "format": "date-time",
    "pattern": (
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
    ),
}
_DATE_VALUE_SCHEMA = {"anyOf": [_DATE_SCHEMA, _DATE_TIME_SCHEMA]}
_NULLABLE_DATE_VALUE_SCHEMA = {
    "anyOf": [
        _DATE_SCHEMA,
        _DATE_TIME_SCHEMA,
        {"type": "null"},
    ]
}

_CALENDAR_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "uid": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_UID_LENGTH,
        },
        "title": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_TITLE_LENGTH,
        },
        "starts_at": _DATE_VALUE_SCHEMA,
        "ends_at": _NULLABLE_DATE_VALUE_SCHEMA,
        "all_day": {"type": "boolean"},
        "description": {
            "anyOf": [
                {"type": "string", "maxLength": MAX_DESCRIPTION_LENGTH},
                {"type": "null"},
            ]
        },
        "location": {
            "anyOf": [
                {"type": "string", "maxLength": MAX_LOCATION_LENGTH},
                {"type": "null"},
            ]
        },
        "item_url": {
            "anyOf": [
                {
                    "type": "string",
                    "format": "uri",
                    "maxLength": MAX_ITEM_URL_LENGTH,
                },
                {"type": "null"},
            ]
        },
        "course_hint": {
            "anyOf": [
                {"type": "string", "maxLength": MAX_COURSE_HINT_LENGTH},
                {"type": "null"},
            ]
        },
        "item_kind": {
            "type": "string",
            "enum": ["assignment", "event", "unknown"],
        },
    },
    "required": [
        "uid",
        "title",
        "starts_at",
        "ends_at",
        "all_day",
        "description",
        "location",
        "item_url",
        "course_hint",
        "item_kind",
    ],
    "additionalProperties": False,
}

GET_UPCOMING_WORK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "enum": ["canvas_ical", "local_ical_snapshot"],
        },
        "fetched_at": {"type": "string", "format": "date-time"},
        "stale": {"type": "boolean"},
        "skipped_event_count": {"type": "integer", "minimum": 0},
        "returned_count": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
        },
        "truncated": {"type": "boolean"},
        "limitations": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
        "items": {
            "type": "array",
            "items": _CALENDAR_ITEM_SCHEMA,
            "maxItems": 100,
        },
    },
    "required": [
        "source",
        "fetched_at",
        "stale",
        "skipped_event_count",
        "returned_count",
        "truncated",
        "limitations",
        "items",
    ],
    "additionalProperties": False,
}
