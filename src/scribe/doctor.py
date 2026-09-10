"""`scribe doctor`: report what an installation got wrong, in one line per check.

Every failure mode this command looks for is silent by construction. A Claude
Code hook whose command cannot be launched is a non-blocking error: the
transcript carries one `hook error` line and the session continues without
scribe. `hooks/supervise.py` deliberately swallows every uv failure and exits
0, so a broken uv also looks exactly like a working install. The git hook
shims fail open for the same reason. Nothing here changes state; the command
only reads and reports, and exits 1 when any check fails.

The decision behind this command, including why `hooks/hooks.json` still names
`python3` on every platform, is `D-260910-keep-python3-launcher-add-doctor`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scribe import gitutil
from scribe.init_repo import (
    DENY_RULE,
    HOOK_NAMES,
    MARKER,
    SETTINGS_PATH,
    configured_hooks_path,
    shim_interpreter,
)
from scribe.store import Store

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HOOKS_JSON = Path("hooks") / "hooks.json"
SUPERVISOR = Path("hooks") / "supervise.py"
CONFIG_PATH = Path(".claude") / "scribe" / "config.json"
SMOKE_TIMEOUT_SECONDS = 60

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass(frozen=True)
class Check:
    """One reported line: what was checked, how it went, and what was found."""

    name: str
    status: str
    detail: str

    def render(self) -> str:
        return f"{self.status:<4}  {self.name}: {self.detail}"


def _tool_version(executable: str, flag: str = "--version") -> str:
    """First line of the tool's own version output, or an empty string."""
    try:
        completed = subprocess.run(
            [executable, flag],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0] if output else ""


def hook_commands(plugin_root: Path) -> tuple[list[str], str | None]:
    """The distinct `command` values in hooks.json, plus a parse error if any."""
    path = plugin_root / HOOKS_JSON
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [], f"cannot read {HOOKS_JSON.as_posix()}: {exc}"
    except ValueError as exc:
        return [], f"{HOOKS_JSON.as_posix()} is not valid JSON: {exc}"
    commands: list[str] = []
    events = payload.get("hooks")
    if not isinstance(events, dict):
        return [], f"{HOOKS_JSON.as_posix()} has no hooks object"
    for matchers in events.values():
        for matcher in matchers if isinstance(matchers, list) else []:
            entries = matcher.get("hooks") if isinstance(matcher, dict) else None
            for entry in entries if isinstance(entries, list) else []:
                command = entry.get("command") if isinstance(entry, dict) else None
                if isinstance(command, str) and command not in commands:
                    commands.append(command)
    return commands, None


def check_plugin_root(plugin_root: Path) -> list[Check]:
    """The plugin's own files: hooks.json parses, the supervisor is present."""
    checks = [Check("plugin root", OK, str(plugin_root))]
    if not (plugin_root / SUPERVISOR).is_file():
        checks.append(Check("supervisor", FAIL, f"{SUPERVISOR.as_posix()} is missing"))
    commands, problem = hook_commands(plugin_root)
    if problem is not None:
        checks.append(Check("hooks.json", FAIL, problem))
        return checks
    checks.append(
        Check(
            "hooks.json",
            OK,
            f"{len(commands)} distinct hook command(s): {', '.join(commands)}",
        )
    )
    return checks


def check_hook_interpreter(plugin_root: Path) -> list[Check]:
    """Every interpreter hooks.json names has to resolve on PATH.

    Claude Code resolves the `command` field through PATH with no platform
    branch available in the hook schema, so an install on a machine whose
    Python is called something else runs no scribe hooks at all.
    """
    commands, problem = hook_commands(plugin_root)
    if problem is not None:
        return []
    checks: list[Check] = []
    for command in commands:
        resolved = shutil.which(command)
        if resolved is None:
            checks.append(
                Check(
                    f"hook interpreter ({command})",
                    FAIL,
                    f"{command} is not on PATH, so Claude Code cannot launch the "
                    "scribe hooks; put one there (on Windows the Microsoft Store "
                    "Python provides python3.exe, or add a python3.cmd shim)",
                )
            )
            continue
        version = _tool_version(command, "-V")
        checks.append(
            Check(
                f"hook interpreter ({command})",
                OK,
                f"{resolved}{f' ({version})' if version else ''}",
            )
        )
    return checks


