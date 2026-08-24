from dataclasses import dataclass
import json
import os
import re
from types import MappingProxyType
from typing import Mapping

from .env import load_project_env


COURSE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class PiazzaConfig:
    """Validated credentials and course allowlist for Piazza access."""

    email: str
    password: str
    courses: Mapping[str, str]
    request_timeout_seconds: float = 10.0


def get_piazza_config() -> PiazzaConfig:
    """Load Piazza configuration only when a Piazza tool is requested."""
    load_project_env()

    email = os.environ.get("PIAZZA_EMAIL", "").strip()
    password = os.environ.get("PIAZZA_PASSWORD", "")
    raw_courses = os.environ.get("PIAZZA_COURSES", "").strip()

    if not email:
        raise RuntimeError("Missing PIAZZA_EMAIL in .env or environment")
    if not password:
        raise RuntimeError("Missing PIAZZA_PASSWORD in .env or environment")
    if not raw_courses:
        raise RuntimeError("Missing PIAZZA_COURSES in .env or environment")

    def reject_duplicate_ids(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError(
                    "PIAZZA_COURSES contains a duplicate course ID"
                )
            result[key] = value
        return result

    try:
        parsed_courses = json.loads(
            raw_courses,
            object_pairs_hook=reject_duplicate_ids,
        )
    except json.JSONDecodeError:
        raise RuntimeError("PIAZZA_COURSES must be a JSON object") from None

    if not isinstance(parsed_courses, dict) or not parsed_courses:
        raise RuntimeError("PIAZZA_COURSES must be a non-empty JSON object")

    courses: dict[str, str] = {}
    for course_id, name in parsed_courses.items():
        if not isinstance(course_id, str) or not course_id.strip():
            raise RuntimeError("PIAZZA_COURSES IDs must be non-empty strings")
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError("PIAZZA_COURSES names must be non-empty strings")
        normalized_id = course_id.strip()
        normalized_name = name.strip()
        if len(normalized_id) > 200:
            raise RuntimeError("PIAZZA_COURSES IDs cannot exceed 200 characters")
        if not COURSE_ID_PATTERN.fullmatch(normalized_id):
            raise RuntimeError(
                "PIAZZA_COURSES IDs may contain only letters, numbers, "
                "underscores, and hyphens"
            )
        if len(normalized_name) > 200:
            raise RuntimeError(
                "PIAZZA_COURSES names cannot exceed 200 characters"
            )
        courses[normalized_id] = normalized_name

    return PiazzaConfig(
        email=email,
        password=password,
        courses=MappingProxyType(courses),
    )
