"""T20: `scribe doctor` (D-260910-keep-python3-launcher-add-doctor).

Every check here exists because the matching failure is silent in production:
a hook that cannot launch, a uv that cannot start, a shim git will not run.
The tests assert that doctor turns each one into a `fail` line and a non-zero
exit, and that a healthy install stays quiet.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from scribe import doctor
from scribe.doctor import FAIL, OK, WARN, Check

RunCli = Callable[..., tuple[int, str, str]]


def _statuses(checks: list[Check], prefix: str) -> list[str]:
    return [check.status for check in checks if check.name.startswith(prefix)]


def test_hook_commands_reads_every_command_from_hooks_json(tmp_path: Path) -> None:
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "python3"}]}
                    ],
                    "PreToolUse": [
                        {
                            "matcher": "Edit",
                            "hooks": [
                                {"type": "command", "command": "python3"},
                                {"type": "command", "command": "other"},
                            ],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    commands, problem = doctor.hook_commands(tmp_path)
    assert problem is None
    assert commands == ["python3", "other"]


def test_hook_commands_reports_unreadable_and_malformed_manifests(
    tmp_path: Path,
) -> None:
    commands, problem = doctor.hook_commands(tmp_path)
    assert commands == []
    assert problem is not None and "cannot read" in problem

    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "hooks.json").write_text("{not json", encoding="utf-8")
    commands, problem = doctor.hook_commands(tmp_path)
    assert commands == []
    assert problem is not None and "not valid JSON" in problem


def test_missing_hook_interpreter_is_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "hooks.json").write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": "python3"}]}]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    checks = doctor.check_hook_interpreter(tmp_path)
    assert _statuses(checks, "hook interpreter") == [FAIL]
    assert "not on PATH" in checks[0].detail


def test_supervisor_that_exits_zero_after_skipping_is_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fail-open path: exit 0 with no version means scribe never ran."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "hooks.json").write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": "python3"}]}]}}),
        encoding="utf-8",
    )
    (hooks / "supervise.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        doctor.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="scribe: --version skipped (uv could not start: no such file)\n",
        ),
    )
    checks = doctor.check_supervisor_runs(tmp_path)
    assert [check.status for check in checks] == [FAIL]
    assert "uv could not start" in checks[0].detail


def test_supervisor_that_answers_with_a_version_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "hooks.json").write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": "python3"}]}]}}),
        encoding="utf-8",
    )
    (hooks / "supervise.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        doctor.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="scribe 0.1.0 (/plugin)\n", stderr=""
        ),
    )
    checks = doctor.check_supervisor_runs(tmp_path)
    assert [check.status for check in checks] == [OK]


@pytest.mark.skipif(os.name == "nt", reason="posix executable bit")
def test_shim_problems_cover_ownership_mode_and_shebang(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign"
    foreign.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert "not scribe-managed" in (doctor._shim_problem(foreign) or "")

    unreadable = tmp_path / "missing"
    assert doctor._shim_problem(unreadable) is not None

    managed = tmp_path / "managed"
    managed.write_text(
        "#!/usr/bin/env -S python3 -I -S\n# scribe-managed v1\n", encoding="utf-8"
    )
    assert "not executable" in (doctor._shim_problem(managed) or "")
    managed.chmod(0o755)
    assert doctor._shim_problem(managed) is None

    absent = tmp_path / "absent"
    absent.write_text(
        "#!/usr/bin/env -S pythonX -I -S\n# scribe-managed v1\n", encoding="utf-8"
    )
    absent.chmod(0o755)
    assert "not on PATH" in (doctor._shim_problem(absent) or "")


def test_settings_check_wants_the_deny_rule(tmp_path: Path) -> None:
    assert doctor.check_settings(tmp_path)[0].status == WARN
    settings = tmp_path / ".claude"
    settings.mkdir()
    (settings / "settings.json").write_text(
        json.dumps({"permissions": {"deny": []}}), encoding="utf-8"
    )
    assert doctor.check_settings(tmp_path)[0].status == FAIL
    (settings / "settings.json").write_text(
        json.dumps({"permissions": {"deny": [doctor.DENY_RULE]}}), encoding="utf-8"
    )
    assert doctor.check_settings(tmp_path)[0].status == OK


def test_gitignored_settings_are_reported_as_unreachable(tmp_repo: Path) -> None:
    """A deny rule inside an ignored .claude/ protects one machine only.

    Reported from a Windows install where the repository root was itself a
    .claude directory, so `scribe init` wrote a nested settings file that the
    repository's own .gitignore covered.
    """
    settings = tmp_repo / ".claude"
    settings.mkdir(exist_ok=True)
    (settings / "settings.json").write_text(
        json.dumps({"permissions": {"deny": [doctor.DENY_RULE]}}), encoding="utf-8"
    )
    assert [check.status for check in doctor.check_settings(tmp_repo)] == [OK]

    (tmp_repo / ".gitignore").write_text(".claude/\n", encoding="utf-8")
    checks = doctor.check_settings(tmp_repo)
    assert [check.status for check in checks] == [OK, WARN]
    assert "never reaches a teammate" in checks[1].detail


def test_stale_index_is_a_failure(tmp_repo: Path) -> None:
    (tmp_repo / "docs" / "decisions" / "INDEX.md").write_text(
        "stale\n", encoding="utf-8"
    )
    checks = doctor.check_store(tmp_repo)
    assert [check.status for check in checks if check.name == "index"] == [FAIL]


def test_healthy_store_passes(tmp_repo: Path, run_cli: RunCli) -> None:
    run_cli(["index"], tmp_repo)
    checks = doctor.check_store(tmp_repo)
    assert [check.status for check in checks] == [OK, OK]


def test_doctor_json_reports_every_check_and_the_exit_code(
    tmp_repo: Path, run_cli: RunCli
) -> None:
    code, stdout, _ = run_cli(["doctor", "--json"], tmp_repo)
    payload = json.loads(stdout)
    assert payload["ok"] == (code == 0)
    assert {"name", "status", "detail"} <= set(payload["checks"][0])
    assert any(
        check["name"].startswith("hook interpreter") for check in payload["checks"]
    )


def test_render_ends_with_a_counted_summary() -> None:
    lines = doctor.render(
        [Check("a", OK, "fine"), Check("b", FAIL, "broken"), Check("c", WARN, "eh")]
    )
    assert lines[0].startswith("ok")
    assert "3 checks, 1 failed, 1 warnings" in lines[-1]
