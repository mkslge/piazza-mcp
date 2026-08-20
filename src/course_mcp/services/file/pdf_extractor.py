from pathlib import Path

from pypdf import PdfReader


class PdfExtractionError(ValueError):
    """Report that a PDF could not provide searchable text."""


class PdfTextExtractor:
    def extract_pages(self, path: Path) -> list[tuple[int, list[str]]]:
        """Extract each PDF page into one-based page numbers and text lines."""
        try:
            reader = PdfReader(path)
        except Exception as exc:
            raise PdfExtractionError(f"Unable to read PDF: {path.name}") from exc

        if reader.is_encrypted:
            raise PdfExtractionError(f"PDF is encrypted: {path.name}")

        try:
            pages = [
                (page_number, (page.extract_text() or "").splitlines())
                for page_number, page in enumerate(reader.pages, start=1)
            ]
        except Exception as exc:
            raise PdfExtractionError(
                f"Unable to extract PDF text: {path.name}"
            ) from exc

        if not any(line.strip() for _, lines in pages for line in lines):
            raise PdfExtractionError(f"PDF has no extractable text: {path.name}")

        return pages
