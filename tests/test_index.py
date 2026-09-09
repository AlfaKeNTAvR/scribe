import fcntl
import json
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from scribe.frontmatter import join
from scribe.index import render_index
from scribe.state import ledger_lock_path
from scribe.store import Store
from scribe.ulid import generate as generate_ulid


def write_fixture_record(
    directory: Path,
    alias: str,
    *,
    date: str,
    review_state: str = "unreviewed",
    effective_state: str = "proposed",
    decided_by: str = "agent",
    supersedes: str | None = None,
    affects: list[dict[str, object]] | None = None,
    regret_when: str | None = None,
    review: str | None = None,
) -> Path:
    # A real ULID, not the alias (V5): an attestation for this record carries
    # this id, and `attestation_item_problems` now requires it to be
    # ULID-shaped, matching how every real record is actually keyed.
    data = {
        "id": generate_ulid(),
        "alias": alias,
        "title": f"Title of {alias}",
        "date": date,
        "review_state": review_state,
        "effective_state": effective_state,
        "decided_by": decided_by,
        "affects": affects if affects is not None else [],
        "regret_when": regret_when,
        "review": review,
        "supersedes": supersedes,
        "history": [{"at": f"{date}T00:00:00Z", "event": "proposed", "by": "test"}],
    }
    path = directory / f"{alias}.md"
    path.write_text(join(data, f"\n# Title of {alias}\n"), encoding="utf-8")
    return path


@pytest.fixture
def fixture_store(tmp_path: Path) -> Store:
    """Store covering every routing branch of section 3.5."""
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    write_fixture_record(
        decisions,
        "D-260901-ratified-predecessor",
        date="2026-09-01",
        review_state="ratified",
        decided_by="human",
    )
    write_fixture_record(
        decisions,
        "D-260910-supersedes-ratified",
        date="2026-09-10",
        effective_state="implemented",
        supersedes="D-260901-ratified-predecessor",
        affects=[
            {"type": "path", "pattern": "src/scribe/index.py"},
            {"type": "path", "pattern": "tests/**", "negate": True},
            {"type": "action", "pattern": "git-push"},
        ],
    )
    write_fixture_record(
        decisions,
        "D-260909-implemented-unreviewed",
        date="2026-09-09",
        effective_state="implemented",
    )
    write_fixture_record(
        decisions,
        "D-260908-proposed-unreviewed",
        date="2026-09-08",
        decided_by="agent-recommended",
        regret_when="Three of these pile up.",
        review="2026-12-08",
    )
    write_fixture_record(
        decisions,
        "D-260902-active-predecessor",
        date="2026-09-02",
        review_state="ratified",
        effective_state="implemented",
        decided_by="human",
    )
    write_fixture_record(
        decisions,
        "D-260911-rejected-successor",
        date="2026-09-11",
        review_state="rejected",
        supersedes="D-260902-active-predecessor",
    )
    write_fixture_record(
        decisions,
        "D-260903-expired",
        date="2026-09-03",
        review_state="ratified",
        effective_state="expired",
    )
    write_fixture_record(
        decisions,
        "D-260904-stale-superseded",
        date="2026-09-04",
        review_state="ratified",
        effective_state="superseded",
        decided_by="human",
    )
    store = Store(tmp_path)
    attestations = []
    for record in store.records():
        if record.data.get("review_state") == "ratified":
            attestations.append(
                {
                    "id": record.data["id"],
                    "alias": record.data["alias"],
                    "verdict": "ratified",
                    "by": "@test",
                    "at": f"{record.data['date']}T00:00:00Z",
                    "via": "cli",
                    "body_sha256": record.body_sha256(),
                }
            )
    (decisions / "RATIFICATIONS.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in attestations), encoding="utf-8"
    )
    return store


