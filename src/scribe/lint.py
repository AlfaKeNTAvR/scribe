"""`scribe lint`: every rule the single-record validator cannot see (plan 4.12).

Lint is the store-wide pass. It runs `validate` over every record, re-runs the
index generator, compares the store with a git base through `history_check.py`,
executes the `verify` entries against the working tree, and reports the
lifecycle smells (stale proposals, overdue reviews, unreachable links). Errors
set the exit code; warnings and info lines are printed and cost nothing.

`--expire` is the one mutating switch: a proposal nobody reviewed for
STALE_PROPOSAL_DAYS is moved to `expired`, and `reconcile_supersession` then
restores any predecessor the expired record was holding down.
"""

from __future__ import annotations

import math
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import gitutil
from .history_check import check_records_against_base
from .index import locked_check_index, locked_write_index, write_index
from .matching import matches
from .policy import RULE_NAMES
from .record import Record
from .schema import validate_pytest_target, validate_record
from .state import ledger_lock_path, load_state, locked, update_state
from .store import Store, reconcile_supersession

STALE_PROPOSAL_DAYS = 30
LINT_BY = "scribe-lint"
DEFAULT_BASES = ("origin/main", "HEAD~1")
# Deliberately state-based, not `store.effective_authority`: the lifecycle
# smells below (`review_overdue`, `unreviewed_implemented`) must still fire
# on records that are not yet ratified, which is the whole point of catching
# them here before they are.
ACTIVE_STATES = {"proposed", "implemented", "backtracked"}
SKIPPED_DIRECTORIES = {".git"}
DEFAULT_VERIFY_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str = ""

    def render(self) -> str:
        head = f"{self.path}: " if self.path else ""
        return f"{head}{self.severity}: {self.code}: {self.message}"


# --- helpers ----------------------------------------------------------------


def _relative(store: Store, path: Path) -> str:
    try:
        return path.resolve().relative_to(store.root).as_posix()
    except ValueError:
        return path.as_posix()


def _repo_files(root: Path) -> list[str]:
    """The files `verify` globs are matched against, repository-relative.

    Git decides the list, so anything `.gitignore` covers is out: a `.venv`
    inside the repository holds a `LICENSE` for every dependency, and a
    `verify` glob with no slash matches at any depth, so those copies would be
    checked and reported as failures. Outside a repository, or when git
    cannot answer, fall back to walking the tree minus `.git/`.
    """
    listed = gitutil.working_tree_files(root)
    if listed is not None:
        return listed
    found: list[str] = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = [
            name for name in subdirectories if name not in SKIPPED_DIRECTORIES
        ]
        base = Path(directory)
        for filename in filenames:
            found.append((base / filename).relative_to(root).as_posix())
    return sorted(found)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def resolve_base(explicit: str | None, root: Path) -> tuple[str | None, list[Finding]]:
    """The ref the immutability rules compare against (plan 4.12)."""
    if explicit is not None:
        if gitutil.rev_parse_commit(explicit, root) is None:
            return None, [
                Finding("error", "unknown_base", f"unknown base ref: {explicit}")
            ]
        return explicit, []
    for candidate in DEFAULT_BASES:
        if gitutil.rev_parse_commit(candidate, root) is not None:
            return candidate, []
    return None, []


# --- rules ------------------------------------------------------------------


def _validate_findings(store: Store) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(store.path.glob("D-*.md")):
        relative = _relative(store, path)
        try:
            record = Record.load(path)
            problems = validate_record(record.data, record.body, store=store, path=path)
        except (OSError, ValueError) as exc:
            findings.append(Finding("error", "parse_error", str(exc), relative))
            continue
        findings.extend(
            Finding(problem.severity, problem.code, problem.message, relative)
            for problem in problems
        )
    return findings


def _duplicate_identity(store: Store) -> list[Finding]:
    """Two files claiming the same alias or the same ULID (plan 3.1 item 1)."""
    findings: list[Finding] = []
    for key in ("alias", "id"):
        seen: dict[Any, list[str]] = {}
        for record in store.records():
            value = record.data.get(key)
            if value is None:
                continue
            seen.setdefault(value, []).append(_relative(store, record.path))
        for value, paths in sorted(seen.items(), key=lambda item: str(item[0])):
            if len(paths) > 1:
                findings.append(
                    Finding(
                        "error",
                        "duplicate_alias",
                        f"{key} {value} is used by {len(paths)} records: "
                        + " ".join(sorted(paths)),
                    )
                )
    return findings


