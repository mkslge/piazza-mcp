from collections import Counter
from typing import Any


class PiazzaShapeProfiler:
    """Report aggregate Piazza response shapes without exposing values."""

    def profile(
        self,
        summaries: list[dict[str, Any]],
        thread: dict[str, Any] | None,
    ) -> dict[str, Any]:
        objects = [*summaries]
        if thread is not None:
            objects.append(thread)

        top_level_keys = Counter()
        value_types = Counter()
        known_post_kinds = Counter()
        history_lengths = Counter()
        child_depths = Counter()
        html_field_count = 0

        for item in objects:
            for key, value in item.items():
                top_level_keys[key] += 1
                value_types[f"{key}:{type(value).__name__}"] += 1
            post_kind = item.get("type")
            known_post_kinds[
                post_kind
                if post_kind in {"question", "note", "poll"}
                else "unknown"
            ] += 1
            history = item.get("history")
            history_lengths[str(len(history) if isinstance(history, list) else 0)] += 1
            html_field_count += self._count_html_fields(item)
            self._record_child_depths(item.get("children"), 1, child_depths)

        return {
            "summary_count": len(summaries),
            "full_thread_profiled": thread is not None,
            "top_level_key_counts": dict(sorted(top_level_keys.items())),
            "value_type_counts": dict(sorted(value_types.items())),
            "post_kind_counts": dict(sorted(known_post_kinds.items())),
            "history_length_counts": dict(sorted(history_lengths.items())),
            "child_depth_counts": dict(sorted(child_depths.items())),
            "html_field_count": html_field_count,
        }

    def _record_child_depths(
        self,
        children: Any,
        depth: int,
        counts: Counter,
    ) -> None:
        if not isinstance(children, list):
            return
        for child in children:
            if not isinstance(child, dict):
                continue
            counts[str(depth)] += 1
            self._record_child_depths(child.get("children"), depth + 1, counts)

    @staticmethod
    def _count_html_fields(value: Any) -> int:
        if isinstance(value, dict):
            return sum(
                PiazzaShapeProfiler._count_html_fields(item)
                for item in value.values()
            )
        if isinstance(value, list):
            return sum(
                PiazzaShapeProfiler._count_html_fields(item) for item in value
            )
        if isinstance(value, str):
            lowered = value.casefold()
            return int("<p" in lowered or "<div" in lowered or "<br" in lowered)
        return 0
