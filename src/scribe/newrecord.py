"""`scribe new`: turn a JSON spec into a validated decision record (plan 4.9).

The spec carries only what a human or an agent can know: the front-matter keys
that are not generated, plus the body sections. Everything with an identity or a
lifecycle meaning (`id`, `alias`, `date`, `review_state`, `effective_state`, the
ratification fields, `implementation_links`, `history`) is produced here, so a
caller can not talk a record into looking reviewed.

Nothing is written until the whole record validates: a bad spec leaves the store
untouched and reports the validator's problems.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .frontmatter import join
from .index import write_index
from .record import utc_now
from .schema import KEYS, Problem, validate_record
from .state import (
    RECORDS_WRITTEN_CAP,
    ledger_lock_path,
    load_state,
    locked,
    push_recent,
    session_entry,
    update_state,
)
from .store import Store, reconcile_supersession
from .ulid import generate

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "record_template.md"
SLUG_MAX_LENGTH = 40
SLUG_FALLBACK = "decision"
DEFAULT_BY = "scribe-new"
UNKNOWN_SESSION = "unknown"
# V8: exclusive-create keeps retrying numbered suffixes; this bounds the retry
# so a pathological collision fails cleanly instead of looping forever.
MAX_ALIAS_ATTEMPTS = 1000

SPEC_FRONT_MATTER_KEYS = (
    "title",
    "task_refs",
    "decided_by",
    "recommended_by",
    "provenance",
    "affects",
    "tags",
    "reversibility",
    "blast_radius",
    "regret_when",
    "review",
    "verify",
    "supersedes",
    "relates_to",
)
SPEC_BODY_KEYS = (
    "y_statement",
    "question",
    "criteria",
    "constraints",
    "options",
    "decision",
    "consequences",
    "attempted_and_failed",
    "evidence_quote",
    "evidence_pointers",
)
PROVENANCE_DEFAULTS = {
    "authored_by": "agent",
    "agent": None,
    "model": None,
    "session": None,
    "prompt_ids": [],
    "trigger": "user-prompt",
    "source_messages": [],
}
FRONT_MATTER_DEFAULTS: dict[str, Any] = {
    "task_refs": [],
    "decided_by": "agent",
    "recommended_by": None,
    "affects": [],
    "tags": [],
    "reversibility": "unknown",
    "blast_radius": "component",
    "regret_when": None,
    "review": None,
    "verify": [],
    "supersedes": None,
    "relates_to": [],
}


class SpecError(ValueError):
    """The spec file is missing, unreadable, or not a JSON object."""


def load_spec(path: str | Path) -> dict[str, Any]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"cannot read spec: {exc}") from exc
    try:
        loaded = json.loads(text)
    except ValueError as exc:
        raise SpecError(f"spec is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SpecError("spec must be a JSON object")
    unknown = sorted(set(loaded) - set(SPEC_FRONT_MATTER_KEYS) - set(SPEC_BODY_KEYS))
    if unknown:
        raise SpecError(f"unknown spec keys: {', '.join(unknown)}")
    return loaded


def slugify(title: str) -> str:
    """Lowercase ASCII words joined by single hyphens, trimmed to 40 characters."""
    lowered = title.lower().encode("ascii", "ignore").decode("ascii")
    collapsed = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", lowered)).strip("-")
    trimmed = collapsed[:SLUG_MAX_LENGTH].strip("-")
    return trimmed or SLUG_FALLBACK


def alias_stem(slug: str, today: str) -> str:
    return f"D-{today[2:].replace('-', '')}-{slug}"


def _alias_candidates(stem: str) -> Iterator[str]:
    """`stem`, then `stem-2`, `stem-3`, ... without bound; callers cap attempts."""
    yield stem
    suffix = 2
    while True:
        yield f"{stem}-{suffix}"
        suffix += 1


def unique_alias(store: Store, slug: str, today: str) -> str:
    """`D-YYMMDD-<slug>`, with `-2`, `-3` appended while the file already exists.

    Best-effort only: two callers can both see the same free alias here before
    either writes. `_write_record_exclusive` is what actually reserves the
    filename (V8), retrying this same sequence under `open(path, "x")`.
    """
    stem = alias_stem(slug, today)
    for candidate in _alias_candidates(stem):
        if not (store.path / f"{candidate}.md").exists():
            return candidate
    raise AssertionError("unreachable")  # pragma: no cover


def _write_record_exclusive(
    store: Store, stem: str, data: dict[str, Any], body: str
) -> tuple[Path, str] | None:
    """Reserve a filename and write the record under exclusive create (V8).

    Tries `stem`, then `stem-2`, `stem-3`, ... via `os.O_EXCL`, so two `scribe
    new` runs racing on the same title can never overwrite one another: the
    loser always advances to the next unused suffix rather than clobbering the
    winner's file. `data["alias"]` is updated in place to match whichever
    candidate is finally used. Returns None (nothing written) once
    MAX_ALIAS_ATTEMPTS candidates are all taken.
    """
    store.path.mkdir(parents=True, exist_ok=True)
    for attempt, candidate in enumerate(_alias_candidates(stem)):
        if attempt >= MAX_ALIAS_ATTEMPTS:
            return None
        data["alias"] = candidate
        candidate_path = store.path / f"{candidate}.md"
        try:
            descriptor = os.open(candidate_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(join(data, body))
        return candidate_path, candidate
    return None


def _blockquote(text: str) -> str:
    """Continuation lines of a quoted paragraph keep the `> ` marker."""
    lines = str(text).strip().splitlines() or [""]
    return "\n> ".join(line.rstrip() for line in lines)


def _option_rows(options: Any) -> str:
    rows = []
    for option in options if isinstance(options, list) else []:
        if not isinstance(option, dict):
            continue
        why = "chosen" if option.get("chosen") else str(option.get("why_rejected", ""))
        cells = [
            str(option.get("option", "")),
            str(option.get("for", "")),
            str(option.get("against", "")),
            str(option.get("evidence", "")),
            why,
        ]
        rows.append("| " + " | ".join(cell.replace("|", "/") for cell in cells) + " |")
    return "\n".join(rows)


def _attempted_block(text: Any) -> str:
    if not text or not str(text).strip():
        return ""
    return f"\n## Attempted and failed\n\n{str(text).strip()}\n"


def _pointer_lines(pointers: Any) -> str:
    items = pointers if isinstance(pointers, list) else []
    return "\n".join(f"- {item}" for item in items)


def render_body(spec: dict[str, Any], title: str) -> str:
    """Fill the template; the body always starts with the blank line before the H1."""
    substitutions = {
        "TITLE": title,
        "Y_STATEMENT": _blockquote(spec.get("y_statement", "")),
        "QUESTION": str(spec.get("question", "")).strip(),
        "CRITERIA": str(spec.get("criteria", "")).strip(),
        "CONSTRAINTS": str(spec.get("constraints", "")).strip(),
        "OPTIONS_ROWS": _option_rows(spec.get("options")),
        "DECISION": str(spec.get("decision", "")).strip(),
        "CONSEQUENCES": str(spec.get("consequences", "")).strip(),
        "ATTEMPTED_AND_FAILED": _attempted_block(spec.get("attempted_and_failed")),
        "EVIDENCE_QUOTE": _blockquote(spec.get("evidence_quote", "")),
        "EVIDENCE_POINTERS": _pointer_lines(spec.get("evidence_pointers")),
    }
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    text = re.sub(r"\{\{([A-Z_]+)\}\}", lambda match: substitutions[match[1]], text)
    return "\n" + text


def _session_defaults(root: Path, session: str | None) -> tuple[list[str], list[str]]:
    """The session's `task_refs` and its most recent prompt id, both possibly empty."""
    if session is None:
        return [], []
    entry = load_state(root).get("sessions", {}).get(session)
    if not isinstance(entry, dict):
        return [], []
    task_refs = entry.get("task_refs")
    prompt_ids = entry.get("prompt_ids")
    refs = (
        [item for item in task_refs if isinstance(item, str)]
        if isinstance(task_refs, list)
        else []
    )
    prompts = (
        [item for item in prompt_ids if isinstance(item, str)]
        if isinstance(prompt_ids, list)
        else []
    )
    return refs, prompts[:1]


