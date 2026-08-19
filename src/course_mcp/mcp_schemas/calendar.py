_NULLABLE_STRING_SCHEMA = {
    "anyOf": [
        {"type": "string"},
        {"type": "null"},
    ]
}

_CALENDAR_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "uid": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "starts_at": {"type": "string", "minLength": 1},
        "ends_at": _NULLABLE_STRING_SCHEMA,
        "all_day": {"type": "boolean"},
        "description": {
            "anyOf": [
                {"type": "string", "maxLength": 1000},
                {"type": "null"},
            ]
        },
        "location": _NULLABLE_STRING_SCHEMA,
        "item_url": _NULLABLE_STRING_SCHEMA,
        "course_hint": _NULLABLE_STRING_SCHEMA,
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
        "returned_count": {"type": "integer", "minimum": 0},
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
        "returned_count",
        "truncated",
        "limitations",
        "items",
    ],
    "additionalProperties": False,
}
