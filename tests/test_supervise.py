"""Codex V1: `hooks/supervise.py` keeps a broken uv from denying tools or commits.

Every test drives the exact registered command shape (`python3 -I -S
<plugin>/hooks/supervise.py hook <event>`) or the installed git shim, with `uv`
replaced by a fake script on PATH where the failure has to be provoked.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from scribe import protocol

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = PROJECT_ROOT / "hooks" / "supervise.py"
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "hooks"
UV_ERROR = "error: Could not acquire lock for /home/x/.cache/uv: Read-only file system"


def load_fixture(name: str, cwd: Path) -> str:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    payload["cwd"] = str(cwd)
    return json.dumps(payload)


def fake_uv(directory: Path, script: str) -> Path:
    """A `uv` on its own PATH entry that runs `script` (sh) instead of uv."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "uv"
    path.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def path_with(*dirs: Path, uv: bool) -> str:
    """A PATH holding the given dirs, the system dirs and (optionally) the real uv."""
    entries = [str(d) for d in dirs] + ["/usr/bin", "/bin"]
    real_uv = shutil.which("uv")
    if uv and real_uv:
        entries.append(str(Path(real_uv).parent))
    return os.pathsep.join(entries)


def supervise(
    argv: list[str], cwd: Path, payload: str = "", path: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [sys.executable, "-I", "-S", str(SUPERVISOR), *argv],
        input=payload,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )


# --- protocol and registration ----------------------------------------------


def test_marker_constant_matches_the_package() -> None:
    namespace: dict[str, object] = {}
    source = SUPERVISOR.read_text(encoding="utf-8")
    marker_line = next(
        line for line in source.splitlines() if line.startswith("DENY_MARKER")
    )
    exec(marker_line, namespace)  # noqa: S102 - one constant assignment from our own file
    assert namespace["DENY_MARKER"] == protocol.DENY_MARKER


def test_supervisor_is_stdlib_only_and_python38_syntax() -> None:
    source = SUPERVISOR.read_text(encoding="utf-8")
    imports = {
        line.split()[1]
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    }
    assert imports == {"os", "subprocess", "sys"}
    assert "scribe" not in imports
    compile(source, str(SUPERVISOR), "exec", flags=0, dont_inherit=True)


# --- the registered hook command -------------------------------------------


def test_real_uv_still_injects_through_the_supervisor(tmp_repo: Path) -> None:
    result = supervise(
        ["hook", "pre-tool-use-edit"],
        tmp_repo,
        load_fixture("pre_tool_use_edit_match.json", tmp_repo),
    )
    assert result.returncode == 0, result.stderr
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "retrieval candidates" in context


def test_uv_startup_failure_exits_zero_with_one_line(
    tmp_repo: Path, tmp_path: Path
) -> None:
    fake_uv(tmp_path / "bin", f'echo "{UV_ERROR}" >&2\nexit 2\n')
    result = supervise(
        ["hook", "pre-tool-use-edit"],
        tmp_repo,
        load_fixture("pre_tool_use_edit_match.json", tmp_repo),
        path=path_with(tmp_path / "bin", uv=False),
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        f"scribe: hook pre-tool-use-edit skipped (exit 2: {UV_ERROR})"
    ]