def section_blocks(text: str, heading: str) -> list[list[str]]:
    """Split a section's body into per-record blocks (heading line plus its
    bullet lines), dropping the blank separator lines and the queue note."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if line.startswith("### "):
            if current:
                blocks.append(current)
            current = [line]
        elif line == "":
            continue
        elif current:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def test_header_counts_records(fixture_store: Store) -> None:
    text = render_index(fixture_store)
    assert text.startswith("# Decision index\n\n")
    assert "Generated by `scribe index` from 8 records. Do not edit by hand." in text


def test_review_queue_holds_every_unreviewed_record_in_group_order(
    fixture_store: Store,
) -> None:
    text = render_index(fixture_store)
    assert "## Review queue (3)" in text
    queue = section_blocks(text, "## Review queue")
    assert queue[0][0] == "### 1. D-260910-supersedes-ratified [supersedes ratified]"
    assert "- supersedes: D-260901-ratified-predecessor" in queue[0]
    assert queue[1][0] == "### 2. D-260909-implemented-unreviewed"
    assert queue[2][0] == "### 3. D-260908-proposed-unreviewed"
    assert "[supersedes ratified]" not in queue[1][0] + queue[2][0]


def test_queue_block_carries_states_affects_and_title(fixture_store: Store) -> None:
    queue = section_blocks(render_index(fixture_store), "## Review queue")
    assert queue[0] == [
        "### 1. D-260910-supersedes-ratified [supersedes ratified]",
        "- supersedes: D-260901-ratified-predecessor",
        "- state: implemented, unreviewed",
        "- by: agent",
        "- review: ",
        "- title: Title of D-260910-supersedes-ratified",
        "- affects: src/scribe/index.py, !tests/**",
    ]


def test_active_holds_only_effectively_attested_authority(
    fixture_store: Store,
) -> None:
    text = render_index(fixture_store)
    assert "## Active decisions (1)" in text
    active = section_blocks(text, "## Active decisions")
    assert [block[0] for block in active] == [
        "### D-260902-active-predecessor",
    ]


def test_rejected_successor_leaves_its_predecessor_active(
    fixture_store: Store,
) -> None:
    active = section_blocks(render_index(fixture_store), "## Active decisions")
    predecessor = next(
        block for block in active if block[0] == "### D-260902-active-predecessor"
    )
    assert predecessor == [
        "### D-260902-active-predecessor",
        "- state: implemented, ratified",
        "- by: human",
        "- review: ",
        "- title: Title of D-260902-active-predecessor",
    ]
    assert not any(block[0] == "### D-260911-rejected-successor" for block in active)


def test_unattested_record_is_not_active(fixture_store: Store) -> None:
    active = section_blocks(render_index(fixture_store), "## Active decisions")
    assert not any(
        "D-260908-proposed-unreviewed" in line for block in active for line in block
    )


def test_retired_states_cover_edge_rejected_expired_and_stale(
    fixture_store: Store,
) -> None:
    text = render_index(fixture_store)
    assert "## Retired (4)" in text
    retired = section_blocks(text, "## Retired")
    states = {block[0][len("### ") :]: block[1] for block in retired}
    assert states == {
        "D-260911-rejected-successor": "- retired: rejected",
        "D-260904-stale-superseded": "- retired: superseded (stale)",
        "D-260903-expired": "- retired: expired",
        "D-260901-ratified-predecessor": (
            "- retired: superseded by D-260910-supersedes-ratified"
        ),
    }
    assert all(not line.startswith("- affects:") for block in retired for line in block)


def test_backtracked_record_appears_in_retired_not_vanished(tmp_path: Path) -> None:
    """A ratified record whose effective_state is backtracked used to vanish:

    it is not superseded, rejected, expired or superseded (stale), so
    `_retired_state` returned None, and it is also not `proposed` or
    `implemented`, so `Store.effective_authority` returned False. It landed
    in neither Active nor Retired. Fails on the old code because `retired`
    comes back empty instead of holding the one backtracked line.
    """
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    write_fixture_record(
        decisions,
        "D-260905-backtracked",
        date="2026-09-05",
        review_state="ratified",
        effective_state="backtracked",
        decided_by="human",
    )
    store = Store(tmp_path)
    record = store.records()[0]
    (decisions / "RATIFICATIONS.jsonl").write_text(
        json.dumps(
            {
                "id": record.data["id"],
                "alias": record.data["alias"],
                "verdict": "ratified",
                "by": "@test",
                "at": "2026-09-05T00:00:00Z",
                "via": "cli",
                "body_sha256": record.body_sha256(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store = Store(tmp_path)
    text = render_index(store)
    assert "## Active decisions (0)" in text
    retired = section_blocks(text, "## Retired")
    assert retired == [
        [
            "### D-260905-backtracked",
            "- retired: backtracked",
            "- state: backtracked, ratified",
            "- by: human",
            "- review: ",
            "- title: Title of D-260905-backtracked",
        ]
    ]


def test_render_matches_the_format_c_heading_per_record_layout(
    tmp_path: Path,
) -> None:
    """Pins the heading-per-record layout (format C, docs/build/13-index-preview-c.md):
    one `### ` heading per record with one `- field:` bullet per line, blocks
    separated by a single blank line. Fails on the old pipe-separated
    one-line-per-record renderer, which never emits a `### ` heading at all.
    """
    decisions = tmp_path / "docs" / "decisions"
    decisions.mkdir(parents=True)
    write_fixture_record(
        decisions,
        "D-1-ratified-predecessor",
        date="2026-01-01",
        review_state="ratified",
        effective_state="implemented",
        decided_by="human",
    )
    write_fixture_record(
        decisions,
        "D-2-supersedes-ratified",
        date="2026-01-02",
        effective_state="implemented",
        supersedes="D-1-ratified-predecessor",
        affects=[{"type": "path", "pattern": "src/a.py"}],
        regret_when="Something bad happens.",
        review="2026-06-01",
    )
    write_fixture_record(
        decisions,
        "D-3-active",
        date="2026-01-03",
        review_state="ratified",
        effective_state="implemented",
        decided_by="human",
    )
    store = Store(tmp_path)
    attestations = [
        {
            "id": record.data["id"],
            "alias": record.data["alias"],
            "verdict": "ratified",
            "by": "@test",
            "at": f"{record.data['date']}T00:00:00Z",
            "via": "cli",
            "body_sha256": record.body_sha256(),
        }
        for record in store.records()
        if record.data.get("review_state") == "ratified"
    ]
    (decisions / "RATIFICATIONS.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in attestations), encoding="utf-8"
    )
    text = render_index(Store(tmp_path))
    assert text == (
        "# Decision index\n\n"
        "Generated by `scribe index` from 3 records. Do not edit by hand.\n\n"
        "## Review queue (1)\n\n"
        "Ordered: records that supersede a ratified record first, then "
        "implemented, then proposed; newest first within each group.\n\n"
        "### 1. D-2-supersedes-ratified [supersedes ratified]\n"
        "- supersedes: D-1-ratified-predecessor\n"
        "- state: implemented, unreviewed\n"
        "- by: agent\n"
        "- review: 2026-06-01\n"
        "- title: Title of D-2-supersedes-ratified\n"
        "- affects: src/a.py\n"
        "- regret: Something bad happens.\n\n"
        "## Active decisions (1)\n\n"
        "### D-3-active\n"
        "- state: implemented, ratified\n"
        "- by: human\n"
        "- review: \n"
        "- title: Title of D-3-active\n\n"
        "## Retired (1)\n\n"
        "### D-1-ratified-predecessor\n"
        "- retired: superseded by D-2-supersedes-ratified\n"
        "- state: implemented, ratified\n"
        "- by: human\n"
        "- review: \n"
        "- title: Title of D-1-ratified-predecessor\n"
    )


def test_render_is_deterministic(fixture_store: Store) -> None:
    first = render_index(fixture_store)
    second = render_index(Store(fixture_store.root))
    assert first == second


def test_empty_store_renders_all_three_sections(tmp_path: Path) -> None:
    (tmp_path / "docs" / "decisions").mkdir(parents=True)
    text = render_index(Store(tmp_path))
    assert text == (
        "# Decision index\n\n"
        "Generated by `scribe index` from 0 records. Do not edit by hand.\n\n"
        "## Review queue (0)\n\n"
        "Ordered: records that supersede a ratified record first, then "
        "implemented, then proposed; newest first within each group.\n\n"
        "## Active decisions (0)\n\n"
        "## Retired (0)\n"
    )


def test_index_command_writes_then_check_passes(
    tmp_repo: Path, run_cli: Callable[..., tuple[int, str, str]]
) -> None:
    decisions = tmp_repo / "docs" / "decisions"
    code, out, _ = run_cli(["index", "--check"], tmp_repo)
    assert code == 1
    assert "out of date" in out

    code, out, _ = run_cli(["index"], tmp_repo)
    assert code == 0
    assert "docs/decisions/INDEX.md" in out
    generated = (decisions / "INDEX.md").read_text(encoding="utf-8")
    assert generated == render_index(Store(tmp_repo))

    code, out, _ = run_cli(["index", "--check"], tmp_repo)
    assert code == 0
    assert "up to date" in out


def test_index_check_fails_on_a_hand_edited_file(
    tmp_repo: Path, run_cli: Callable[..., tuple[int, str, str]]
) -> None:
    run_cli(["index"], tmp_repo)
    index_file = tmp_repo / "docs" / "decisions" / "INDEX.md"
    index_file.write_text(
        index_file.read_text(encoding="utf-8") + "hand edit\n", encoding="utf-8"
    )
    code, _, _ = run_cli(["index", "--check"], tmp_repo)
    assert code == 1


def test_index_command_reports_a_missing_store(
    tmp_path: Path, run_cli: Callable[..., tuple[int, str, str]]
) -> None:
    code, out, _ = run_cli(["index", str(tmp_path / "nowhere")], tmp_path)
    assert code == 1
    assert "no decision store found" in out


def test_index_write_lock_timeout_exits_nonzero_without_writing(
    tmp_repo: Path, run_cli: Callable[..., tuple[int, str, str]]
) -> None:
    """V8: `scribe index` writes under the same ledger lock as new, ratify,
    post-commit, relink and lint --expire. Fails on the old code: it took no
    lock at all, so it would write INDEX.md immediately and exit 0 regardless
    of another writer holding the lock, and the elapsed time would not
    include a 2 s wait.
    """
    index_file = tmp_repo / "docs" / "decisions" / "INDEX.md"
    assert not index_file.exists()
    lock_path = ledger_lock_path(tmp_repo)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        code, _, stderr = run_cli(["index"], tmp_repo)
        elapsed = time.monotonic() - started
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)

    assert elapsed >= 2.0
    assert code == 1
    assert "ledger lock timeout" in stderr
    assert not index_file.exists()


def test_index_check_lock_timeout_exits_nonzero(
    tmp_repo: Path, run_cli: Callable[..., tuple[int, str, str]]
) -> None:
    """V8: `scribe index --check` reads under the ledger lock too, reloading
    records after acquiring it. Fails on the old code the same way as the
    write case above (no lock, immediate exit, no 2 s wait).
    """
    assert run_cli(["index"], tmp_repo)[0] == 0
    lock_path = ledger_lock_path(tmp_repo)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        code, _, stderr = run_cli(["index", "--check"], tmp_repo)
        elapsed = time.monotonic() - started
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)

    assert elapsed >= 2.0
    assert code == 1
    assert "ledger lock timeout" in stderr
