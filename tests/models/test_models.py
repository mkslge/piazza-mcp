from course_mcp.models.file import File


def test_file_stores_path():
    file = File("course/notes.txt")

    assert file.path == "course/notes.txt"
