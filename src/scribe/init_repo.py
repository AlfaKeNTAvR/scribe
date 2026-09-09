"""`scribe init`: install the git hook shims and the repo-side files (plan 5.5).

Everything here is idempotent: a path that already carries what init would
write is reported as `unchanged`. Files init did not write are never replaced
without `--force` (hooks get a `<name>.pre-scribe` backup), the config file is
never overwritten at all (F21), and the CI workflow only appears with an
explicit `--ci-source` (F6). Preflight (F28) runs before the first write.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import scribe
from scribe import gitutil
from scribe.config import DEFAULTS, config_path, write_config
from scribe.index import write_index
from scribe.store import Store

HOOK_NAMES = ("prepare-commit-msg", "commit-msg", "post-commit")
MARKER = "# scribe-managed"
TEMPLATES = Path(__file__).resolve().parent / "templates"
SHIM_TEMPLATE = TEMPLATES / "githook_shim.py"
WORKFLOW_TEMPLATE = TEMPLATES / "scribe-check.yml"
WORKFLOW_PATH = Path(".github") / "workflows" / "scribe-check.yml"
SETTINGS_PATH = Path(".claude") / "settings.json"
GITIGNORE_LINE = ".claude/scribe/"
DENY_RULE = "Edit(/docs/decisions/RATIFICATIONS.jsonl)"
LEGACY_DENY_RULES = (
    "Write(docs/decisions/RATIFICATIONS.jsonl)",
    "Edit(docs/decisions/RATIFICATIONS.jsonl)",
)
URL_PREFIXES = ("git+https://", "https://")
NO_CI_HINT = (
    "scribe: no CI workflow written; re-run with --ci-source "
    "<git+https URL or path> once the scribe package is reachable from CI"
)
PLUGIN_ROOT = Path(scribe.__file__).resolve().parents[2]


class InitError(Exception):
    """A condition that stops init before it writes anything."""


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    foreign_hook_kept: bool = False
    written: list[str] = field(default_factory=list)

    def note(self, verb: str, display: str) -> None:
        self.lines.append(f"scribe init: {verb} {display}")
        if verb in ("wrote", "replaced"):
            self.written.append(display)


# --- rendering ---------------------------------------------------------------


def shim_interpreter(platform: str = os.name) -> str:
    return "python" if platform == "nt" else "python3"


def render_shim(hook: str, plugin_root: Path, platform: str = os.name) -> str:
    text = SHIM_TEMPLATE.read_text(encoding="utf-8")
    substitutions = {
        "SHEBANG": f"/usr/bin/env {shim_interpreter(platform)}",
        "PLUGIN_ROOT": str(plugin_root),
        "HOOK": hook,
    }
    for key, value in substitutions.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def check_command(spec: str) -> tuple[str, str | None]:
    """The `scribe check` invocation for a `--ci-source` spec, plus a warning."""
    if spec.startswith(URL_PREFIXES):
        return f'uvx --from "{spec}" scribe check', None
    if spec == ".":
        return "uv run --frozen --project . scribe check", None
    if not Path(spec).exists():
        raise InitError(
            f"scribe: --ci-source {spec} is neither a git+https/https URL "
            "nor an existing path"
        )
    warning = (
        f"scribe: warning: --ci-source {spec} is a filesystem path; the workflow "
        "only works where that path exists"
    )
    return f"uv run --frozen --project {spec} scribe check", warning


def render_workflow(spec: str) -> tuple[str, str | None]:
    command, warning = check_command(spec)
    text = WORKFLOW_TEMPLATE.read_text(encoding="utf-8")
    return text.replace("{{SCRIBE_CHECK_COMMAND}}", command), warning


# --- preflight ---------------------------------------------------------------


def preflight(platform: str = os.name) -> None:
    """F28: `uv` and the shim interpreter must resolve, or hooks would silently skip."""
    for tool in ("uv", shim_interpreter(platform)):
        if shutil.which(tool) is None:
            raise InitError(
                f"scribe: preflight failed: {tool} not on PATH; "
                "hooks would silently skip"
            )


def configured_hooks_path(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), "config", "--get", "core.hooksPath"],
        text=True,
        capture_output=True,
        check=False,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def chaining_instructions(root: Path, hooks_path: str) -> str:
    calls = "\n".join(
        f"    {name}: uv run --frozen --project {PLUGIN_ROOT} "
        f'scribe git-hook {name} "$@"'
        for name in HOOK_NAMES
    )
    return (
        f"scribe: core.hooksPath is set to {hooks_path}; nothing installed.\n"
        f"  Either re-run `scribe init --hooks-dir {hooks_path}` to install the "
        "shims there (replacing hooks of the same name only with --force),\n"
        f"  or chain scribe from the hooks in {hooks_path} by adding to each:\n"
        f"{calls}\n"
        f"  (repository: {root})"
    )


def resolve_hooks_dir(root: Path, hooks_dir: str | None) -> Path:
    if hooks_dir is not None:
        return Path(hooks_dir).resolve()
    configured = configured_hooks_path(root)
    if configured is not None:
        raise InitError(chaining_instructions(root, configured))
    found = gitutil.git_path_hooks(root)
    if found is None:
        raise InitError("scribe: git rev-parse --git-path hooks failed")
    return found


# --- the individual writes ---------------------------------------------------


def display(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def is_scribe_managed(path: Path) -> bool:
    try:
        return MARKER in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def install_hook(
    hooks_dir: Path, name: str, root: Path, force: bool, report: Report
) -> None:
    target = hooks_dir / name
    rendered = render_shim(name, PLUGIN_ROOT)
    shown = display(root, target)
    if target.exists():
        if is_scribe_managed(target):
            if target.read_text(encoding="utf-8", errors="replace") == rendered:
                report.note("unchanged", shown)
                return
        elif not force:
            report.lines.append(
                f"scribe: existing {name} hook kept; use --force to replace "
                f"(a backup {name}.pre-scribe is written)"
            )
            report.foreign_hook_kept = True
            return
        else:
            backup = hooks_dir / f"{name}.pre-scribe"
            target.replace(backup)
            hooks_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8", newline="\n")
            target.chmod(0o755)
            report.note("replaced", f"{shown} (previous hook saved as {backup.name})")
            return
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8", newline="\n")
    target.chmod(0o755)
    report.note("wrote", shown)


def ensure_gitignore(root: Path, report: Report) -> None:
    target = root / ".gitignore"
    shown = display(root, target)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    if GITIGNORE_LINE in (line.strip() for line in existing.splitlines()):
        report.note("unchanged", shown)
        return
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    target.write_text(existing + prefix + GITIGNORE_LINE + "\n", encoding="utf-8")
    report.note("wrote", shown)


def ensure_config(root: Path, report: Report) -> None:
    """F21: the safe defaults are written once and never overwritten."""
    target = config_path(root)
    if target.exists():
        report.note("unchanged", display(root, target))
        return
    write_config(root, **DEFAULTS)
    report.note("wrote", display(root, target))


def ensure_workflow(root: Path, spec: str | None, force: bool, report: Report) -> None:
    if spec is None:
        report.lines.append(NO_CI_HINT)
        return
    rendered, warning = render_workflow(spec)
    if warning:
        report.lines.append(warning)
    target = root / WORKFLOW_PATH
    shown = display(root, target)
    if target.exists():
        if is_scribe_managed(target):
            if target.read_text(encoding="utf-8") == rendered:
                report.note("unchanged", shown)
                return
        elif not force:
            report.lines.append(
                f"scribe init: kept {shown} (not scribe-managed; use --force to replace)"
            )
            return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8", newline="\n")
    report.note("wrote", shown)


def deny_rules_with_scribe(rules: list[Any]) -> list[Any]:
    kept = [rule for rule in rules if rule not in LEGACY_DENY_RULES]
    if DENY_RULE not in kept:
        kept.append(DENY_RULE)
    return kept


def ensure_settings(root: Path, report: Report) -> None:
    """F5: `.claude/settings.json` denies edits to the attestation ledger."""
    target = root / SETTINGS_PATH
    shown = display(root, target)
    settings: dict[str, Any] = {}
    if target.exists():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            report.lines.append(f"scribe init: skipped {shown} (invalid JSON: {exc})")
            return
        if not isinstance(loaded, dict):
            report.lines.append(
                f"scribe init: skipped {shown} (top level is not an object)"
            )
            return
        settings = loaded
    permissions = settings.get("permissions")
    if permissions is None:
        permissions = {}
    if not isinstance(permissions, dict):
        report.lines.append(
            f"scribe init: skipped {shown} (permissions is not an object)"
        )
        return
    deny = permissions.get("deny")
    if deny is None:
        deny = []
    if not isinstance(deny, list):
        report.lines.append(
            f"scribe init: skipped {shown} (permissions.deny is not a list)"
        )
        return
    updated_deny = deny_rules_with_scribe(deny)
    if target.exists() and updated_deny == deny:
        report.note("unchanged", shown)
        return
    updated = {**settings, "permissions": {**permissions, "deny": updated_deny}}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    report.note("wrote", shown)


def ensure_store(root: Path, report: Report) -> None:
    store = Store(root)
    shown = display(root, store.path)
    if store.path.is_dir():
        report.note("unchanged", shown)
        return
    store.path.mkdir(parents=True)
    (store.path / "RATIFICATIONS.jsonl").write_text("", encoding="utf-8")
    write_index(store)
    report.note("wrote", shown)


def follow_ups(root: Path, report: Report) -> list[str]:
    candidates = (
        ".gitignore",
        SETTINGS_PATH.as_posix(),
        WORKFLOW_PATH.as_posix(),
        "docs/decisions",
    )
    to_commit = [path for path in candidates if (root / path).exists()]
    lines = ["scribe init: next steps"]
    if to_commit:
        lines.append(f"  - commit the new files: git add {' '.join(to_commit)}")
    if (root / WORKFLOW_PATH).exists():
        lines.append(
            "  - add branch protection on the default branch requiring the "
            "scribe-check job"
        )
    return lines


# --- entry point -------------------------------------------------------------


def run_init(
    start: str | Path = ".",
    *,
    force: bool = False,
    hooks_dir: str | None = None,
    ci_source: str | None = None,
) -> tuple[int, list[str]]:
    """Exit code and the lines `scribe init` prints, in plan 5.5 order."""
    root = gitutil.toplevel(start)
    if root is None:
        return 1, ["scribe: not inside a git repository"]
    try:
        preflight()
        target_hooks_dir = resolve_hooks_dir(root, hooks_dir)
        if ci_source is not None:
            check_command(ci_source)
    except InitError as exc:
        return 1, [str(exc)]
    report = Report()
    for name in HOOK_NAMES:
        install_hook(target_hooks_dir, name, root, force, report)
    ensure_gitignore(root, report)
    ensure_config(root, report)
    ensure_workflow(root, ci_source, force, report)
    ensure_settings(root, report)
    ensure_store(root, report)
    report.lines.extend(follow_ups(root, report))
    return (1 if report.foreign_hook_kept else 0), report.lines
