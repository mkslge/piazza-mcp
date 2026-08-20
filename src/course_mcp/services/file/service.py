import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .pdf_extractor import PdfTextExtractor

COURSE_SEARCH_MAX_DEPTH = 5
COURSE_SEARCH_EXCLUDED_DIRS = frozenset(
    {"venv", "__pycache__", "node_modules", "dist", "build"}
)


class FileService:
    def __init__(
        self,
        root_dir: Path,
        pdf_extractor: PdfTextExtractor | None = None,
    ):
        """Create a filesystem service restricted to a resolved root directory."""
        self.root_dir = root_dir.resolve()
        self.pdf_extractor = (
            pdf_extractor if pdf_extractor is not None else PdfTextExtractor()
        )

    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path while preventing access outside the root."""
        path = (self.root_dir / relative_path).resolve()

        # Resolving first makes both parent traversal and symlink escapes visible.
        if not path.is_relative_to(self.root_dir):
            raise ValueError(f"Path is outside ROOT_DIR: {relative_path}")

        return path

    def _resolve_directory(self, relative_path: str) -> Path:
        """Resolve and validate a directory located beneath the configured root."""
        path = self.resolve_path(relative_path)

        if not path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {relative_path}")

        return path

    def _relative_path(self, path: Path) -> str:
        """Convert an absolute path into a portable path relative to the root."""
        return path.relative_to(self.root_dir).as_posix()

    def list_files(self, relative_path: str = "") -> list[str]:
        """List direct child files in a directory using root-relative paths."""
        directory = self._resolve_directory(relative_path)

        return sorted(
            self._relative_path(path)
            for path in directory.iterdir()
            if path.is_file()
        )

    def list_dirs(self, relative_path: str = "") -> list[str]:
        """List direct child directories using root-relative paths."""
        directory = self._resolve_directory(relative_path)

        return sorted(
            self._relative_path(path)
            for path in directory.iterdir()
            if path.is_dir()
        )

    def get_contents(
        self,
        relative_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Read an entire text file or an optional one-based line range."""
        path = self.resolve_path(relative_path)

        if start_line is None and end_line is None:
            return path.read_text()

        lines = path.read_text().splitlines(keepends=True)
        start_index = 0 if start_line is None else max(start_line - 1, 0)
        end_index = None if end_line is None else end_line

        return "".join(lines[start_index:end_index])

    def search_file(
        self,
        course_title: str,
        file_path: str,
        keyword: str,
        context_lines: int = 3,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search one course file and return bounded matches with context."""
        self._validate_search_arguments(
            course_title,
            file_path,
            keyword,
            context_lines,
            max_results,
        )
        path = self._resolve_course_file(course_title, file_path)
        file_result = self._search_path(
            path,
            keyword,
            context_lines,
            max_results,
        )

        return {
            "course_title": course_title,
            "file_path": file_path,
            "keyword": keyword,
            **file_result,
        }

    def search_course(
        self,
        course_title: str,
        keyword: str,
        context_lines: int = 3,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search eligible files recursively within one course."""
        self._validate_course_search_arguments(
            course_title,
            keyword,
            context_lines,
            max_results,
        )
        course_path = self._resolve_course(course_title)
        course_candidate = self.root_dir / course_title
        if course_candidate.is_symlink():
            raise ValueError("course_title must not be a symbolic link")

        matching_files = []

        for path in self._iter_course_files(course_path):
            file_path = path.relative_to(course_path).as_posix()
            try:
                file_result = self._search_path(
                    path,
                    keyword,
                    context_lines,
                    max_results,
                )
            except (OSError, ValueError):
                continue

            if file_result["match_count"] > 0:
                matching_files.append({"file_path": file_path, **file_result})

        matching_files.sort(key=lambda file_result: file_result["file_path"])
        return {
            "course_title": course_title,
            "keyword": keyword,
            "matching_file_count": len(matching_files),
            "match_count": sum(
                file_result["match_count"] for file_result in matching_files
            ),
            "files": matching_files,
        }

    def _search_path(
        self,
        path: Path,
        keyword: str,
        context_lines: int,
        max_results: int,
    ) -> dict[str, Any]:
        """Search one resolved path and return its match details."""
        # Normalize a text document or each PDF page into the same line source.
        if path.suffix.casefold() == ".pdf":
            sources = self.pdf_extractor.extract_pages(path)
        else:
            sources = [(None, self._read_text(path).splitlines())]

        # Scan every line before limiting results so match_count remains exact.
        matches = [
            (source_index, line_index)
            for source_index, (_, lines) in enumerate(sources)
            for line_index, line in enumerate(lines)
            if keyword.casefold() in line.casefold()
        ]
        # The limit applies to marked matches; surrounding context stays intact.
        selected_matches = matches[:max_results]
        excerpts = self._build_excerpts(
            sources,
            selected_matches,
            context_lines,
        )

        return {
            "match_count": len(matches),
            "truncated": len(matches) > max_results,
            "excerpts": excerpts,
        }

    def _validate_search_arguments(
        self,
        course_title: str,
        file_path: str,
        keyword: str,
        context_lines: int,
        max_results: int,
    ) -> None:
        """Validate search input types and configured numeric bounds."""
        self._validate_course_search_arguments(
            course_title,
            keyword,
            context_lines,
            max_results,
        )
        if not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

    def _validate_course_search_arguments(
        self,
        course_title: str,
        keyword: str,
        context_lines: int,
        max_results: int,
    ) -> None:
        """Validate arguments shared by single-file and course-wide searches."""
        for name, value in (("course_title", course_title), ("keyword", keyword)):
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")

        if keyword == "":
            raise ValueError("keyword must not be empty")
        if type(context_lines) is not int or not 0 <= context_lines <= 20:
            raise ValueError("context_lines must be an integer from 0 to 20")
        if type(max_results) is not int or not 1 <= max_results <= 100:
            raise ValueError("max_results must be an integer from 1 to 100")

    def _resolve_course(self, course_title: str) -> Path:
        """Resolve a direct course directory beneath the configured root."""
        course_relative = Path(course_title)
        if course_relative.is_absolute() or len(course_relative.parts) != 1:
            raise ValueError("course_title must name a direct course directory")

        course_path = (self.root_dir / course_relative).resolve()
        if course_path.parent != self.root_dir:
            raise ValueError("course_title must name a direct course directory")
        if not course_path.is_dir():
            raise NotADirectoryError(f"Course is not a directory: {course_title}")

        return course_path

    def _resolve_course_file(self, course_title: str, file_path: str) -> Path:
        """Resolve a regular file while enforcing its selected course boundary."""
        course_path = self._resolve_course(course_title)

        file_relative = Path(file_path)
        if file_relative.is_absolute():
            raise ValueError("file_path must be relative to the course directory")

        # Resolve before containment checks to reject traversal and symlink escapes.
        path = (course_path / file_relative).resolve()
        if not path.is_relative_to(course_path):
            raise ValueError(f"File is outside course directory: {file_path}")
        if not path.exists():
            raise FileNotFoundError(f"File does not exist: {file_path}")
        if not path.is_file():
            raise IsADirectoryError(f"Path is not a file: {file_path}")

        return path

    def _iter_course_files(self, course_path: Path) -> Iterator[Path]:
        """Yield searchable candidates through the fixed course depth limit."""
        for root, directory_names, file_names in os.walk(
            course_path,
            topdown=True,
            followlinks=False,
        ):
            directory = Path(root)
            relative_directory = directory.relative_to(course_path)
            depth = len(relative_directory.parts)

            if depth >= COURSE_SEARCH_MAX_DEPTH:
                directory_names[:] = []
            else:
                directory_names[:] = sorted(
                    name
                    for name in directory_names
                    if not name.startswith(".")
                    and name not in COURSE_SEARCH_EXCLUDED_DIRS
                    and not (directory / name).is_symlink()
                )

            for file_name in sorted(file_names):
                path = directory / file_name
                if (
                    file_name.startswith(".")
                    or path.is_symlink()
                    or not path.is_file()
                ):
                    continue
                yield path

    def _read_text(self, path: Path) -> str:
        """Read a file as UTF-8 and translate decoding failures into tool errors."""
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"File is not valid UTF-8 text: {path.name}") from exc
        except OSError as exc:
            raise ValueError(f"Unable to read file: {path.name}") from exc

    def _build_excerpts(
        self,
        sources: list[tuple[int | None, list[str]]],
        matches: list[tuple[int, int]],
        context_lines: int,
    ) -> list[dict[str, Any]]:
        """Merge overlapping match contexts into structured response excerpts."""
        # Windows use zero-based, end-exclusive indexes until serialization.
        windows: list[tuple[int, int, int, list[int]]] = []

        for source_index, line_index in matches:
            lines = sources[source_index][1]
            start = max(0, line_index - context_lines)
            end = min(len(lines), line_index + context_lines + 1)

            # Merge true overlaps in one source, but keep adjacent windows apart.
            if (
                windows
                and windows[-1][0] == source_index
                and start < windows[-1][2]
            ):
                previous_source, previous_start, previous_end, match_lines = (
                    windows[-1]
                )
                windows[-1] = (
                    previous_source,
                    previous_start,
                    max(previous_end, end),
                    [*match_lines, line_index],
                )
            else:
                windows.append((source_index, start, end, [line_index]))

        excerpts = []
        for source_index, start, end, match_lines in windows:
            page, lines = sources[source_index]
            # The public response uses one-based, inclusive line locations.
            excerpt = {
                "start_line": start + 1,
                "end_line": end,
                "match_lines": [line_index + 1 for line_index in match_lines],
                "lines": [
                    {"line_number": index + 1, "text": lines[index]}
                    for index in range(start, end)
                ],
            }
            if page is not None:
                excerpt = {"page": page, **excerpt}
            excerpts.append(excerpt)

        return excerpts
