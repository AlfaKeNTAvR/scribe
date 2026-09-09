from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .record import MUTABLE_KEYS
from .ulid import is_valid, timestamp_ms

if TYPE_CHECKING:
    from .store import Store


@dataclass(frozen=True)
class Problem:
    severity: str
    code: str
    message: str


KEYS = [
    "id",
    "alias",
    "title",
    "date",
    "schema_version",
    "task_refs",
    "review_state",
    "effective_state",
    "decided_by",
    "recommended_by",
    "ratified_by",
    "ratified_at",
    "provenance",
    "affects",
    "implementation_links",
    "tags",
    "reversibility",
    "blast_radius",
    "regret_when",
    "review",
    "verify",
    "supersedes",
    "relates_to",
    "history",
]
REQUIRED_NON_NULL = {
    "id",
    "alias",
    "title",
    "date",
    "schema_version",
    "task_refs",
    "review_state",
    "effective_state",
    "decided_by",
    "provenance",
    "affects",
    "implementation_links",
    "tags",
    "reversibility",
    "blast_radius",
    "verify",
    "relates_to",
    "history",
}
ALIAS_RE = re.compile(r"^D-\d{6}-[a-z0-9]+(?:-[a-z0-9]+)*$")
TASK_REF_RES = [
    re.compile(r"^[A-Z][A-Z0-9]{1,9}-\d+$"),
    re.compile(r"^#\d+$"),
    re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+$"),
]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
TAG_RE = re.compile(r"^[a-z0-9-]+$")
ACTION_RE = re.compile(r"^[a-z][a-z0-9-]*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
VERIFY_ID_RE = re.compile(r"^[a-z0-9-]+$")
HISTORY_EVENTS = {
    "proposed",
    "implemented",
    "ratified",
    "rejected",
    "superseded",
    "restored",
    "expired",
    "backtracked",
    "link_added",
    "supersedes_set",
    "relinked",
}
SECTIONS = [
    "Question",
    "Criteria",
    "Constraints and assumptions",
    "Options considered",
    "Decision",
    "Consequences",
    "Evidence",
]


def _is_str(value: Any) -> bool:
    return isinstance(value, str)


def _is_list_of_strings(value: Any) -> bool:
    return isinstance(value, list) and all(_is_str(item) for item in value)


def _valid_date(value: Any) -> bool:
    if not _is_str(value) or not DATE_RE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _valid_datetime(value: Any) -> bool:
    if not _is_str(value) or not DATETIME_RE.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _body_hash(body: str) -> str:
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.rstrip().encode("utf-8")).hexdigest()


