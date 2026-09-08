from pathlib import Path
import subprocess

import pytest

from scribe.record import Record
from scribe.gitutil import git_path_hooks, staged_paths, toplevel
from scribe.store import Store, reconcile_supersession


def make_record(
    tmp_path: Path,
    alias: str,
    record_id: str,
    *,
    review_state: str = "unreviewed",
    effective_state: str = "proposed",
    supersedes: str | None = None,
) -> Record:
    return Record(
        tmp_path / f"{alias}.md",
        {
            "id": record_id,
            "alias": alias,
            "review_state": review_state,
            "effective_state": effective_state,
            "supersedes": supersedes,
            "history": [{"at": "2026-09-08T00:00:00Z", "event": "proposed", "by": "test"}],
        },
        "",
    )


@pytest.mark.parametrize(
    ("review_state", "effective_state", "effective"),
    [
        ("unreviewed", "proposed", True),
        ("ratified", "implemented", True),
        ("unreviewed", "superseded", True),
        ("rejected", "proposed", False),
        ("unreviewed", "expired", False),
        ("unreviewed", "backtracked", False),
    ],
)
def test_effective_edges(
    tmp_path: Path, review_state: str, effective_state: str, effective: bool
) -> None:
    predecessor = make_record(tmp_path, "D-260908-old", "01M21BV91NZSW1HMJ127KZAA5J")
    successor = make_record(
        tmp_path,
        "D-260909-new",
        "01M21BV91NZSW1HMJ127KZAA5K",
        review_state=review_state,
        effective_state=effective_state,
        supersedes=predecessor.data["alias"],
    )
    store = Store(tmp_path)
    store._records = [predecessor, successor]
    assert store.effective_edges() == ([(successor, predecessor)] if effective else [])


def test_effective_edge_resolves_ulid_and_ignores_dangling(tmp_path: Path) -> None:
    predecessor = make_record(tmp_path, "D-260908-old", "01M21BV91NZSW1HMJ127KZAA5J")
    successor = make_record(
        tmp_path,
        "D-260909-new",
        "01M21BV91NZSW1HMJ127KZAA5K",
        supersedes=predecessor.data["id"],
    )
    dangling = make_record(
        tmp_path,
        "D-260910-later",
        "01M21BV91NZSW1HMJ127KZAA5M",
        supersedes="D-260901-missing",
    )
    store = Store(tmp_path)
    store._records = [predecessor, successor, dangling]
    assert store.effective_edges() == [(successor, predecessor)]


def test_reconcile_marks_predecessor_and_appends_history(tmp_path: Path) -> None:
    predecessor = make_record(
        tmp_path,
        "D-260908-old",
        "01M21BV91NZSW1HMJ127KZAA5J",
        effective_state="implemented",
    )
    successor = make_record(
        tmp_path,
        "D-260909-new",
        "01M21BV91NZSW1HMJ127KZAA5K",
        supersedes=predecessor.data["alias"],
    )
    assert reconcile_supersession([predecessor, successor], "scribe-new") == [predecessor]
    assert predecessor.data["effective_state"] == "superseded"
    assert predecessor.data["history"][-1] | {"at": "ignored"} == {
        "at": "ignored",
        "event": "superseded",
        "by": "scribe-new",
        "field": "effective_state",
        "old": "implemented",
        "new": "superseded",
    }


def test_reconcile_restores_latest_prior_state(tmp_path: Path) -> None:
    predecessor = make_record(
        tmp_path,
        "D-260908-old",
        "01M21BV91NZSW1HMJ127KZAA5J",
        effective_state="implemented",
    )
    successor = make_record(
        tmp_path,
        "D-260909-new",
        "01M21BV91NZSW1HMJ127KZAA5K",
        supersedes=predecessor.data["alias"],
    )
    reconcile_supersession([predecessor, successor], "scribe-new")
    successor.data["review_state"] = "rejected"
    assert reconcile_supersession([predecessor, successor], "scribe-reject") == [predecessor]
    assert predecessor.data["effective_state"] == "implemented"
    assert predecessor.data["history"][-1]["event"] == "restored"
    assert predecessor.data["history"][-1]["old"] == "superseded"
    assert predecessor.data["history"][-1]["new"] == "implemented"


def test_reconcile_does_not_invent_restore_state(tmp_path: Path) -> None:
    stale = make_record(
        tmp_path,
        "D-260908-stale",
        "01M21BV91NZSW1HMJ127KZAA5J",
        effective_state="superseded",
    )
    assert reconcile_supersession([stale], "scribe-lint") == []
    assert stale.data["effective_state"] == "superseded"


def test_reconcile_chain_keeps_superseded_successor_effective(tmp_path: Path) -> None:
    first = make_record(tmp_path, "D-260908-first", "01M21BV91NZSW1HMJ127KZAA5J")
    second = make_record(
        tmp_path,
        "D-260909-second",
        "01M21BV91NZSW1HMJ127KZAA5K",
        supersedes=first.data["alias"],
    )
    third = make_record(
        tmp_path,
        "D-260910-third",
        "01M21BV91NZSW1HMJ127KZAA5M",
        supersedes=second.data["alias"],
    )
    reconcile_supersession([first, second, third], "test")
    assert first.data["effective_state"] == "superseded"
    assert second.data["effective_state"] == "superseded"


def test_git_utilities_normalize_git_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = tmp_path / "repo" / "nested"
    nested.mkdir(parents=True)
    responses = {
        ("rev-parse", "--show-toplevel"): str(tmp_path / "repo") + "\n",
        ("diff", "--cached", "--name-only", "--diff-filter=ACMR"): "src/a.py\ndir\\b.py\n",
        ("rev-parse", "--git-path", "hooks"): "../.git/hooks\n",
    }

    def fake_git(cwd: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, responses[args], "")

    monkeypatch.setattr("scribe.gitutil._git", fake_git)
    assert toplevel(nested) == tmp_path / "repo"
    assert staged_paths(nested) == ["src/a.py", "dir/b.py"]
    assert git_path_hooks(nested) == tmp_path / "repo" / ".git" / "hooks"