def build_front_matter(
    spec: dict[str, Any],
    record_id: str,
    alias: str,
    today: str,
    session: str | None,
    session_task_refs: list[str],
    session_prompt_ids: list[str],
) -> dict[str, Any]:
    provenance = {**PROVENANCE_DEFAULTS}
    supplied = spec.get("provenance")
    if isinstance(supplied, dict):
        provenance.update(
            {key: value for key, value in supplied.items() if key in provenance}
        )
    if provenance["session"] is None:
        provenance["session"] = session
    if not isinstance(supplied, dict) or "prompt_ids" not in supplied:
        provenance["prompt_ids"] = list(session_prompt_ids)

    values: dict[str, Any] = {
        **FRONT_MATTER_DEFAULTS,
        **{key: spec[key] for key in SPEC_FRONT_MATTER_KEYS if key in spec},
    }
    values["provenance"] = provenance
    if "task_refs" not in spec:
        values["task_refs"] = list(session_task_refs)

    generated = {
        "id": record_id,
        "alias": alias,
        "title": str(spec.get("title", "")).strip(),
        "date": today,
        "schema_version": 1,
        "review_state": "unreviewed",
        "effective_state": "proposed",
        "ratified_by": None,
        "ratified_at": None,
        "implementation_links": [],
    }
    values.update(generated)
    return {key: values[key] for key in KEYS if key != "history"}