def _base_findings(store: Store, base: str | None) -> list[Finding]:
    if base is None:
        return []
    return [
        Finding(problem.severity, problem.code, problem.message, path)
        for path, problem in check_records_against_base(base, store.root)
    ]


def _index_findings(store: Store, fix_index: bool) -> list[Finding]:
    """V8: the check (and the `--fix-index` write) happen under the ledger lock,
    with records reloaded only after the lock is held, so this never compares
    against, or writes over, a snapshot a concurrent writer (new, ratify,
    post-commit, relink, lint --expire) has already moved past.
    """
    if fix_index:
        target, changed, acquired = locked_write_index(store)
        if not acquired:
            print(
                "scribe lint --fix-index: ledger lock timeout; index not regenerated",
                file=sys.stderr,
            )
            return [
                Finding(
                    "error",
                    "ledger_lock_timeout",
                    "ledger lock timeout; index not regenerated",
                )
            ]
        if not changed:
            return []
        return [
            Finding(
                "info",
                "index_stale",
                "regenerated by --fix-index",
                _relative(store, target),
            )
        ]
    target, up_to_date, acquired = locked_check_index(store)
    if not acquired:
        print(
            "scribe lint: ledger lock timeout; index not checked",
            file=sys.stderr,
        )
        return [
            Finding(
                "error",
                "ledger_lock_timeout",
                "ledger lock timeout; index not checked",
            )
        ]
    if up_to_date:
        return []
    return [
        Finding(
            "error",
            "index_stale",
            "differs from the generated index, run scribe index",
            _relative(store, target),
        )
    ]


def _is_active(record: Record, retired: set[int]) -> bool:
    return (
        record.data.get("review_state") != "rejected"
        and record.data.get("effective_state") in ACTIVE_STATES
        and id(record) not in retired
    )


def _lifecycle_findings(store: Store, today: date) -> list[Finding]:
    """The state smells of plan 4.12 that need the whole store, not one record."""
    retired = {id(predecessor) for _, predecessor in store.effective_edges()}
    history = gitutil.ReachableCommits(store.root)
    findings: list[Finding] = []
    for record in store.records():
        relative = _relative(store, record.path)
        data = record.data
        state = data.get("effective_state")
        review_state = data.get("review_state")
        if id(record) in retired and state in {"proposed", "implemented"}:
            findings.append(
                Finding(
                    "warning",
                    "effective_state_stale",
                    "an effective edge retires this record but effective_state is "
                    + str(state),
                    relative,
                )
            )
        elif id(record) not in retired and state == "superseded":
            findings.append(
                Finding(
                    "warning",
                    "effective_state_stale",
                    "effective_state is superseded but no effective edge points here",
                    relative,
                )
            )
        findings.extend(_unknown_action_findings(data, relative))
        if review_state == "rejected" and state == "implemented":
            findings.append(
                Finding(
                    "warning",
                    "rejected_but_implemented",
                    "a rejected decision is still the implemented one",
                    relative,
                )
            )
        active = _is_active(record, retired)
        review_date = _as_date(data.get("review"))
        if active and review_date is not None and review_date < today:
            findings.append(
                Finding(
                    "warning",
                    "review_overdue",
                    f"the review date {review_date.isoformat()} has passed",
                    relative,
                )
            )
        if active and state == "implemented" and review_state == "unreviewed":
            findings.append(
                Finding(
                    "info",
                    "unreviewed_implemented",
                    "implemented but nobody has ratified or rejected it",
                    relative,
                )
            )
        findings.extend(_unreachable_link_findings(history, data, relative))
    return findings


def _unknown_action_findings(data: dict[str, Any], relative: str) -> list[Finding]:
    findings: list[Finding] = []
    for item in data.get("affects") or []:
        if not isinstance(item, dict) or item.get("type") != "action":
            continue
        pattern = item.get("pattern")
        if isinstance(pattern, str) and pattern not in RULE_NAMES:
            findings.append(
                Finding(
                    "warning",
                    "unknown_action",
                    f"action pattern is not a denylist rule name: {pattern}",
                    relative,
                )
            )
    return findings


def _unreachable_link_findings(
    history: gitutil.ReachableCommits, data: dict[str, Any], relative: str
) -> list[Finding]:
    findings: list[Finding] = []
    for link in data.get("implementation_links") or []:
        commit = link.get("commit") if isinstance(link, dict) else None
        if isinstance(commit, str) and history.resolve(commit) is None:
            findings.append(
                Finding(
                    "warning",
                    "unreachable_link",
                    f"commit {commit} is not in this history, run scribe relink",
                    relative,
                )
            )
    return findings


