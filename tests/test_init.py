"""T14: `scribe init` and the shim it installs (plan 5, 5.5, F5, F6, F21, F28)."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from scribe.init_repo import DENY_RULE, HOOK_NAMES, NO_CI_HINT

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
SPEC_PLAIN = FIXTURES / "new_spec.json"
SPEC_SUPERSEDES = FIXTURES / "check_spec_supersedes.json"
WORKFLOW = Path(".github") / "workflows" / "scribe-check.yml"
SETTINGS = Path(".claude") / "settings.json"
CONFIG = Path(".claude") / "scribe" / "config.json"
FOREIGN_HOOK = "#!/bin/sh\nexit 0\n"

RunCli = Callable[..., tuple[int, str, str]]


def test_ci_source_filesystem_path_is_one_shell_argument(tmp_path: Path) -> None:
    from scribe.init_repo import check_command

    source = tmp_path / "plugin's path; literal $(name)"
    source.mkdir()
    command, warning = check_command(str(source))
    assert shlex.split(command) == [
        "uv",
        "run",
        "--frozen",
        "--project",
        str(source),
        "scribe",
        "check",
    ]
    assert warning is not None


# --- helpers -----------------------------------------------------------------


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=check,
    )


def hooks_dir(repo: Path) -> Path:
    return repo / ".git" / "hooks"


def init(run_cli: RunCli, repo: Path, *args: str) -> tuple[int, str]:
    code, stdout, _ = run_cli(["init", *args], repo)
    return code, stdout


def init_with_ci(run_cli: RunCli, repo: Path, *args: str) -> tuple[int, str]:
    return init(run_cli, repo, "--ci-source", str(PROJECT_ROOT), *args)


def snapshot(repo: Path) -> dict[str, bytes]:
    """Every file under the repo, .git/hooks included, keyed by relative path."""
    files: dict[str, bytes] = {}
    for path in repo.rglob("*"):
        if path.is_file():
            files[path.relative_to(repo).as_posix()] = path.read_bytes()
    return files


def run_line(repo: Path) -> str:
    text = (repo / WORKFLOW).read_text(encoding="utf-8")
    lines = [
        line.strip() for line in text.splitlines() if line.strip().startswith("- run:")
    ]
    assert len(lines) == 1, text
    return lines[0].removeprefix("- run:").strip()


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


# --- the happy path (AT clauses 1 to 5) --------------------------------------


def test_init_installs_four_managed_executable_hooks(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    code, stdout = init_with_ci(run_cli, tmp_repo)

    assert code == 0, stdout
    for name in HOOK_NAMES:
        hook = hooks_dir(tmp_repo) / name
        text = hook.read_text(encoding="utf-8")
        # -I -S isolates the very first interpreter start from a broken
        # PYTHONHOME/PYTHONPATH; see init_repo.shim_shebang and
        # test_supervise.test_installed_shim_survives_a_broken_pythonhome.
        assert text.startswith("#!/usr/bin/env -S python3 -I -S\n")
        assert "# scribe-managed" in text
        assert f'HOOK = "{name}"' in text
        assert f'PLUGIN_ROOT = r"{PROJECT_ROOT}"' in text
        assert "import supervise" in text
        assert 'supervise.run(["git-hook", HOOK]' in text
        assert os.access(hook, os.X_OK)
        assert f"scribe init: wrote .git/hooks/{name}" in stdout
    assert set(HOOK_NAMES) == {
        "prepare-commit-msg",
        "commit-msg",
        "post-commit",
        "post-rewrite",
    }


def test_init_appends_the_scratch_dir_to_gitignore(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    (tmp_repo / ".gitignore").write_text("*.pyc", encoding="utf-8")

    assert init_with_ci(run_cli, tmp_repo)[0] == 0

    assert (tmp_repo / ".gitignore").read_text(
        encoding="utf-8"
    ) == "*.pyc\n.claude/scribe/\n"


def test_init_writes_the_safe_config_and_never_overwrites_it(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    assert init_with_ci(run_cli, tmp_repo)[0] == 0
    config = json.loads((tmp_repo / CONFIG).read_text(encoding="utf-8"))
    assert config == {
        "version": 1,
        "SCRIBE_GATES": "shadow",
        "SCRIBE_COMMIT_MSG": "warn",
    }

    (tmp_repo / CONFIG).write_text('{"version": 1, "SCRIBE_GATES": "enforce"}\n')
    code, stdout = init_with_ci(run_cli, tmp_repo, "--force")

    assert code == 0
    assert f"scribe init: unchanged {CONFIG.as_posix()}" in stdout
    assert json.loads((tmp_repo / CONFIG).read_text(encoding="utf-8")) == {
        "version": 1,
        "SCRIBE_GATES": "enforce",
    }


def test_init_writes_a_workflow_whose_run_line_invokes_the_ci_source(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    code, stdout = init_with_ci(run_cli, tmp_repo)

    assert code == 0
    assert "scribe: warning: --ci-source" in stdout  # a path only works where it exists
    text = (tmp_repo / WORKFLOW).read_text(encoding="utf-8")
    assert text.startswith("# scribe-managed v1\n")
    workflow = yaml.safe_load(text)
    steps = workflow["jobs"]["scribe-check"]["steps"]
    assert steps[1] == {"uses": "astral-sh/setup-uv@v10"}
    assert steps[2]["run"].startswith(
        f"uv run --frozen --project {PROJECT_ROOT} scribe check"
    )
    assert steps[2]["run"].endswith('--base "origin/${{ github.base_ref }}"')


def test_a_url_ci_source_renders_uvx(run_cli: RunCli, tmp_repo: Path) -> None:
    url = "git+https://github.com/example/scribe@v0.1.0"
    code, stdout = init(run_cli, tmp_repo, "--ci-source", url)

    assert code == 0
    assert "scribe: warning" not in stdout
    assert run_line(tmp_repo).startswith(f'uvx --from "{url}" scribe check')


def test_a_bogus_ci_source_writes_nothing(run_cli: RunCli, tmp_repo: Path) -> None:
    before = snapshot(tmp_repo)

    code, stdout = init(run_cli, tmp_repo, "--ci-source", "/no/such/path")

    assert code == 1
    assert "neither a git+https/https URL nor an existing path" in stdout
    assert snapshot(tmp_repo) == before


def test_init_writes_exactly_the_deny_rule(run_cli: RunCli, tmp_repo: Path) -> None:
    assert init_with_ci(run_cli, tmp_repo)[0] == 0

    settings = json.loads((tmp_repo / SETTINGS).read_text(encoding="utf-8"))

    assert settings == {"permissions": {"deny": [DENY_RULE]}}
    assert DENY_RULE == "Edit(/docs/decisions/RATIFICATIONS.jsonl)"


def test_init_keeps_other_settings_and_drops_the_legacy_rules(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    (tmp_repo / SETTINGS).write_text(
        json.dumps(
            {
                "model": "opus",
                "permissions": {
                    "allow": ["Bash(git status)"],
                    "deny": [
                        "Write(docs/decisions/RATIFICATIONS.jsonl)",
                        "Bash(rm -rf *)",
                        "Edit(docs/decisions/RATIFICATIONS.jsonl)",
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    assert init_with_ci(run_cli, tmp_repo)[0] == 0

    settings = json.loads((tmp_repo / SETTINGS).read_text(encoding="utf-8"))
    assert settings == {
        "model": "opus",
        "permissions": {
            "allow": ["Bash(git status)"],
            "deny": ["Bash(rm -rf *)", DENY_RULE],
        },
    }


def test_invalid_settings_json_is_skipped_with_a_message(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    (tmp_repo / SETTINGS).write_text("{not json", encoding="utf-8")

    code, stdout = init_with_ci(run_cli, tmp_repo)

    assert code == 0
    assert "scribe init: skipped .claude/settings.json (invalid JSON" in stdout
    assert (tmp_repo / SETTINGS).read_text(encoding="utf-8") == "{not json"


def test_init_creates_an_empty_store_when_missing(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    shutil.rmtree(tmp_repo / "docs")

    code, stdout = init_with_ci(run_cli, tmp_repo)

    assert code == 0
    assert "scribe init: wrote docs/decisions" in stdout
    assert (tmp_repo / "docs" / "decisions" / "RATIFICATIONS.jsonl").read_bytes() == b""
    index = (tmp_repo / "docs" / "decisions" / "INDEX.md").read_text(encoding="utf-8")
    assert index.startswith("# Decision index")
    assert run_cli(["index", "--check"], tmp_repo)[0] == 0


# --- AT clauses 6 and 7: no --ci-source, idempotence -------------------------


def test_without_ci_source_no_workflow_is_written_and_the_hint_is_printed(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    code, stdout = init(run_cli, tmp_repo)

    assert code == 0
    assert not (tmp_repo / WORKFLOW).exists()
    assert not (tmp_repo / ".github").exists()
    assert NO_CI_HINT in stdout
    assert NO_CI_HINT.startswith(
        "scribe: no CI workflow written; re-run with --ci-source"
    )


def test_init_next_steps_hint_the_subdirectory_start_limitation(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    """V21: scribe init reminds the user where the deny rule actually loads."""
    code, stdout = init(run_cli, tmp_repo)

    assert code == 0
    assert "scribe init: next steps" in stdout
    assert f"start Claude Code sessions at the repository root ({tmp_repo})" in stdout
    assert (
        "RATIFICATIONS.jsonl deny rule in .claude/settings.json does not load "
        "for a session started in a subdirectory"
    ) in stdout
    assert "Edit(**/docs/decisions/RATIFICATIONS.jsonl) to your user settings" in stdout


def test_second_run_is_unchanged_everywhere(run_cli: RunCli, tmp_repo: Path) -> None:
    assert init_with_ci(run_cli, tmp_repo)[0] == 0
    before = snapshot(tmp_repo)

    code, stdout = init_with_ci(run_cli, tmp_repo)

    assert code == 0
    assert snapshot(tmp_repo) == before
    statuses = [
        line for line in stdout.splitlines() if line.startswith("scribe init: ")
    ]
    statuses = [
        line for line in statuses if not line.startswith("scribe init: next steps")
    ]
    assert statuses, stdout
    assert all(line.startswith("scribe init: unchanged ") for line in statuses), stdout
    reported = {line.removeprefix("scribe init: unchanged ") for line in statuses}
    assert reported == {
        *(f".git/hooks/{name}" for name in HOOK_NAMES),
        ".gitignore",
        CONFIG.as_posix(),
        WORKFLOW.as_posix(),
        SETTINGS.as_posix(),
        "docs/decisions",
    }


# --- AT clause 8: a foreign hook, kept then replaced under --force -----------


def test_foreign_commit_msg_is_kept_with_exit_one(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    hooks_dir(tmp_repo).mkdir(parents=True, exist_ok=True)
    (hooks_dir(tmp_repo) / "commit-msg").write_text(FOREIGN_HOOK, encoding="utf-8")

    code, stdout = init_with_ci(run_cli, tmp_repo)

    assert code == 1
    assert (
        "scribe: existing commit-msg hook kept; use --force to replace "
        "(a backup commit-msg.pre-scribe is written)"
    ) in stdout
    assert (hooks_dir(tmp_repo) / "commit-msg").read_text(
        encoding="utf-8"
    ) == FOREIGN_HOOK
    assert not (hooks_dir(tmp_repo) / "commit-msg.pre-scribe").exists()
    for name in ("prepare-commit-msg", "post-commit", "post-rewrite"):
        assert "# scribe-managed" in (hooks_dir(tmp_repo) / name).read_text(
            encoding="utf-8"
        )


def test_force_replaces_the_foreign_hook_and_keeps_a_backup(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    hooks_dir(tmp_repo).mkdir(parents=True, exist_ok=True)
    (hooks_dir(tmp_repo) / "commit-msg").write_text(FOREIGN_HOOK, encoding="utf-8")

    code, stdout = init_with_ci(run_cli, tmp_repo, "--force")

    assert code == 0
    assert "scribe init: replaced .git/hooks/commit-msg" in stdout
    assert "# scribe-managed" in (hooks_dir(tmp_repo) / "commit-msg").read_text(
        encoding="utf-8"
    )
    assert os.access(hooks_dir(tmp_repo) / "commit-msg", os.X_OK)
    backup = hooks_dir(tmp_repo) / "commit-msg.pre-scribe"
    assert backup.read_text(encoding="utf-8") == FOREIGN_HOOK


# --- AT clause 9: core.hooksPath -------------------------------------------


def test_core_hooks_path_set_exits_one_with_chaining_instructions(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    git(tmp_repo, "config", "core.hooksPath", ".githooks")
    before = snapshot(tmp_repo)

    code, stdout = init_with_ci(run_cli, tmp_repo)

    assert code == 1
    assert "core.hooksPath is set to .githooks" in stdout
    assert "scribe init --hooks-dir .githooks" in stdout
    for name in HOOK_NAMES:
        assert f'scribe git-hook {name} "$@"' in stdout
    assert snapshot(tmp_repo) == before


def test_hooks_dir_installs_into_the_given_directory(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    git(tmp_repo, "config", "core.hooksPath", ".githooks")

    code, stdout = init_with_ci(run_cli, tmp_repo, "--hooks-dir", ".githooks")

    assert code == 0, stdout
    for name in HOOK_NAMES:
        assert "# scribe-managed" in (tmp_repo / ".githooks" / name).read_text(
            encoding="utf-8"
        )
        assert not (hooks_dir(tmp_repo) / name).exists()


# --- AT clause 10: preflight (F28) ------------------------------------------


def test_preflight_without_uv_exits_one_and_writes_nothing(
    run_cli: RunCli, tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_which = shutil.which
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd, *a, **k: None if cmd == "uv" else real_which(cmd, *a, **k),
    )
    before = snapshot(tmp_repo)

    code, stdout = init_with_ci(run_cli, tmp_repo)

    assert code == 1
    assert stdout.strip() == (
        "scribe: preflight failed: uv not on PATH; hooks would silently skip"
    )
    assert snapshot(tmp_repo) == before
    assert not (tmp_repo / SETTINGS).exists()
    assert not (tmp_repo / CONFIG).exists()
    assert not (tmp_repo / WORKFLOW).exists()
    assert not any((hooks_dir(tmp_repo) / name).exists() for name in HOOK_NAMES)


def test_preflight_without_the_shim_interpreter_names_it(
    run_cli: RunCli, tmp_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_which = shutil.which
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd, *a, **k: None if cmd == "python3" else real_which(cmd, *a, **k),
    )

    code, stdout = init_with_ci(run_cli, tmp_repo)

    assert code == 1
    assert "preflight failed: python3 not on PATH" in stdout


# --- AT clause 11: the installed shim, end to end ---------------------------


def test_installed_shim_adds_a_decision_trailer_to_a_real_commit(
    run_cli: RunCli, tmp_repo: Path
) -> None:
    assert shutil.which("uv") is not None, "uv must be on PATH for the shim test"
    assert init_with_ci(run_cli, tmp_repo)[0] == 0
    git(tmp_repo, "add", "-A")
    subprocess.run(
        ["git", "-C", str(tmp_repo), "commit", "-q", "-m", "chore: baseline"],
        env={**os.environ, "SCRIBE_SKIP_HOOKS": "1"},
        check=True,
    )
    code, stdout, _ = run_cli(["new", "--spec", str(SPEC_PLAIN)], tmp_repo)
    assert code == 0, stdout
    record_path = tmp_repo / stdout.strip()
    alias = record_path.stem
    ulid = yaml.safe_load(record_path.read_text(encoding="utf-8").split("---")[1])["id"]

    git(tmp_repo, "add", "docs/decisions")
    result = git(tmp_repo, "commit", "-q", "-m", "docs: Record a decision")

    assert result.returncode == 0, result.stderr
    message = git(tmp_repo, "log", "-1", "--format=%B").stdout
    trailers = [line for line in message.splitlines() if line.startswith("Decision:")]
    assert trailers == [f"Decision: {alias} {ulid}"]
    assert "scribe:" not in result.stderr, result.stderr
    assert not (tmp_repo / ".claude" / "scribe" / "hook-errors.log").exists()


# --- AT clause 12: F6 end to end ---------------------------------------------


@pytest.fixture
def ci_ledger(tmp_repo: Path, run_cli: RunCli) -> tuple[Path, list[str]]:
    """`main` with the three records, the init output, and the workflow's command."""
    git(tmp_repo, "checkout", "-q", "-b", "main")
    assert init_with_ci(run_cli, tmp_repo)[0] == 0
    assert run_cli(["index"], tmp_repo)[0] == 0
    commit_all(tmp_repo, "chore: Bootstrap the ledger")
    command = run_line(tmp_repo)
    expression = '--base "origin/${{ github.base_ref }}"'
    assert command.endswith(expression)
    return tmp_repo, shlex.split(command.replace(expression, "--base main"))