def validate_record(
    mapping: dict[str, Any],
    body: str,
    store: Store | None = None,
    path: str | Path | None = None,
    check_attestation: bool = True,
) -> list[Problem]:
    problems: list[Problem] = []

    def error(code: str, message: str) -> None:
        problems.append(Problem("error", code, message))

    def warning(code: str, message: str) -> None:
        problems.append(Problem("warning", code, message))

    for key in mapping:
        if key not in KEYS:
            error("unknown_key", f"unknown top-level key: {key}")
    for key in KEYS:
        if key not in mapping:
            error("missing_key", f"required key is missing: {key}")
        elif key in REQUIRED_NON_NULL and mapping[key] is None:
            error("null_required", f"required key may not be null: {key}")

    record_id = mapping.get("id")
    if not is_valid(record_id):
        error("invalid_ulid", "id must be a canonical 128-bit ULID")
    alias = mapping.get("alias")
    if not _is_str(alias) or not ALIAS_RE.fullmatch(alias) or not 8 <= len(alias) <= 60:
        error("invalid_alias", "alias must be D-YYMMDD-slug and 8 to 60 characters")
    if (
        path is not None
        and Path(path).stem.startswith("D-")
        and _is_str(alias)
        and Path(path).stem != alias
    ):
        error("alias_filename_mismatch", f"filename stem must equal alias {alias}")

    title = mapping.get("title")
    if (
        not _is_str(title)
        or not 3 <= len(title) <= 200
        or "\n" in title
        or "\r" in title
    ):
        error("invalid_title", "title must be a single line of 3 to 200 characters")
    date_value = mapping.get("date")
    if not _valid_date(date_value):
        error("invalid_date", "date must be YYYY-MM-DD")
    if (
        type(mapping.get("schema_version")) is not int
        or mapping.get("schema_version") != 1
    ):
        error("invalid_schema_version", "schema_version must be 1")

    task_refs = mapping.get("task_refs")
    if not _is_list_of_strings(task_refs):
        error("invalid_type", "task_refs must be a list of strings")
    else:
        for value in task_refs:
            if not any(pattern.fullmatch(value) for pattern in TASK_REF_RES):
                error("invalid_task_ref", f"invalid task reference: {value}")

    _enum(mapping, "review_state", {"unreviewed", "ratified", "rejected"}, error)
    _enum(
        mapping,
        "effective_state",
        {"proposed", "implemented", "superseded", "expired", "backtracked"},
        error,
    )
    _enum(mapping, "decided_by", {"human", "agent-recommended", "agent"}, error)
    _nullable_string(mapping, "recommended_by", error)
    _nullable_string(mapping, "ratified_by", error)
    ratified_at = mapping.get("ratified_at")
    if ratified_at is not None and not _valid_datetime(ratified_at):
        error("invalid_datetime", "ratified_at must be an ISO 8601 UTC datetime")

    _validate_provenance(mapping.get("provenance"), error)
    _validate_affects(mapping.get("affects"), error)
    _validate_links(mapping.get("implementation_links"), error)

    tags = mapping.get("tags")
    if not _is_list_of_strings(tags):
        error("invalid_type", "tags must be a list of strings")
    elif any(not TAG_RE.fullmatch(item) for item in tags):
        error("invalid_tag", "tags must contain lowercase letters, digits, or hyphens")
    _enum(mapping, "reversibility", {"two-way-door", "one-way-door", "unknown"}, error)
    _enum(mapping, "blast_radius", {"component", "team", "cross-team", "org"}, error)
    regret = mapping.get("regret_when")
    if regret is not None and (not _is_str(regret) or len(regret) > 200):
        error(
            "invalid_regret_when", "regret_when must be null or at most 200 characters"
        )
    review = mapping.get("review")
    if review is not None and not _valid_date(review):
        error("invalid_review", "review must be null or YYYY-MM-DD")
    _validate_verify(mapping.get("verify"), error, store)

    supersedes = mapping.get("supersedes")
    if supersedes is not None and not _is_str(supersedes):
        error("invalid_type", "supersedes must be a string or null")
    relates = mapping.get("relates_to")
    if not _is_list_of_strings(relates):
        error("invalid_type", "relates_to must be a list of strings")
    _validate_history(mapping.get("history"), error)
    sections = _validate_body(body, title, mapping.get("effective_state"), error)

    review_state = mapping.get("review_state")
    has_ratifier = mapping.get("ratified_by") is not None
    has_ratified_at = mapping.get("ratified_at") is not None
    if (review_state == "unreviewed" and (has_ratifier or has_ratified_at)) or (
        _in_str_set(review_state, {"ratified", "rejected"})
        and not (has_ratifier and has_ratified_at)
    ):
        error(
            "ratified_fields_inconsistent",
            "ratified_by and ratified_at must agree with review_state",
        )
    if (
        mapping.get("effective_state") == "backtracked"
        and not sections.get("Attempted and failed", "").strip()
    ):
        error(
            "missing_attempted_and_failed",
            "backtracked records require a non-empty Attempted and failed section",
        )
    if (
        mapping.get("effective_state") == "implemented"
        and mapping.get("implementation_links") == []
    ):
        warning(
            "implemented_without_links",
            "implemented record has no implementation links",
        )

    if is_valid(record_id) and _valid_date(date_value):
        try:
            ulid_date = datetime.fromtimestamp(
                timestamp_ms(record_id) / 1000, timezone.utc
            ).date()
        except (OverflowError, OSError, ValueError):
            warning(
                "ulid_date_out_of_range",
                "ULID timestamp is outside the representable date range",
            )
        else:
            if abs((ulid_date - date.fromisoformat(date_value)).days) > 1:
                warning(
                    "ulid_date_mismatch",
                    "ULID timestamp differs from date by more than one day",
                )

    if store is not None:
        if supersedes is not None:
            target = store.resolve(supersedes)
            if target is None:
                error(
                    "dangling_reference", f"supersedes does not resolve: {supersedes}"
                )
            elif target.data.get("id") == record_id:
                error("self_supersedes", "a record may not supersede itself")
        if isinstance(relates, list):
            for value in relates:
                if store.resolve(value) is None:
                    error("dangling_reference", f"relates_to does not resolve: {value}")
        if mapping.get("effective_state") == "superseded":
            incoming = any(
                predecessor.data.get("id") == record_id
                for _, predecessor in store.effective_edges()
            )
            if not incoming:
                warning(
                    "superseded_without_successor",
                    "superseded record has no effective successor",
                )
        if check_attestation:
            attestation = store.latest_attestation(record_id)
            if _in_str_set(review_state, {"ratified", "rejected"}):
                if (
                    not attestation
                    or attestation.get("verdict") != review_state
                    or attestation.get("body_sha256") != _body_hash(body)
                ):
                    error(
                        "unattested_review_state",
                        "review state has no matching current-body attestation",
                    )
            elif review_state == "unreviewed" and attestation:
                verdict = attestation.get("verdict", "ratify")
                command = {"ratified": "ratify", "rejected": "reject"}.get(
                    verdict, verdict
                )
                error(
                    "state_behind_attestation",
                    f"run scribe {command} {alias} again to apply the recorded verdict",
                )
    return problems


