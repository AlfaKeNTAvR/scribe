import io
import json
import os
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import scribe
from scribe.config import gates_mode
from scribe.hooks import launcher
from scribe.hooks.launcher import Verdict, run_advisory, run_gate
from scribe.state import ERROR_LOG_MAX_BYTES, error_log_path, log_hook_error

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "hooks"
HOOK_ARGS_PREFIX = [
    "-I",
    "-S",
    "${CLAUDE_PLUGIN_ROOT}/hooks/supervise.py",
    "hook",
]

RunHook = Callable[..., subprocess.CompletedProcess[str]]


def load_fixture(name: str, cwd: Path) -> dict:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    payload["cwd"] = str(cwd)
    return payload


def state_file(root: Path) -> Path:
    return root / ".claude" / "scribe" / "state.json"


# --- manifest and registration ---------------------------------------------


def test_every_manifest_states_the_same_version() -> None:
    """A stale marketplace version strands installed copies.

    Claude Code caches an installed plugin under its version, so publishing
    new skills without moving the marketplace entry leaves users on the old
    copy with no sign that anything changed.
    """
    marketplace = json.loads(
        (PROJECT_ROOT / ".claude-plugin" / "marketplace.json").read_text()
    )
    entry = next(item for item in marketplace["plugins"] if item["name"] == "scribe")
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert entry["version"] == scribe.__version__
    assert f'version = "{scribe.__version__}"' in pyproject