def _is_stale_proposal(record: Record, today: date) -> bool:
    data = record.data
    if data.get("effective_state") != "proposed":
        return False
    if data.get("review_state") != "unreviewed":
        return False
    if data.get("implementation_links"):
        return False
    written = _as_date(data.get("date"))
    return written is not None and today - written > timedelta(days=STALE_PROPOSAL_DAYS)


def _proposal_stale_finding(store: Store, record: Record, expired: bool) -> Finding:
    return Finding(
        "warning",
        "proposal_stale",
        f"proposed and unreviewed since {_as_date(record.data.get('date'))}"
        + (", expired by --expire" if expired else ""),
        _relative(store, record.path),
    )


def _expire_stale(store: Store, today: date) -> list[Finding]:
    """Reload, then move every still-stale proposal to expired (V8: ledger lock).

    On a lock timeout this reports one error finding and one stderr line, and
    changes nothing; `_stale_proposal_findings` still reports the plain
    (un-suffixed) `proposal_stale` warnings from its own pre-lock scan.

    INDEX.md is regenerated here, before the lock is released, rather than
    left to the separate `_index_findings` pass later in `lint_store`: that
    pass takes its own lock and reloads from disk, so if this function
    dropped the lock first, a ratify or another writer could land in the
    gap and this run's now-stale in-memory snapshot would either overwrite
    it (with --fix-index) or never get written at all (without it).
    """
    with locked(ledger_lock_path(store.root)) as acquired:
        if not acquired:
            print(
                "scribe lint --expire: ledger lock timeout; nothing expired",
                file=sys.stderr,
            )
            return [
                Finding(
                    "error",
                    "ledger_lock_timeout",
                    "ledger lock timeout; --expire made no changes",
                )
            ]
        store.records(refresh=True)
        stale = [
            record for record in store.records() if _is_stale_proposal(record, today)
        ]
        findings = [
            _proposal_stale_finding(store, record, expired=True) for record in stale
        ]
        for record in stale:
            record.apply_change("effective_state", "expired", "expired", LINT_BY)
            record.save()
        for record in reconcile_supersession(store.records(), LINT_BY):
            record.save()
        if stale:
            write_index(store)
        return findings


def _stale_proposal_findings(store: Store, today: date, expire: bool) -> list[Finding]:
    """`proposal_stale`, and with `--expire` the expiry and the restore it triggers."""
    stale = [record for record in store.records() if _is_stale_proposal(record, today)]
    if not stale:
        return []
    if not expire:
        return [
            _proposal_stale_finding(store, record, expired=False) for record in stale
        ]
    return _expire_stale(store, today)


def _verify_findings(
    store: Store, files: list[str], invalid_paths: frozenset[str] = frozenset()
) -> list[Finding]:
    """Runs every `verify` entry, skipping records `_validate_findings` already
    flagged with an error (`invalid_paths`, relative paths): a record with a
    malformed `verify` entry, or any other schema error, already has its
    problem reported once; running verify against it besides risks a second,
    confusing finding for the same root cause (or, before this fix, hides the
    problem entirely when the verify entry happens to spawn something that
    exits the way `expect` wants).
    """
    findings: list[Finding] = []
    for record in store.records():
        relative = _relative(store, record.path)
        if relative in invalid_paths:
            continue
        for entry in record.data.get("verify") or []:
            if not isinstance(entry, dict):
                continue
            engine = entry.get("engine")
            if engine == "grep":
                findings.extend(_run_verify_entry(store, entry, files, relative))
            elif engine == "pytest":
                findings.extend(_run_pytest_verify_entry(store, entry, relative))
    return findings


