from types import SimpleNamespace

import pytest

import course_mcp.services.file.pdf_extractor as extractor_module
from course_mcp.services.file import (
    PdfExtractionError,
    PdfTextExtractor,
)


class FakePdfPage:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error

    def extract_text(self):
        if self.error is not None:
            raise self.error
        return self.text


def test_extract_pages_numbers_pages_and_splits_lines(monkeypatch, tmp_path):
    path = tmp_path / "lecture.pdf"
    pages = [FakePdfPage("first\nsecond"), FakePdfPage("third")]
    monkeypatch.setattr(
        extractor_module,
        "PdfReader",
        lambda reader_path: SimpleNamespace(is_encrypted=False, pages=pages),
    )

    result = PdfTextExtractor().extract_pages(path)

    assert result == [(1, ["first", "second"]), (2, ["third"])]


def test_extract_pages_rejects_encrypted_pdfs(monkeypatch, tmp_path):
    path = tmp_path / "lecture.pdf"
    monkeypatch.setattr(
        extractor_module,
        "PdfReader",
        lambda reader_path: SimpleNamespace(is_encrypted=True, pages=[]),
    )

    with pytest.raises(PdfExtractionError, match="PDF is encrypted: lecture.pdf"):
        PdfTextExtractor().extract_pages(path)

    assert issubclass(PdfExtractionError, ValueError)


def test_extract_pages_wraps_reader_initialization_failures(monkeypatch, tmp_path):
    path = tmp_path / "corrupt.pdf"

    def fail_to_read(reader_path):
        raise RuntimeError("corrupt")

    monkeypatch.setattr(extractor_module, "PdfReader", fail_to_read)

    with pytest.raises(PdfExtractionError, match="Unable to read PDF: corrupt.pdf"):
        PdfTextExtractor().extract_pages(path)


def test_extract_pages_wraps_page_extraction_failures(monkeypatch, tmp_path):
    path = tmp_path / "lecture.pdf"
    monkeypatch.setattr(
        extractor_module,
        "PdfReader",
        lambda reader_path: SimpleNamespace(
            is_encrypted=False,
            pages=[FakePdfPage(error=RuntimeError("failed"))],
        ),
    )

    with pytest.raises(
        PdfExtractionError,
        match="Unable to extract PDF text: lecture.pdf",
    ):
        PdfTextExtractor().extract_pages(path)


def test_extract_pages_rejects_pdfs_without_searchable_text(monkeypatch, tmp_path):
    path = tmp_path / "empty.pdf"
    monkeypatch.setattr(
        extractor_module,
        "PdfReader",
        lambda reader_path: SimpleNamespace(
            is_encrypted=False,
            pages=[FakePdfPage(None), FakePdfPage(" \n\t")],
        ),
    )

    with pytest.raises(
        PdfExtractionError,
        match="PDF has no extractable text: empty.pdf",
    ):
        PdfTextExtractor().extract_pages(path)