def test_plugin_manifest_fields() -> None:
    manifest = json.loads((PROJECT_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "scribe"
    assert manifest["version"] == scribe.__version__
    assert manifest["author"]["name"] == "Nikita Boguslavskii"
    assert manifest["description"]
    # Published from a public marketplace, so the entry says who owns it and
    # under what terms (D-260910-use-apache-license-not-mit).
    assert manifest["license"] == "Apache-2.0"
    assert manifest["homepage"].startswith("https://")


def test_hooks_json_every_handler_is_exec_form() -> None:
    registration = json.loads((PROJECT_ROOT / "hooks" / "hooks.json").read_text())
    events = registration["hooks"]
    assert set(events) == {
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "TaskCompleted",
        "Stop",
    }
    seen_events: set[str] = set()
    for event_name, entries in events.items():
        for entry in entries:
            for handler in entry["hooks"]:
                assert handler["type"] == "command"
                assert handler["command"] == "python3"
                assert handler["args"][: len(HOOK_ARGS_PREFIX)] == HOOK_ARGS_PREFIX
                assert isinstance(handler["timeout"], int)
                hook_event = handler["args"][len(HOOK_ARGS_PREFIX)]
                assert hook_event in launcher.HOOK_MODULES
                seen_events.add(hook_event)
                if entry.get("matcher") == "Edit|Write":
                    assert handler["timeout"] == 1
                    assert hook_event == "pre-tool-use-edit"
    assert seen_events == set(launcher.HOOK_MODULES)
    matchers = {entry.get("matcher") for entry in events["PreToolUse"]}
    assert matchers == {"Edit|Write", "ExitPlanMode", "Bash|PowerShell"}
    assert "matcher" not in events["SessionStart"][0]
    assert events["SessionStart"][0]["hooks"][0]["timeout"] == 120


# --- fail-open ---------------------------------------------------------------


def test_malformed_stdin_exits_zero_silently(run_hook: RunHook, tmp_repo: Path) -> None:
    raw = (FIXTURES / "malformed.txt").read_text(encoding="utf-8")
    result = run_hook("session-start", raw, tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not state_file(tmp_repo).exists()


def test_empty_stdin_exits_zero_silently(run_hook: RunHook, tmp_repo: Path) -> None:
    result = run_hook("user-prompt-submit", "", tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_unknown_event_exits_zero(run_hook: RunHook, tmp_repo: Path) -> None:
    result = run_hook(
        "no-such-event", load_fixture("session_start.json", tmp_repo), tmp_repo
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert "unknown hook event" in result.stderr


def test_raising_handler_is_logged_and_exits_zero(
    tmp_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = load_fixture("session_start.json", tmp_repo)

    def explode(_: dict) -> None:
        raise RuntimeError("boom")

    assert run_advisory(explode, payload, event="session-start") == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    log = error_log_path(tmp_repo).read_text(encoding="utf-8")
    assert "scribe: session-start failed: RuntimeError: boom" in log


def test_debug_env_mirrors_failure_to_stderr(
    tmp_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCRIBE_DEBUG", "1")

    def explode(_: dict) -> None:
        raise ValueError("visible")

    assert (
        run_advisory(explode, load_fixture("session_start.json", tmp_repo), event="x")
        == 0
    )
    assert "scribe: x failed: ValueError: visible" in capsys.readouterr().err


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_read_only_state_dir_fails_open(run_hook: RunHook, tmp_repo: Path) -> None:
    scribe_dir = tmp_repo / ".claude" / "scribe"
    scribe_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        result = run_hook(
            "user-prompt-submit",
            load_fixture("user_prompt_with_refs.json", tmp_repo),
            tmp_repo,
        )
    finally:
        scribe_dir.chmod(stat.S_IRWXU)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not state_file(tmp_repo).exists()


def test_state_dir_as_regular_file_fails_open(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    scribe_dir = tmp_repo / ".claude" / "scribe"
    scribe_dir.rmdir()
    scribe_dir.write_text("not a directory\n", encoding="utf-8")
    result = run_hook(
        "session-start",
        load_fixture("session_start.json", tmp_repo),
        tmp_repo,
        env={"SCRIBE_DEBUG": "1"},
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert "scribe: session-start failed" in result.stderr
    assert scribe_dir.read_text(encoding="utf-8") == "not a directory\n"


def test_error_log_keeps_newest_half_above_limit(tmp_repo: Path) -> None:
    path = error_log_path(tmp_repo)
    line = ("old " * 24 + "\n").encode()
    path.write_bytes(line * (ERROR_LOG_MAX_BYTES // len(line) + 200))
    assert path.stat().st_size > ERROR_LOG_MAX_BYTES
    log_hook_error(tmp_repo, "scribe: newest")
    content = path.read_text(encoding="utf-8")
    assert path.stat().st_size < ERROR_LOG_MAX_BYTES
    assert content.endswith("scribe: newest\n")
    assert content.startswith("old ")


def test_read_payload_rejects_non_object() -> None:
    assert launcher.read_payload(io.StringIO("[1, 2]")) is None
    assert launcher.read_payload(io.StringIO("   ")) is None
    assert launcher.read_payload(io.StringIO('{"a": 1}')) == {"a": 1}


# --- gates ---------------------------------------------------------------------


def deny(_: dict) -> Verdict:
    return Verdict(
        False, "scribe: denied for the test", {"event": "gate_verdict", "tool": "Bash"}
    )


def gate_log_lines(root: Path) -> list[dict]:
    path = root / ".claude" / "scribe" / "gate-log.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_run_gate_shadow_logs_deny_and_exits_zero(
    tmp_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = load_fixture("session_start.json", tmp_repo)
    assert gates_mode(tmp_repo) == "shadow"
    assert run_gate(deny, gates_mode(tmp_repo), payload) == 0
    assert capsys.readouterr() == ("", "")
    (entry,) = gate_log_lines(tmp_repo)
    assert entry["verdict"] == "deny"
    assert entry["event"] == "gate_verdict"
    assert entry["reason"] == "scribe: denied for the test"
    assert "at" in entry


def test_run_gate_enforce_exits_two_with_reason(
    tmp_repo: Path, set_config: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    set_config(tmp_repo, SCRIBE_GATES="enforce")
    assert gates_mode(tmp_repo) == "enforce"
    payload = load_fixture("session_start.json", tmp_repo)
    assert run_gate(deny, gates_mode(tmp_repo), payload) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "scribe: denied for the test" in captured.err
    assert gate_log_lines(tmp_repo)[0]["verdict"] == "deny"


def test_run_gate_allow_exits_zero_in_enforce(
    tmp_repo: Path, set_config: Callable[..., Path]
) -> None:
    set_config(tmp_repo, SCRIBE_GATES="enforce")
    payload = load_fixture("session_start.json", tmp_repo)
    assert run_gate(lambda _: Verdict(True), "enforce", payload) == 0
    assert gate_log_lines(tmp_repo)[0]["verdict"] == "allow"


@pytest.mark.parametrize("mode", ["shadow", "enforce"])
def test_run_gate_crash_exits_zero_and_is_loud(
    tmp_repo: Path, capsys: pytest.CaptureFixture[str], mode: str
) -> None:
    def explode(_: dict) -> Verdict:
        raise RuntimeError("gate crash")

    assert (
        run_gate(
            explode, mode, load_fixture("session_start.json", tmp_repo), event="gate"
        )
        == 0
    )
    assert "scribe: gate failed: RuntimeError: gate crash" in capsys.readouterr().err
    assert "gate crash" in error_log_path(tmp_repo).read_text(encoding="utf-8")


def test_unknown_gate_mode_value_falls_back_to_shadow(
    tmp_repo: Path, set_config: Callable[..., Path]
) -> None:
    set_config(tmp_repo, SCRIBE_GATES="yes please")
    assert gates_mode(tmp_repo) == "shadow"
    (tmp_repo / ".claude" / "scribe" / "config.json").write_text(
        "{broken", encoding="utf-8"
    )
    assert gates_mode(tmp_repo) == "shadow"
    assert gates_mode(None) == "shadow"


def test_stub_gate_and_reconcile_events_are_silent(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    payload = load_fixture("session_start.json", tmp_repo)
    for event in ("pre-tool-use-edit", "gate", "reconcile"):
        result = run_hook(event, payload, tmp_repo)
        assert (result.returncode, result.stdout, result.stderr) == (0, "", ""), event
    assert not (tmp_repo / ".claude" / "scribe" / "gate-log.jsonl").exists()
