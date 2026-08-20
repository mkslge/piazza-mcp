from typing import Any

from course_mcp.services.file import get_file_service

from .service import CourseService


_course_service: CourseService | None = None


def get_course_service() -> CourseService:
    """Return the lazily initialized course service."""
    global _course_service

    if _course_service is None:
        _course_service = CourseService(get_file_service())
    return _course_service


def get_courses() -> list[str]:
    """Return courses through the configured course service."""
    return get_course_service().get_courses()


def get_files(course_title: str) -> list[str]:
    """Return course files through the configured course service."""
    return get_course_service().get_files(course_title)


def search_file(
    course_title: str,
    file_path: str,
    keyword: str,
    context_lines: int = 3,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search a course file through the configured course service."""
    return get_course_service().search_file(
        course_title,
        file_path,
        keyword,
        context_lines,
        max_results,
    )


def search_course(
    course_title: str,
    keyword: str,
    context_lines: int = 3,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search a course recursively through the configured course service."""
    return get_course_service().search_course(
        course_title,
        keyword,
        context_lines,
        max_results,
    )