def _run_verify_entry(
    store: Store,
    entry: dict[str, Any],
    files: list[str],
    relative: str,
) -> list[Finding]:
    """One `verify` entry against the working tree, plan 4.4 glob semantics."""
    entry_id = str(entry.get("id", "?"))
    severity = entry.get("severity")
    if not isinstance(severity, str) or severity not in {"error", "warning"}:
        severity = "error"
    pattern = entry.get("pattern")
    globs = [item for item in (entry.get("paths") or []) if isinstance(item, str)]
    if not isinstance(pattern, str):
        return [
            Finding(
                "error",
                "verify_error",
                f"verify {entry_id}: pattern is not a string",
                relative,
            )
        ]
    try:
        expression = re.compile(pattern)
    except re.error as exc:
        return [
            Finding(
                "error",
                "verify_error",
                f"verify {entry_id}: invalid regex {pattern!r}: {exc}",
                relative,
            )
        ]
    selected = [path for path in files if any(matches(glob, path) for glob in globs)]
    expect_match = entry.get("expect") != "no-match"
    if not selected and expect_match:
        return [
            Finding(
                severity,
                "verify_failed",
                f"verify {entry_id}: no file matches {' '.join(globs)}",
                relative,
            )
        ]
    findings: list[Finding] = []
    for path in selected:
        try:
            text = (store.root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                Finding(
                    "error",
                    "verify_error",
                    f"verify {entry_id}: cannot read {path}: {exc}",
                    relative,
                )
            )
            continue
        hit = any(expression.search(line) for line in text.splitlines())
        if expect_match and not hit:
            findings.append(
                Finding(
                    severity,
                    "verify_failed",
                    f"verify {entry_id}: {path} has no line matching {pattern!r}",
                    relative,
                )
            )
        elif not expect_match and hit:
            findings.append(
                Finding(
                    severity,
                    "verify_failed",
                    f"verify {entry_id}: {path} has a line matching {pattern!r}",
                    relative,
                )
            )
    return findings


def _verify_timeout_seconds() -> float:
    """`SCRIBE_VERIFY_TIMEOUT`, or the default for anything not a positive,
    finite number (unset, unparseable, `nan`, `inf`, zero, or negative)."""
    raw = os.environ.get("SCRIBE_VERIFY_TIMEOUT")
    if raw is None:
        return DEFAULT_VERIFY_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_VERIFY_TIMEOUT_SECONDS
    if not math.isfinite(value) or value <= 0:
        return DEFAULT_VERIFY_TIMEOUT_SECONDS
    return value


def _pytest_available(root: Path) -> bool:
    """Whether `root` looks set up to run `uv run --frozen pytest` (plan Q4).

    A cheap gate, not a guarantee: a `pyproject.toml` that mentions `pytest`.
    Anything short of that (no file, or one that never names pytest) is
    reported as `verify_error` without spawning a subprocess.
    """
    pyproject = root / "pyproject.toml"
    try:
        return pyproject.is_file() and "pytest" in pyproject.read_text(encoding="utf-8")
    except OSError:
        return False


def _pytest_target_problem(target: Any, store: Store) -> str | None:
    """First message `schema.validate_pytest_target` raises against `target`, if any.

    One shared rule (schema.py Q4) decides what a pytest verify target may
    be; this only adapts that rule's `error(code, message)` callback into a
    plain message so the runner below can reject before spawning anything.
    """
    problems: list[str] = []

    def error(code: str, message: str) -> None:
        problems.append(message)

    validate_pytest_target(target, error, store)
    return problems[0] if problems else None


def _kill_verify_process_group(process: subprocess.Popen[str]) -> None:
    """Kill the whole process group a timed-out verify subprocess started.

    `start_new_session=True` (POSIX only) made `process.pid` the process
    group id for `uv run ... pytest ...` and everything it spawns, so
    `os.killpg` reaches pytest and any grandchild a slow test itself started
    (e.g. `test_slow`'s own subprocess), not just the direct `uv` child a
    plain `process.kill()` would leave running. No process group exists on
    Windows (`os.killpg` is not available there), so this falls back to
    killing the direct child only.
    """
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except OSError:
            pass
    process.kill()


