"""Deferred behaviour, stated as skip-marked tests (plan 5.2, 5.4, 7 item 7, F13).

Each test names the behaviour that is not implemented in this run and the
condition under which it is switched on. No task may un-skip or modify another
task's test here.
"""

import pytest

VERIFY_ACTIVATION = (
    "F13: enable after 14 days of dogfood `scribe lint` with zero `verify_error`"
)


@pytest.mark.skip(reason=VERIFY_ACTIVATION)
def test_commit_msg_runs_verify_on_staged_content() -> None:
    """commit-msg runs each referenced record's `verify` entries against the staged
    content (README 10.4 "Commit validation") and warns, or fails under enforce,
    on `verify_failed`. Until then only `scribe lint` runs `verify`."""
    raise AssertionError(
        "deferred: commit-msg does not run verify on staged content yet"
    )


@pytest.mark.skip(reason=VERIFY_ACTIVATION)
def test_check_runs_verify_on_committed_content() -> None:
    """`scribe check --base <ref>` runs each changed record's `verify` entries against
    the committed content of the range and fails on `verify_failed` (plan 5.4, the
    "Not implemented (F13)" paragraph). Until then only `scribe lint` runs `verify`,
    so a branch can land code that contradicts its own record's verify entry."""
    raise AssertionError(
        "deferred: scribe check does not run verify on committed content yet"
    )