def _in_str_set(value: Any, options: Any) -> bool:
    """Membership on a set of strings, false (not a crash) for an unhashable value."""
    return isinstance(value, str) and value in options


def _enum(mapping: dict[str, Any], key: str, allowed: set[str], error: Any) -> None:
    if not _in_str_set(mapping.get(key), allowed):
        error("invalid_enum", f"{key} must be one of {', '.join(sorted(allowed))}")


def _nullable_string(mapping: dict[str, Any], key: str, error: Any) -> None:
    if mapping.get(key) is not None and not _is_str(mapping.get(key)):
        error("invalid_type", f"{key} must be a string or null")


def _validate_provenance(value: Any, error: Any) -> None:
    keys = {
        "authored_by",
        "agent",
        "model",
        "session",
        "prompt_ids",
        "trigger",
        "source_messages",
    }
    if not isinstance(value, dict):
        error("invalid_type", "provenance must be a mapping")
        return
    if set(value) != keys:
        error("invalid_provenance", "provenance must contain exactly the required keys")
    if not _in_str_set(value.get("authored_by"), {"human", "agent", "agent-drafted"}):
        error("invalid_enum", "invalid provenance.authored_by")
    if not _in_str_set(
        value.get("trigger"), {"user-prompt", "hook", "automation", "self-initiated"}
    ):
        error("invalid_enum", "invalid provenance.trigger")
    for key in ("agent", "model", "session"):
        if value.get(key) is not None and not _is_str(value.get(key)):
            error("invalid_type", f"provenance.{key} must be a string or null")
    for key in ("prompt_ids", "source_messages"):
        if not _is_list_of_strings(value.get(key)):
            error("invalid_type", f"provenance.{key} must be a list of strings")