def test_missing_uv_exits_zero_with_one_line(tmp_repo: Path, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = supervise(
        ["hook", "user-prompt-submit"],
        tmp_repo,
        load_fixture("user_prompt_submit.json", tmp_repo),
        path=path_with(empty, uv=False),
    )
    assert result.returncode == 0
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith(
        "scribe: hook user-prompt-submit skipped (uv could not start:"
    )


def test_application_crash_exit_code_is_mapped_to_zero(
    tmp_repo: Path, tmp_path: Path
) -> None:
    fake_uv(
        tmp_path / "bin",
        'echo "Traceback (most recent call last):" >&2\n'
        'echo "ModuleNotFoundError: No module named yaml" >&2\nexit 1\n',
    )
    result = supervise(
        ["hook", "gate"], tmp_repo, "{}", path=path_with(tmp_path / "bin", uv=False)
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        "scribe: hook gate skipped (exit 1: ModuleNotFoundError: No module named yaml)"
    ]


def test_deliberate_deny_is_forwarded_without_the_marker(
    tmp_repo: Path, tmp_path: Path
) -> None:
    fake_uv(
        tmp_path / "bin",
        f'echo "{protocol.DENY_MARKER} $SCRIBE_DENY_TOKEN]" >&2\necho "blocked: force push" >&2\nexit 2\n',
    )
    result = supervise(
        ["hook", "gate"], tmp_repo, "{}", path=path_with(tmp_path / "bin", uv=False)
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.splitlines() == ["blocked: force push"]


def test_traceback_marker_impersonation_is_fail_open(
    tmp_repo: Path, tmp_path: Path
) -> None:
    fake_uv(
        tmp_path / "bin",
        'echo "[scribe-deny]" >&2\necho "[scribe-deny wrongtoken]" >&2\nexit 1\n',
    )
    result = supervise(
        ["hook", "gate"], tmp_repo, "{}", path=path_with(tmp_path / "bin", uv=False)
    )
    assert result.returncode == 0


@pytest.mark.parametrize(
    "argv, expected", [(["hook", "gate"], 2), (["git-hook", "commit-msg"], 1)]
)
def test_marker_forces_blocking_status(
    tmp_repo: Path, tmp_path: Path, argv: list[str], expected: int
) -> None:
    fake_uv(
        tmp_path / "bin",
        f'echo "{protocol.DENY_MARKER} $SCRIBE_DENY_TOKEN]" >&2\nexit 0\n',
    )
    result = supervise(argv, tmp_repo, "{}", path=path_with(tmp_path / "bin", uv=False))
    assert result.returncode == expected


def test_success_output_is_forwarded_verbatim(tmp_repo: Path, tmp_path: Path) -> None:
    fake_uv(tmp_path / "bin", 'printf \'{"ok": true}\\n\'\necho "note" >&2\nexit 0\n')
    result = supervise(
        ["hook", "gate"], tmp_repo, "{}", path=path_with(tmp_path / "bin", uv=False)
    )
    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        '{"ok": true}\n',
        "note\n",
    )


def test_enforce_deny_end_to_end_through_the_supervisor(
    tmp_repo: Path, set_config
) -> None:
    set_config(tmp_repo, SCRIBE_GATES="enforce")
    result = supervise(
        ["hook", "gate"], tmp_repo, load_fixture("gate_bash_force_push.json", tmp_repo)
    )
    assert result.returncode == 2
    assert "irreversible-action denylist" in result.stderr
    assert protocol.DENY_MARKER not in result.stderr


def test_stdin_is_handed_to_uv_unread(tmp_repo: Path, tmp_path: Path) -> None:
    fake_uv(tmp_path / "bin", "cat\nexit 0\n")
    result = supervise(
        ["hook", "gate"],
        tmp_repo,
        '{"cwd": "x"}',
        path=path_with(tmp_path / "bin", uv=False),
    )
    assert result.stdout == '{"cwd": "x"}'


# --- the installed git shim --------------------------------------------------


@pytest.fixture
def shim_repo(run_cli, tmp_repo: Path) -> Path:
    """tmp_repo with `scribe init` applied and a baseline commit made with hooks skipped."""
    assert shutil.which("uv") is not None, "uv must be on PATH to install the shims"
    code, stdout, _ = run_cli(["init"], tmp_repo)
    assert code == 0, stdout
    subprocess.run(["git", "-C", str(tmp_repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_repo), "commit", "-q", "-m", "chore: baseline"],
        env={**os.environ, "SCRIBE_SKIP_HOOKS": "1"},
        check=True,
    )
    return tmp_repo


def git_commit(repo: Path, message: str, path: str) -> subprocess.CompletedProcess[str]:
    subprocess.run(["git", "-C", str(repo), "add", "--", path], check=True)
    return subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", message],
        env={**os.environ, "PATH": path},
        text=True,
        capture_output=True,
        check=False,
    )


def test_installed_shim_lets_the_commit_through_when_uv_is_broken(
    shim_repo: Path, tmp_path: Path
) -> None:
    fake_uv(tmp_path / "bin", f'echo "{UV_ERROR}" >&2\nexit 2\n')
    (shim_repo / "notes.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(shim_repo), "add", "notes.md"], check=True)
    result = subprocess.run(
        ["git", "-C", str(shim_repo), "commit", "-q", "-m", "docs: Notes"],
        env={**os.environ, "PATH": path_with(tmp_path / "bin", uv=False)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    skipped = [
        line for line in result.stderr.splitlines() if "skipped (exit 2:" in line
    ]
    assert {line.split()[1] for line in skipped} >= {"git-hook"}
    assert "prepare-commit-msg" in result.stderr and "post-commit" in result.stderr


def test_installed_shim_forwards_a_deliberate_commit_rejection(
    shim_repo: Path, set_config
) -> None:
    set_config(shim_repo, SCRIBE_COMMIT_MSG="enforce")
    (shim_repo / "notes.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(shim_repo), "add", "notes.md"], check=True)
    result = subprocess.run(
        [
            "git",
            "-C",
            str(shim_repo),
            "commit",
            "-q",
            "-m",
            "docs: Notes\n\nDecision: D-260101-nope",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "commit rejected" in result.stderr
    assert protocol.DENY_MARKER not in result.stderr