def check_uv() -> list[Check]:
    """`uv` runs every scribe entry point, including from inside the shims."""
    name = os.environ.get("SCRIBE_UV", "uv")
    resolved = shutil.which(name)
    if resolved is None:
        return [
            Check(
                f"uv ({name})",
                FAIL,
                f"{name} is not on PATH; every hook and git hook will skip",
            )
        ]
    version = _tool_version(name)
    return [
        Check(f"uv ({name})", OK, f"{resolved}{f' ({version})' if version else ''}")
    ]


def check_supervisor_runs(plugin_root: Path) -> list[Check]:
    """End to end: the interpreter starts the supervisor, which reaches scribe.

    This is the check the other ones exist to explain. It runs the real
    supervisor the way Claude Code runs it, asking scribe for its version. A
    fail-open skip prints `scribe: ... skipped` and still exits 0, so the
    exit code alone proves nothing and the output has to be read.
    """
    commands, problem = hook_commands(plugin_root)
    if problem is not None:
        return []
    supervisor = plugin_root / SUPERVISOR
    checks: list[Check] = []
    for command in commands:
        if shutil.which(command) is None:
            continue
        try:
            completed = subprocess.run(
                [command, "-I", "-S", str(supervisor), "--version"],
                capture_output=True,
                text=True,
                timeout=SMOKE_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            checks.append(
                Check(
                    "supervisor smoke test",
                    FAIL,
                    f"no answer in {SMOKE_TIMEOUT_SECONDS}s; a hook would be killed "
                    "at its timeout and scribe would skip",
                )
            )
            continue
        except OSError as exc:
            checks.append(Check("supervisor smoke test", FAIL, str(exc)))
            continue
        answer = completed.stdout.strip()
        if completed.returncode == 0 and answer.startswith("scribe "):
            checks.append(Check("supervisor smoke test", OK, answer))
            continue
        skipped = next(
            (
                line
                for line in completed.stderr.splitlines()
                if line.startswith("scribe: ")
            ),
            completed.stderr.strip().splitlines()[-1]
            if completed.stderr.strip()
            else f"exit {completed.returncode}",
        )
        checks.append(
            Check(
                "supervisor smoke test",
                FAIL,
                f"scribe did not answer, so every hook fails open silently: {skipped}",
            )
        )
    return checks


def _shim_problem(path: Path) -> str | None:
    """Why an installed git hook would not run, or None when it looks sound."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return str(exc)
    if MARKER not in text:
        return "present but not scribe-managed (another tool owns it)"
    if os.name != "nt" and not os.access(path, os.X_OK):
        return "not executable, so git will ignore it"
    first = text.splitlines()[0] if text else ""
    if first.startswith("#!"):
        interpreter = first[2:].split()
        # `#!/usr/bin/env -S python3 -I -S`: the interpreter is the first
        # argument after env and its flags, not env itself.
        if interpreter and interpreter[0].endswith("env"):
            rest = [word for word in interpreter[1:] if not word.startswith("-")]
            name = rest[0] if rest else ""
        else:
            name = Path(interpreter[0]).name if interpreter else ""
        if name and shutil.which(name) is None:
            return f"shebang names {name}, which is not on PATH"
    return None


def check_git_hooks(root: Path) -> list[Check]:
    """The four shims `scribe init` writes, and whether git would run them."""
    configured = configured_hooks_path(root)
    if configured is not None:
        hooks_dir = Path(configured)
        if not hooks_dir.is_absolute():
            hooks_dir = root / hooks_dir
    else:
        found = gitutil.git_path_hooks(root)
        if found is None:
            return [Check("git hooks", FAIL, "git rev-parse --git-path hooks failed")]
        hooks_dir = found
    missing = []
    problems = []
    for name in HOOK_NAMES:
        target = hooks_dir / name
        if not target.exists():
            missing.append(name)
            continue
        problem = _shim_problem(target)
        if problem is not None:
            problems.append(f"{name}: {problem}")
    checks = []
    if missing == list(HOOK_NAMES):
        checks.append(
            Check(
                "git hooks",
                WARN,
                f"none installed in {hooks_dir}; run scribe init in this repository",
            )
        )
    elif missing:
        checks.append(
            Check("git hooks", FAIL, f"missing from {hooks_dir}: {', '.join(missing)}")
        )
    else:
        checks.append(Check("git hooks", OK, f"all four installed in {hooks_dir}"))
    checks.extend(Check("git hook", FAIL, problem) for problem in problems)
    if configured is not None:
        checks.append(
            Check(
                "core.hooksPath",
                WARN,
                f"set to {configured}; git ignores .git/hooks entirely",
            )
        )
    return checks


def check_settings(root: Path) -> list[Check]:
    """`.claude/settings.json` is what stops an agent editing the ledger."""
    path = root / SETTINGS_PATH
    if not path.is_file():
        return [
            Check(
                "settings deny rule",
                WARN,
                f"{SETTINGS_PATH.as_posix()} is missing; nothing stops an agent "
                "editing RATIFICATIONS.jsonl",
            )
        ]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [Check("settings deny rule", FAIL, f"{SETTINGS_PATH.as_posix()}: {exc}")]
    permissions = payload.get("permissions")
    rules = permissions.get("deny") if isinstance(permissions, dict) else None
    if not (isinstance(rules, list) and DENY_RULE in rules):
        return [
            Check(
                "settings deny rule",
                FAIL,
                f"{DENY_RULE} is not in {SETTINGS_PATH.as_posix()}; re-run scribe init",
            )
        ]
    checks = [Check("settings deny rule", OK, DENY_RULE)]
    if _is_git_ignored(root, SETTINGS_PATH):
        checks.append(
            Check(
                "settings reach",
                WARN,
                f"{SETTINGS_PATH.as_posix()} is git-ignored, so the deny rule "
                "protects this machine only and never reaches a teammate or "
                "another checkout",
            )
        )
    return checks


def _is_git_ignored(root: Path, relative: Path) -> bool:
    """True when git would refuse to track the path, so it cannot be shared."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", relative.as_posix()],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def check_config(root: Path) -> list[Check]:
    path = root / CONFIG_PATH
    if not path.is_file():
        return [
            Check(
                "config", WARN, f"{CONFIG_PATH.as_posix()} is missing (defaults used)"
            )
        ]
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [Check("config", FAIL, f"{CONFIG_PATH.as_posix()}: {exc}")]
    return [Check("config", OK, CONFIG_PATH.as_posix())]


