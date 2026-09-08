from datetime import date, datetime, timezone

import pytest

from scribe.frontmatter import FrontMatterError, join, split


def test_split_normalizes_timestamps_and_preserves_body() -> None:
    mapping, body = split("---\ndate: 2026-09-08\nat: 2026-09-08T20:37:43Z\n---\n\n# Body\n")
    assert mapping == {"date": "2026-09-08", "at": "2026-09-08T20:37:43Z"}
    assert body == "\n# Body\n"


def test_join_uses_flow_style_and_round_trips() -> None:
    mapping = {
        "date": date(2026, 9, 8),
        "history": [{"at": datetime(2026, 9, 8, tzinfo=timezone.utc), "event": "proposed"}],
        "affects": [{"type": "path", "pattern": "src/**"}],
    }
    text = join(mapping, "\nbody\r\n")
    assert "history:\n- {at: '2026-09-08T00:00:00Z', event: proposed}" in text
    assert "affects:\n- {type: path, pattern: src/**}" in text
    loaded, body = split(text)
    assert loaded["date"] == "2026-09-08"
    assert body == "\nbody\n"


def test_split_rejects_missing_delimiters() -> None:
    with pytest.raises(FrontMatterError):
        split("title: nope")
