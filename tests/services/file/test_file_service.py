import importlib

import pytest

from course_mcp.config import filesystem as filesystem_config_module
from course_mcp.services.file import factory as file_factory_module
from course_mcp.services.file import PdfExtractionError


def load_file_service(monkeypatch, root_dir):
    monkeypatch.setenv("ROOT_DIR", str(root_dir))
    monkeypatch.delenv("ROOT_DIR_", raising=False)
    monkeypatch.setattr(filesystem_config_module, "load_project_env", lambda: None)
    monkeypatch.setattr(file_factory_module, "_file_service", None)

    return importlib.import_module("course_mcp.services.file")


def test_resolve_path_stays_inside_root(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)

    assert service.resolve_path("notes/week1.txt") == (
        tmp_path / "notes" / "week1.txt"
    ).resolve()


def test_resolve_path_rejects_paths_outside_root(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)

    with pytest.raises(ValueError, match="Path is outside ROOT_DIR"):
        service.resolve_path("../secret.txt")


def test_get_contents_reads_whole_file(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    file_path = tmp_path / "lecture.txt"
    file_path.write_text("line one\nline two\n")

    assert service.get_contents("lecture.txt") == "line one\nline two\n"


def test_get_contents_reads_line_range(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    file_path = tmp_path / "lecture.txt"
    file_path.write_text("one\ntwo\nthree\n")

    assert service.get_contents("lecture.txt", start_line=2, end_line=3) == "two\nthree\n"


def test_module_level_get_contents_uses_injected_root(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    file_path = tmp_path / "lecture.txt"
    file_path.write_text("module helper\n")

    assert module.get_contents("lecture.txt") == "module helper\n"


def create_course_file(tmp_path, relative_path, contents, *, binary=False):
    path = tmp_path / "CMSC132" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        path.write_bytes(contents)
    else:
        path.write_text(contents, encoding="utf-8")
    return path


def test_search_file_matches_literal_case_insensitively_and_merges_context(
    monkeypatch,
    tmp_path,
):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(
        tmp_path,
        "notes/week1.txt",
        "intro\nRECURSION recursion\nbetween\nrecursion!\nend\n",
    )

    result = service.search_file(
        "CMSC132",
        "notes/week1.txt",
        "recursion",
        context_lines=1,
    )

    assert result == {
        "course_title": "CMSC132",
        "file_path": "notes/week1.txt",
        "keyword": "recursion",
        "match_count": 2,
        "truncated": False,
        "excerpts": [
            {
                "start_line": 1,
                "end_line": 5,
                "match_lines": [2, 4],
                "lines": [
                    {"line_number": 1, "text": "intro"},
                    {"line_number": 2, "text": "RECURSION recursion"},
                    {"line_number": 3, "text": "between"},
                    {"line_number": 4, "text": "recursion!"},
                    {"line_number": 5, "text": "end"},
                ],
            }
        ],
    }


@pytest.mark.parametrize("keyword", ["two words", "!", " "])
def test_search_file_accepts_literal_whitespace_and_punctuation(
    monkeypatch,
    tmp_path,
    keyword,
):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(tmp_path, "notes.txt", "two words!\n")

    result = service.search_file(
        "CMSC132",
        "notes.txt",
        keyword,
        context_lines=0,
    )

    assert result["match_count"] == 1


def test_search_file_returns_empty_excerpts_for_no_matches(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(tmp_path, "notes.txt", "iteration\n")

    result = service.search_file("CMSC132", "notes.txt", "recursion")

    assert result["match_count"] == 0
    assert result["truncated"] is False
    assert result["excerpts"] == []


def test_search_file_truncates_marked_matches_but_keeps_context(
    monkeypatch,
    tmp_path,
):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(tmp_path, "notes.txt", "match one\nmatch two\n")

    result = service.search_file(
        "CMSC132",
        "notes.txt",
        "match",
        context_lines=1,
        max_results=1,
    )

    assert result["match_count"] == 2
    assert result["truncated"] is True
    assert result["excerpts"][0]["match_lines"] == [1]
    assert result["excerpts"][0]["lines"] == [
        {"line_number": 1, "text": "match one"},
        {"line_number": 2, "text": "match two"},
    ]


@pytest.mark.parametrize(
    ("keyword", "context_lines", "max_results", "message"),
    [
        ("", 3, 20, "keyword must not be empty"),
        ("match", -1, 20, "context_lines must be an integer from 0 to 20"),
        ("match", 21, 20, "context_lines must be an integer from 0 to 20"),
        ("match", 3, 0, "max_results must be an integer from 1 to 100"),
        ("match", 3, 101, "max_results must be an integer from 1 to 100"),
    ],
)
def test_search_file_validates_search_arguments(
    monkeypatch,
    tmp_path,
    keyword,
    context_lines,
    max_results,
    message,
):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)

    with pytest.raises(ValueError, match=message):
        service.search_file(
            "CMSC132",
            "notes.txt",
            keyword,
            context_lines,
            max_results,
        )


def test_search_file_rejects_invalid_course_and_file_paths(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(tmp_path, "notes.txt", "content\n")
    other_course = tmp_path / "CMSC216"
    other_course.mkdir()
    (other_course / "secret.txt").write_text("secret\n")

    with pytest.raises(ValueError, match="direct course directory"):
        service.search_file("CMSC132/nested", "notes.txt", "content")
    with pytest.raises(ValueError, match="relative to the course"):
        service.search_file("CMSC132", str(tmp_path / "outside.txt"), "content")
    with pytest.raises(ValueError, match="outside course directory"):
        service.search_file("CMSC132", "../CMSC216/secret.txt", "secret")


def test_search_file_rejects_symlink_escape(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(tmp_path, "notes.txt", "content\n")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n")
    (tmp_path / "CMSC132" / "link.txt").symlink_to(outside)

    with pytest.raises(ValueError, match="outside course directory"):
        service.search_file("CMSC132", "link.txt", "secret")


def test_search_file_rejects_missing_directory_and_non_utf8_file(
    monkeypatch,
    tmp_path,
):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(tmp_path, "binary.dat", b"\xff\xfe", binary=True)
    (tmp_path / "CMSC132" / "folder").mkdir()

    with pytest.raises(FileNotFoundError, match="does not exist"):
        service.search_file("CMSC132", "missing.txt", "text")
    with pytest.raises(IsADirectoryError, match="not a file"):
        service.search_file("CMSC132", "folder", "text")
    with pytest.raises(ValueError, match="not valid UTF-8"):
        service.search_file("CMSC132", "binary.dat", "text")


class FakePdfExtractor:
    def __init__(self, results):
        self.results = results
        self.paths = []

    def extract_pages(self, path):
        self.paths.append(path)
        result = self.results[path.name]
        if isinstance(result, Exception):
            raise result
        return result


def test_search_file_reports_pdf_pages_and_page_local_lines(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    create_course_file(tmp_path, "LECTURE.PDF", b"pdf", binary=True)
    extractor = FakePdfExtractor(
        {
            "LECTURE.PDF": [
                (1, ["intro", "Recursion", "end"]),
                (2, ["recursion again", "last"]),
            ]
        }
    )
    service = module.FileService(tmp_path, extractor)

    result = service.search_file(
        "CMSC132",
        "LECTURE.PDF",
        "recursion",
        context_lines=1,
    )

    assert result["match_count"] == 2
    assert [excerpt["page"] for excerpt in result["excerpts"]] == [1, 2]
    assert [excerpt["match_lines"] for excerpt in result["excerpts"]] == [
        [2],
        [1],
    ]
    assert result["excerpts"][1]["start_line"] == 1
    assert extractor.paths == [tmp_path / "CMSC132" / "LECTURE.PDF"]


def test_search_file_propagates_pdf_extraction_errors(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    create_course_file(tmp_path, "lecture.pdf", b"pdf", binary=True)
    extractor = FakePdfExtractor(
        {"lecture.pdf": PdfExtractionError("PDF is encrypted: lecture.pdf")}
    )
    service = module.FileService(tmp_path, extractor)

    with pytest.raises(ValueError, match="PDF is encrypted"):
        service.search_file("CMSC132", "lecture.pdf", "keyword")


def test_search_file_reads_text_without_using_pdf_extractor(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    create_course_file(tmp_path, "notes.txt", "needle\n")
    extractor = FakePdfExtractor({})
    service = module.FileService(tmp_path, extractor)

    result = service.search_file("CMSC132", "notes.txt", "needle")

    assert result["match_count"] == 1
    assert extractor.paths == []


def test_search_course_includes_files_through_depth_five(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(tmp_path, "root.txt", "needle\n")

    parts = []
    expected_paths = ["root.txt"]
    for depth in range(1, 7):
        parts.append(f"level{depth}")
        relative_path = "/".join([*parts, "notes.txt"])
        create_course_file(tmp_path, relative_path, "needle\n")
        if depth <= 5:
            expected_paths.append(relative_path)

    result = service.search_course(
        "CMSC132",
        "needle",
        context_lines=0,
    )

    assert result["matching_file_count"] == 6
    assert result["match_count"] == 6
    assert [file_result["file_path"] for file_result in result["files"]] == sorted(
        expected_paths
    )


def test_search_course_skips_hidden_excluded_and_symlink_entries(
    monkeypatch,
    tmp_path,
):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    visible = create_course_file(tmp_path, "visible.txt", "needle\n")
    create_course_file(tmp_path, ".hidden.txt", "needle\n")
    create_course_file(tmp_path, ".hidden/notes.txt", "needle\n")

    for directory_name in (
        "venv",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
    ):
        create_course_file(
            tmp_path,
            f"{directory_name}/notes.txt",
            "needle\n",
        )

    course_path = tmp_path / "CMSC132"
    (course_path / "linked-file.txt").symlink_to(visible)
    (course_path / "linked-directory").symlink_to(course_path)

    result = service.search_course("CMSC132", "needle", context_lines=0)

    assert [file_result["file_path"] for file_result in result["files"]] == [
        "visible.txt"
    ]


def test_search_course_applies_result_limit_per_file_and_sorts_paths(
    monkeypatch,
    tmp_path,
):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(tmp_path, "z-last.txt", "match\nmatch\n")
    create_course_file(tmp_path, "a-first/notes.txt", "match\nmatch\nmatch\n")

    result = service.search_course(
        "CMSC132",
        "match",
        context_lines=0,
        max_results=1,
    )

    assert result["matching_file_count"] == 2
    assert result["match_count"] == 5
    assert [file_result["file_path"] for file_result in result["files"]] == [
        "a-first/notes.txt",
        "z-last.txt",
    ]
    assert all(file_result["truncated"] for file_result in result["files"])
    assert all(
        len(file_result["excerpts"]) == 1 for file_result in result["files"]
    )


def test_search_course_silently_skips_unsearchable_files(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    create_course_file(tmp_path, "notes.txt", "needle\n")
    create_course_file(tmp_path, "binary.dat", b"\xff\xfe", binary=True)
    create_course_file(tmp_path, "valid.pdf", b"pdf", binary=True)
    create_course_file(tmp_path, "empty.pdf", b"pdf", binary=True)
    create_course_file(tmp_path, "broken.pdf", b"pdf", binary=True)
    extractor = FakePdfExtractor(
        {
            "broken.pdf": PdfExtractionError("Unable to read PDF: broken.pdf"),
            "empty.pdf": PdfExtractionError(
                "PDF has no extractable text: empty.pdf"
            ),
            "valid.pdf": [(1, ["needle"])],
        }
    )
    service = module.FileService(tmp_path, extractor)

    result = service.search_course("CMSC132", "needle", context_lines=0)

    assert [file_result["file_path"] for file_result in result["files"]] == [
        "notes.txt",
        "valid.pdf",
    ]
    pdf_result = result["files"][1]
    assert pdf_result["excerpts"][0]["page"] == 1


def test_search_course_returns_empty_files_when_nothing_matches(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(tmp_path, "notes.txt", "iteration\n")

    result = service.search_course("CMSC132", "recursion")

    assert result == {
        "course_title": "CMSC132",
        "keyword": "recursion",
        "matching_file_count": 0,
        "match_count": 0,
        "files": [],
    }


def test_search_course_rejects_symlinked_course(monkeypatch, tmp_path):
    module = load_file_service(monkeypatch, tmp_path)
    service = module.FileService(tmp_path)
    create_course_file(tmp_path, "notes.txt", "needle\n")
    (tmp_path / "COURSE-LINK").symlink_to(tmp_path / "CMSC132")

    with pytest.raises(ValueError, match="must not be a symbolic link"):
        service.search_course("COURSE-LINK", "needle")
