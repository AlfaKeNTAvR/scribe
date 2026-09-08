from datetime import datetime, timezone

import pytest

from scribe.ulid import generate, is_valid, timestamp_ms


def test_ulid_boundaries() -> None:
    assert is_valid("7ZZZZZZZZZZZZZZZZZZZZZZZZZ")
    assert not is_valid("80000000000000000000000000")
    assert not is_valid("01M21BVB05VVF1XV54Y66AWV6I")


def test_generate_embeds_timestamp() -> None:
    instant = datetime(2026, 9, 8, 20, 37, 43, tzinfo=timezone.utc)
    milliseconds = int(instant.timestamp() * 1000)
    value = generate(milliseconds)
    assert is_valid(value)
    assert timestamp_ms(value) == milliseconds


def test_timestamp_rejects_overflow() -> None:
    with pytest.raises(ValueError):
        timestamp_ms("80000000000000000000000000")