def _validate_affects(value: Any, error: Any) -> None:
    if not isinstance(value, list):
        error("invalid_type", "affects must be a list")
        return
    for item in value:
        if (
            not isinstance(item, dict)
            or not {"type", "pattern"} <= set(item)
            or set(item) - {"type", "pattern", "negate"}
        ):
            error(
                "invalid_affects",
                "affects items require type and pattern, with optional negate",
            )
            continue
        kind, pattern, negate = (
            item.get("type"),
            item.get("pattern"),
            item.get("negate", False),
        )
        if not _in_str_set(kind, {"path", "package", "action"}):
            error("invalid_affects", "affects type must be path, package, or action")
        if not _is_str(pattern) or not pattern:
            error("invalid_affects", "affects pattern must be a non-empty string")
        if type(negate) is not bool:
            error("invalid_affects", "affects negate must be boolean")
        if kind == "action" and _is_str(pattern) and not ACTION_RE.fullmatch(pattern):
            error("invalid_action", "action pattern must be a denylist rule name")
        if kind != "path" and negate is True:
            error("negate_on_non_path", "negate is only meaningful for path affects")


def _validate_links(value: Any, error: Any) -> None:
    if not isinstance(value, list):
        error("invalid_type", "implementation_links must be a list")
        return
    for item in value:
        if not isinstance(item, dict) or set(item) != {"commit", "paths"}:
            error(
                "invalid_implementation_link",
                "implementation link requires commit and paths",
            )
        elif (
            not _is_str(item["commit"])
            or not COMMIT_RE.fullmatch(item["commit"])
            or not _is_list_of_strings(item["paths"])
        ):
            error("invalid_implementation_link", "invalid implementation link")


def _validate_verify(value: Any, error: Any, store: Store | None = None) -> None:
    grep_keys = {"id", "engine", "pattern", "paths", "expect", "severity"}
    pytest_keys = {"id", "engine", "target", "expect", "severity"}
    if not isinstance(value, list):
        error("invalid_type", "verify must be a list")
        return
    for item in value:
        if not isinstance(item, dict):
            error(
                "invalid_verify", "verify item must contain exactly the required keys"
            )
            continue
        engine = item.get("engine")
        expected_keys = pytest_keys if engine == "pytest" else grep_keys
        if set(item) != expected_keys:
            error(
                "invalid_verify", "verify item must contain exactly the required keys"
            )
            continue
        if not _is_str(item["id"]) or not VERIFY_ID_RE.fullmatch(item["id"]):
            error(
                "invalid_verify",
                "verify id must contain lowercase letters, digits, or hyphens",
            )
        if engine == "jsonpath":
            error(
                "unsupported_engine",
                "jsonpath is on the README allowlist but not implemented in this release",
            )
        elif engine not in {"grep", "pytest"}:
            error("unknown_engine", f"unknown verify engine: {engine}")
        if not _in_str_set(item["severity"], {"error", "warning"}):
            error("invalid_verify", "verify severity must be error or warning")
        if engine == "pytest":
            if not _in_str_set(item["expect"], {"pass", "fail"}):
                error("invalid_verify", "verify expect must be pass or fail")
            _validate_pytest_target(item.get("target"), error, store)
        else:
            if not _is_str(item["pattern"]):
                error("invalid_verify", "verify pattern must be a string")
            if not _is_list_of_strings(item["paths"]):
                error("invalid_verify", "verify paths must be a list of strings")
            if not _in_str_set(item["expect"], {"match", "no-match"}):
                error("invalid_verify", "verify expect must be match or no-match")


def _validate_pytest_target(target: Any, error: Any, store: Store | None) -> None:
    """`target` must be a pytest node id `path[::name[::name...]]`, plan Q4.

    The path segment (before the first `::`) must exist relative to the repo
    root; that check only runs when a store is available (same limitation as
    `dangling_reference` above).
    """
    if not _is_str(target) or not target:
        error("invalid_verify", "verify target must be a non-empty string")
        return
    parts = target.split("::")
    path = parts[0]
    if (
        not path
        or path.startswith(("/", "~"))
        or any(segment == ".." for segment in path.split("/"))
        or any(not name for name in parts[1:])
    ):
        error(
            "invalid_verify",
            "verify target must look like path or path::name, relative to the repo root",
        )
        return
    if store is not None and not (store.root / path).exists():
        error("invalid_verify", f"verify target path does not exist: {path}")


