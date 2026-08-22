import json
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).parents[2]
INSPECTOR = PROJECT_ROOT / "scripts" / "inspect_canvas_calendar.py"


def inspector_environment(snapshot: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "CANVAS_ICAL_URL": "",
            "CANVAS_ICAL_PATH": str(snapshot),
            "CALENDAR_TIMEZONE": "America/New_York",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
        }
    )
    return environment


def run_inspector(snapshot: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSPECTOR)],
        cwd=PROJECT_ROOT,
        env=inspector_environment(snapshot),
        capture_output=True,
        text=True,
        check=False,
    )


def test_inspector_command_prints_aggregate_only_output(tmp_path):
    private_marker = "PRIVATE_COMMAND_VALUE"
    snapshot = tmp_path / "private-feed-token.ics"
    snapshot.write_text(
        f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:{private_marker}-uid
DTSTART:20260820T120000Z
SUMMARY:{private_marker}-title
URL:https://umd.instructure.com/courses/1/assignments/2?token={private_marker}
END:VEVENT
END:VCALENDAR
"""
    )

    result = run_inspector(snapshot)

    assert result.returncode == 0
    profile = json.loads(result.stdout)
    assert profile["source"] == "local_ical_snapshot"
    assert profile["usable_event_count"] == 1
    assert profile["url_shapes"]["canvas_assignment"] == 1
    assert private_marker not in result.stdout
    assert snapshot.name not in result.stdout
    assert result.stderr == ""


def test_inspector_command_redacts_malformed_content_and_path(tmp_path):
    private_marker = "PRIVATE_MALFORMED_COMMAND_VALUE"
    snapshot = tmp_path / "private-malformed-feed-token.ics"
    snapshot.write_text(private_marker)

    result = run_inspector(snapshot)

    assert result.returncode == 1
    assert result.stdout == ""
    assert json.loads(result.stderr) == {
        "error": "Canvas calendar feed is malformed"
    }
    assert private_marker not in result.stderr
    assert snapshot.name not in result.stderr