def _history_entry(by: str, session: str | None, at: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"at": at, "event": "proposed", "by": by}
    if session:
        entry["session"] = session
    return entry


def _register(root: Path, session: str | None, record_id: str, at: str) -> None:
    """Add the ULID to the session's pending decisions and to records_written.

    `pending_decisions` is uncapped (plan 4.9, V19): an id stays until a commit
    consumes it (post-commit's `consume_pending`) or the session itself is
    pruned by `prune_sessions`'s existing expiry. Only `records_written`, the
    plan's own recency list, is capped.
    """
    session_id = session or UNKNOWN_SESSION

    def mutate(state: dict[str, Any]) -> None:
        entry = session_entry(state, session_id, at)
        entry["pending_decisions"] = push_recent(
            entry.get("pending_decisions") or [], [record_id], cap=None
        )
        entry["records_written"] = push_recent(
            entry.get("records_written") or [],
            [{"id": record_id, "at": at}],
            RECORDS_WRITTEN_CAP,
        )

    update_state(root, mutate, now=at)


def create_record(
    store: Store,
    spec: dict[str, Any],
    by: str | None = None,
    session: str | None = None,
    register: bool = False,
) -> tuple[Path | None, list[Problem]]:
    """Write one record from the spec; on any validator error nothing is written.

    V8: the whole mutating part runs under the shared ledger lock, records are
    reloaded right after it is acquired, and the file itself is reserved with
    exclusive create so a same-title race can never overwrite another writer.
    """
    now = utc_now()
    today = datetime.now(timezone.utc).date().isoformat()
    title = str(spec.get("title", "")).strip()
    slug = slugify(title)
    stem = alias_stem(slug, today)

    with locked(ledger_lock_path(store.root)) as acquired:
        if not acquired:
            print(
                "scribe new: ledger lock timeout; no record written",
                file=sys.stderr,
            )
            return None, []
        store.records(refresh=True)
        session_task_refs, session_prompt_ids = _session_defaults(store.root, session)

        alias = unique_alias(store, slug, today)
        data = build_front_matter(
            spec,
            generate(),
            alias,
            today,
            session,
            session_task_refs,
            session_prompt_ids,
        )
        author = by or data["provenance"].get("agent") or DEFAULT_BY
        data["history"] = [_history_entry(author, session, now)]
        body = render_body(spec, title)
        path = store.path / f"{alias}.md"

        problems = validate_record(data, body, store=store, path=path)
        if any(problem.severity == "error" for problem in problems):
            return None, problems

        written = _write_record_exclusive(store, stem, data, body)
        if written is None:
            return None, [
                *problems,
                Problem(
                    "error",
                    "alias_reservation_failed",
                    f"could not reserve a unique filename for {stem} "
                    f"after {MAX_ALIAS_ATTEMPTS} attempts",
                ),
            ]
        path, _final_alias = written

        records = store.records(refresh=True)
        if data["supersedes"] is not None:
            for changed in reconcile_supersession(records, DEFAULT_BY):
                changed.save()
        write_index(store)
        if register:
            _register(store.root, session, data["id"], now)
        return path, problems