def _validate_history(value: Any, error: Any) -> None:
    if not isinstance(value, list) or not value:
        error("invalid_history", "history must be a non-empty list")
        return
    previous = ""
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            error("invalid_history", "history entries must be mappings")
            continue
        if (
            not _in_str_set(item.get("event"), HISTORY_EVENTS)
            or not _is_str(item.get("by"))
            or not _valid_datetime(item.get("at"))
        ):
            error("invalid_history", f"invalid history entry at index {index}")
        at = item.get("at")
        if _is_str(at) and previous and at < previous:
            error("history_out_of_order", "history timestamps must be non-decreasing")
        if _is_str(at):
            previous = at
        field = item.get("field")
        if field is not None and not _in_str_set(field, MUTABLE_KEYS):
            error("history_immutable_field", f"history names immutable field: {field}")
        if not _in_str_set(
            item.get("event"), {"proposed", "link_added", "relinked"}
        ) and not {
            "field",
            "old",
            "new",
        } <= set(item):
            error(
                "invalid_history",
                f"history event {item.get('event')} requires field, old, and new",
            )
    if isinstance(value[0], dict) and value[0].get("event") != "proposed":
        error("invalid_history", "first history event must be proposed")


def _validate_body(body: str, title: Any, state: Any, error: Any) -> dict[str, str]:
    lines = body.splitlines()
    h1s = [(i, line[2:]) for i, line in enumerate(lines) if line.startswith("# ")]
    if len(h1s) != 1 or h1s[0][1] != title:
        error("invalid_h1", "body must contain one H1 equal to title")
    h2s = [(i, line[3:]) for i, line in enumerate(lines) if line.startswith("## ")]
    names = [name for _, name in h2s]
    allowed = set(SECTIONS) | {"Attempted and failed"}
    for name in names:
        if name not in allowed:
            error("unexpected_section", f"unexpected H2 section: {name}")
    expected = (
        SECTIONS[:-1]
        + (["Attempted and failed"] if "Attempted and failed" in names else [])
        + ["Evidence"]
    )
    if names != expected:
        error(
            "invalid_section_order",
            "required H2 sections are missing, duplicated, or out of order",
        )
    sections: dict[str, str] = {}
    for position, (start, name) in enumerate(h2s):
        end = h2s[position + 1][0] if position + 1 < len(h2s) else len(lines)
        sections[name] = "\n".join(lines[start + 1 : end]).strip()
    for name in SECTIONS:
        if not sections.get(name, "").strip():
            error("empty_section", f"section must be non-empty: {name}")
    if h1s and not any(
        line.startswith(">") and line[1:].strip()
        for line in lines[h1s[0][0] + 1 : h2s[0][0] if h2s else len(lines)]
    ):
        error(
            "missing_y_statement", "a blockquoted Y-statement is required after the H1"
        )
    evidence = sections.get("Evidence", "")
    if not any(
        line.startswith(">") and line[1:].strip() for line in evidence.splitlines()
    ):
        error("missing_evidence_quote", "Evidence must contain a non-empty blockquote")
    options = sections.get("Options considered", "")
    table_lines = [
        line.strip() for line in options.splitlines() if line.strip().startswith("|")
    ]
    header = "| Option | For | Against | Evidence | Why rejected |"
    if not table_lines or table_lines[0] != header or len(table_lines) < 4:
        error(
            "invalid_options_table",
            "Options considered requires the exact header and at least two data rows",
        )
    else:
        rows = table_lines[2:]
        chosen = 0
        valid_rows = 0
        for row in rows:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            if len(cells) == 5:
                valid_rows += 1
                chosen += cells[-1] == "chosen"
        if valid_rows < 2 or chosen != 1:
            error(
                "invalid_options_table",
                "Options considered needs at least two rows and exactly one chosen row",
            )
    return sections