def _run_pytest_verify_entry(
    store: Store,
    entry: dict[str, Any],
    relative: str,
) -> list[Finding]:
    """One `verify` entry with `engine: pytest`, mirroring the grep engine above.

    Runs `uv run --frozen pytest -q -x -p no:cacheprovider -- <target>` from
    the repository root. `expect: pass` wants exit code 0, `expect: fail`
    wants exit code 1; anything else (timeout, missing pytest, a collection
    or usage error) is `verify_error`, never a crash out of lint.

    The target is rejected up front through `schema.validate_pytest_target`,
    the same rule `scribe validate` enforces, so an entry validate would
    reject (an option such as `--version`, `..`, an absolute path, or a path
    that does not exist) never reaches a pytest subprocess here either. The
    `--` before `<target>` on the command line is a second, independent
    layer: even a target the validator somehow let through cannot be read by
    pytest as another option.
    """
    entry_id = str(entry.get("id", "?"))
    severity = entry.get("severity")
    if not isinstance(severity, str) or severity not in {"error", "warning"}:
        severity = "error"
    target = entry.get("target")
    target_problem = _pytest_target_problem(target, store)
    if target_problem is not None:
        return [
            Finding(
                "error",
                "verify_error",
                f"verify {entry_id}: {target_problem}",
                relative,
            )
        ]
    if not _pytest_available(store.root):
        return [
            Finding(
                "error",
                "verify_error",
                f"verify {entry_id}: pytest is not available in {store.root}",
                relative,
            )
        ]
    timeout = _verify_timeout_seconds()
    command = [
        "uv",
        "run",
        "--frozen",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "--",
        target,
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=store.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=os.name == "posix",
        )
    except OSError as exc:
        return [
            Finding(
                "error",
                "verify_error",
                f"verify {entry_id}: could not run pytest: {exc}",
                relative,
            )
        ]
    try:
        process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_verify_process_group(process)
        process.communicate()
        return [
            Finding(
                "error",
                "verify_error",
                f"verify {entry_id}: pytest timed out after {timeout:g}s running "
                f"{target}",
                relative,
            )
        ]
    returncode = process.returncode
    if returncode not in (0, 1):
        return [
            Finding(
                "error",
                "verify_error",
                f"verify {entry_id}: pytest collection or usage error running "
                f"{target} (exit {returncode})",
                relative,
            )
        ]
    passed = returncode == 0
    expect_pass = entry.get("expect") != "fail"
    if passed != expect_pass:
        outcome = "passed" if passed else "failed"
        expected = "pass" if expect_pass else "fail"
        return [
            Finding(
                severity,
                "verify_failed",
                f"verify {entry_id}: {target} {outcome}, expected {expected}",
                relative,
            )
        ]
    return []


def _pending_findings(store: Store) -> list[Finding]:
    """Scratch-state ids that resolve to no record; pruned as they are reported."""
    state = load_state(store.root)
    sessions = state.get("sessions")
    if not isinstance(sessions, dict):
        return []
    dangling: dict[str, list[str]] = {}
    for session_id, session in sessions.items():
        if not isinstance(session, dict):
            continue
        unknown = [
            item
            for item in session.get("pending_decisions") or []
            if store.resolve(item) is None
        ]
        if unknown:
            dangling[session_id] = unknown
    if not dangling:
        return []

    def prune(document: dict[str, Any]) -> None:
        for session_id, unknown in dangling.items():
            session = document.get("sessions", {}).get(session_id)
            if isinstance(session, dict):
                session["pending_decisions"] = [
                    item
                    for item in session.get("pending_decisions") or []
                    if item not in unknown
                ]

    update_state(store.root, prune)
    return [
        Finding(
            "info",
            "duplicate_pending",
            f"session {session_id}: pruned pending decisions that resolve to no "
            "record: " + " ".join(unknown),
        )
        for session_id, unknown in sorted(dangling.items())
    ]


# --- entry point ------------------------------------------------------------


def lint_store(
    store: Store,
    base: str | None = None,
    expire: bool = False,
    fix_index: bool = False,
    today: date | None = None,
) -> list[Finding]:
    """Every finding, in the rule order of plan 4.12."""
    reference_day = today or datetime.now(timezone.utc).date()
    resolved_base, findings = resolve_base(base, store.root)
    findings.extend(_duplicate_identity(store))
    validate_findings = _validate_findings(store)
    findings.extend(validate_findings)
    invalid_paths = frozenset(
        finding.path for finding in validate_findings if finding.severity == "error"
    )
    findings.extend(_base_findings(store, resolved_base))
    findings.extend(_lifecycle_findings(store, reference_day))
    findings.extend(_stale_proposal_findings(store, reference_day, expire))
    findings.extend(_verify_findings(store, _repo_files(store.root), invalid_paths))
    findings.extend(_pending_findings(store))
    findings.extend(_index_findings(store, fix_index))
    return findings


def run_lint(
    start: str | Path = ".",
    base: str | None = None,
    expire: bool = False,
    fix_index: bool = False,
) -> tuple[int, list[Finding], int]:
    """Exit code, the findings, and the record count for the summary line."""
    store = Store.discover(start)
    if store is None or not store.path.is_dir():
        return (
            1,
            [Finding("error", "no_store", "no decision store found (docs/decisions)")],
            0,
        )
    findings = lint_store(store, base=base, expire=expire, fix_index=fix_index)
    code = 1 if any(finding.severity == "error" for finding in findings) else 0
    return code, findings, len(store.records())