def run_workflow_command(
    repo: Path, argv: list[str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(repo),
        env={**os.environ, "SCRIBE_SKIP_HOOKS": "1"},
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )


def test_workflow_command_fails_on_a_supersede_branch(
    run_cli: RunCli, ci_ledger: tuple[Path, list[str]]
) -> None:
    repo, argv = ci_ledger
    assert argv[:4] == ["uv", "run", "--frozen", "--project"]
    git(repo, "checkout", "-q", "-b", "feat")
    assert run_cli(["new", "--spec", str(SPEC_SUPERSEDES)], repo)[0] == 0
    commit_all(repo, "feat: Supersede the ratified decision")

    result = run_workflow_command(repo, argv)

    assert result.returncode == 1, result.stdout + result.stderr
    assert (
        "supersedes ratified D-260908-unreviewed-may-supersede-ratified"
        in result.stdout
    )


def test_workflow_command_passes_on_an_ordinary_branch(
    run_cli: RunCli, ci_ledger: tuple[Path, list[str]]
) -> None:
    repo, argv = ci_ledger
    git(repo, "checkout", "-q", "-b", "plain")
    assert run_cli(["new", "--spec", str(SPEC_PLAIN)], repo)[0] == 0
    commit_all(repo, "docs: Record an ordinary decision")

    result = run_workflow_command(repo, argv)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "scribe check: ok"
