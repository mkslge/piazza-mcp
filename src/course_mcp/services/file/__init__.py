"""Public API for file services."""

from .factory import (
    get_contents,
    get_file_service,
    list_dirs,
    list_files,
    search_course,
    search_file,
)
from .pdf_extractor import PdfExtractionError, PdfTextExtractor
from .service import FileService


__all__ = [
    "FileService",
    "PdfExtractionError",
    "PdfTextExtractor",
    "get_contents",
    "get_file_service",
    "list_dirs",
    "list_files",
    "search_course",
    "search_file",
]
