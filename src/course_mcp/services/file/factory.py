from typing import Any

from course_mcp.config import get_root_dir

from .pdf_extractor import PdfTextExtractor
from .service import FileService


_file_service: FileService | None = None


def get_file_service() -> FileService:
    """Return the lazily initialized configured file service."""
    global _file_service

    if _file_service is None:
        _file_service = FileService(get_root_dir(), PdfTextExtractor())
    return _file_service


def get_contents(
    relative_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    """Read text through the configured file service."""
    return get_file_service().get_contents(relative_path, start_line, end_line)


def list_files(relative_path: str = "") -> list[str]:
    """List files through the configured file service."""
    return get_file_service().list_files(relative_path)


def list_dirs(relative_path: str = "") -> list[str]:
    """List directories through the configured file service."""
    return get_file_service().list_dirs(relative_path)


def search_file(
    course_title: str,
    file_path: str,
    keyword: str,
    context_lines: int = 3,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search a course file through the configured file service."""
    return get_file_service().search_file(
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
    """Search a course recursively through the configured file service."""
    return get_file_service().search_course(
        course_title,
        keyword,
        context_lines,
        max_results,
    )
