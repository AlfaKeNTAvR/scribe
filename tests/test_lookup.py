import subprocess
from collections.abc import Callable
from pathlib import Path

from scribe.record import Record

ALIAS = "D-260908-verbatim-quote-is-the-evidence"
ULID = "01M21BVB05VVF1XV54Y66AWV6E"
OTHER_ALIAS = "D-260908-one-way-door-defer-not-stop"
OTHER_ULID = "01M21BVA0X8D5FZCRZNX848569"


def _commit(repo: Path, message: str, touch: str | None = None) -> str:
    if touch is not None:
        path = repo / touch
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{touch}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", message],
        check=True,
    )
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_lookup_commit_with_both_tokens(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    sha = _commit(tmp_repo, f"docs: Bootstrap\n\nDecision: {ALIAS} {ULID}\n")

    code, stdout, _ = run_cli(["lookup", sha], tmp_repo)

    assert code == 0
    assert stdout.splitlines() == [
        f"{ALIAS} {ULID} docs/decisions/{ALIAS}.md (ratified, proposed)"
    ]


def test_lookup_commit_with_alias_only(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    sha = _commit(tmp_repo, f"feat: Alias only\n\nDecision: {ALIAS}\n")

    code, stdout, _ = run_cli(["lookup", sha], tmp_repo)

    assert code == 0
    assert stdout.splitlines() == [
        f"{ALIAS} {ULID} docs/decisions/{ALIAS}.md (ratified, proposed)"
    ]


def test_lookup_commit_with_ulid_only(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    sha = _commit(tmp_repo, f"feat: Ulid only\n\nDecision: {ULID}\n")

    code, stdout, _ = run_cli(["lookup", sha], tmp_repo)

    assert code == 0
    assert stdout.splitlines() == [
        f"{ALIAS} {ULID} docs/decisions/{ALIAS}.md (ratified, proposed)"
    ]


def test_lookup_commit_with_several_trailers(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    message = (
        "docs: Two records\n"
        "\n"
        f"Decision: {ALIAS} {ULID}\n"
        f"Decision: {OTHER_ALIAS} {OTHER_ULID}\n"
    )
    sha = _commit(tmp_repo, message)

    code, stdout, _ = run_cli(["lookup", sha], tmp_repo)

    assert code == 0
    assert stdout.splitlines() == [
        f"{ALIAS} {ULID} docs/decisions/{ALIAS}.md (ratified, proposed)",
        f"{OTHER_ALIAS} {OTHER_ULID} docs/decisions/{OTHER_ALIAS}.md"
        " (ratified, proposed)",
    ]


def test_lookup_commit_with_unknown_token(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    sha = _commit(tmp_repo, "feat: Unknown\n\nDecision: D-260908-nope\n")

    code, stdout, _ = run_cli(["lookup", sha], tmp_repo)

    assert code == 1
    assert stdout.splitlines() == ["UNKNOWN D-260908-nope"]


def test_lookup_commit_without_trailers(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    sha = _commit(tmp_repo, "chore: No trailers\n")

    code, stdout, _ = run_cli(["lookup", sha], tmp_repo)

    assert code == 0
    assert stdout.strip() == f"no Decision trailers on {sha}"


def test_lookup_record_lists_referencing_commits(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    bootstrap = _commit(tmp_repo, f"docs: Bootstrap\n\nDecision: {ALIAS} {ULID}\n")
    implementing = _commit(
        tmp_repo,
        f"feat: Implement it\n\nDecision: {ULID}\n",
        touch="src/thing.py",
    )
    unrelated = _commit(
        tmp_repo,
        f"feat: Other record\n\nDecision: {OTHER_ALIAS} {OTHER_ULID}\n",
    )
    mentions_only = _commit(
        tmp_repo,
        f"chore: Mentions {ALIAS} in the body but carries no trailer\n",
    )

    code, stdout, _ = run_cli(["lookup", ALIAS], tmp_repo)

    assert code == 0
    lines = stdout.splitlines()
    assert lines[0] == f"docs/decisions/{ALIAS}.md"
    assert lines[1] == "commits:"
    assert bootstrap in stdout
    assert implementing in stdout
    assert unrelated not in stdout
    assert mentions_only not in stdout
    assert "implementation_links:" in lines
    assert lines[-1] == "  (none)"


def test_lookup_by_ulid_matches_the_same_record(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    _commit(tmp_repo, f"docs: Bootstrap\n\nDecision: {ALIAS} {ULID}\n")

    code, stdout, _ = run_cli(["lookup", ULID], tmp_repo)

    assert code == 0
    assert stdout.splitlines()[0] == f"docs/decisions/{ALIAS}.md"


def test_lookup_marks_unreachable_implementation_link(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    reachable = _commit(
        tmp_repo,
        f"feat: Reachable\n\nDecision: {ALIAS} {ULID}\n",
        touch="src/thing.py",
    )
    record_path = tmp_repo / "docs" / "decisions" / f"{ALIAS}.md"
    record = Record.load(record_path)
    record.data["implementation_links"] = [
        {"commit": reachable[:12], "paths": ["src/thing.py"]},
        {"commit": "0" * 12, "paths": ["src/gone.py"]},
    ]
    record.save()

    code, stdout, _ = run_cli(["lookup", ALIAS], tmp_repo)

    assert code == 0
    assert f"  {reachable[:12]} src/thing.py" in stdout.splitlines()
    assert f"  {'0' * 12} src/gone.py (not in this history)" in stdout.splitlines()


def test_lookup_unknown_token_exits_one(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    _commit(tmp_repo, "chore: Init\n")

    code, stdout, _ = run_cli(["lookup", "nope"], tmp_repo)

    assert code == 1
    assert stdout.strip() == "not found: nope"