def check_store(root: Path) -> list[Check]:
    """The decision store itself: records load, and INDEX.md is current."""
    from scribe.index import locked_check_index

    store = Store(root)
    if not store.path.is_dir():
        return [
            Check(
                "decision store",
                WARN,
                "docs/decisions does not exist in this repository",
            )
        ]
    try:
        records = store.records(refresh=True)
    except (OSError, ValueError) as exc:
        return [Check("decision store", FAIL, f"records cannot be loaded: {exc}")]
    checks = [Check("decision store", OK, f"{len(records)} records in {store.path}")]
    _, up_to_date, acquired = locked_check_index(store)
    if not acquired:
        checks.append(Check("index", WARN, "ledger lock busy; INDEX.md not checked"))
    elif up_to_date:
        checks.append(Check("index", OK, "INDEX.md is current"))
    else:
        checks.append(Check("index", FAIL, "INDEX.md is stale; run scribe index"))
    return checks


def run_doctor(start: str | Path = ".") -> tuple[int, list[Check]]:
    """Every check, in install order: the plugin first, the repository second."""
    checks = check_plugin_root(PLUGIN_ROOT)
    checks.extend(check_hook_interpreter(PLUGIN_ROOT))
    checks.extend(check_uv())
    checks.extend(check_supervisor_runs(PLUGIN_ROOT))
    root = gitutil.toplevel(start)
    if root is None:
        checks.append(
            Check(
                "repository",
                WARN,
                "not inside a git repository; repository checks skipped",
            )
        )
    else:
        checks.append(Check("repository", OK, str(root)))
        checks.extend(check_git_hooks(root))
        checks.extend(check_settings(root))
        checks.extend(check_config(root))
        checks.extend(check_store(root))
    code = 1 if any(check.status == FAIL for check in checks) else 0
    return code, checks


def render(checks: list[Check], platform: str = os.name) -> list[str]:
    """The printed report: one line per check, then a one-line summary."""
    lines = [check.render() for check in checks]
    failures = sum(check.status == FAIL for check in checks)
    warnings = sum(check.status == WARN for check in checks)
    lines.append(
        f"{len(checks)} checks, {failures} failed, {warnings} warnings "
        f"(hook interpreter on this platform: {shim_interpreter(platform)})"
    )
    return lines
