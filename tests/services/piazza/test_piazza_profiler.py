import json

from piazza_mcp.services.piazza import PiazzaShapeProfiler


def test_profiler_reports_aggregate_shapes_without_private_values():
    private_marker = "PRIVATE_PIAZZA_VALUE"
    summaries = [
        {
            "id": 7,
            "type": "question",
            "subject": private_marker,
            "content_snip": f"<p>{private_marker}</p>",
        }
    ]
    thread = {
        "nr": 7,
        "type": "question",
        "history": [{"content": private_marker}],
        "children": [
            {
                "type": "followup",
                "subject": private_marker,
                "children": [{"type": "feedback", "subject": private_marker}],
            }
        ],
    }

    profile = PiazzaShapeProfiler().profile(summaries, thread)
    serialized = json.dumps(profile)

    assert profile["summary_count"] == 1
    assert profile["full_thread_profiled"] is True
    assert profile["post_kind_counts"] == {"question": 2}
    assert profile["child_depth_counts"] == {"1": 1, "2": 1}
    assert profile["html_field_count"] == 1
    assert private_marker not in serialized
