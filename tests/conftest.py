import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from scribe.cli import main
from scribe.config import write_config
from scribe.record import Record

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    git_home = tmp_path / "home"
    git_home.mkdir()
    monkeypatch.setenv("HOME", str(git_home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    settings = {
        "user.name": "Scribe Tests",
        "user.email": "scribe-tests@example.invalid",
        "commit.gpgsign": "false",
    }
    for key, value in settings.items():
        subprocess.run(
            ["git", "-C", str(root), "config", key, value],
            check=True,
        )
    subprocess.run(
        ["git", "-C", str(root), "config", "--unset-all", "core.hooksPath"],
        check=False,
    )

    decisions = root / "docs" / "decisions"
    decisions.mkdir(parents=True)
    for source in (PROJECT_ROOT / "docs" / "decisions").glob("D-*.md"):
        # These fresh repositories start before implementation. Dogfood relink
        # updates the source ledger with commits that do not exist here; keep
        # its body and ratification, but reset implementation data in this copy.
        record = Record.load(source)
        record.path = decisions / source.name
        record.data["effective_state"] = "proposed"
        record.data["implementation_links"] = []
        record.data["history"] = [
            entry for entry in record.data["history"]
            if entry.get("event") not in {"implemented", "link_added", "relinked"}
        ]
        record.save()
    shutil.copy2(
        PROJECT_ROOT / "docs" / "decisions" / "RATIFICATIONS.jsonl",
        decisions / "RATIFICATIONS.jsonl",
    )
    (root / ".claude" / "scribe").mkdir(parents=True)
    return root


@pytest.fixture
def run_cli(capsys: pytest.CaptureFixture[str]) -> Callable[..., tuple[int, str, str]]:
    def run(
        args: Sequence[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        previous_cwd = Path.cwd()
        previous_env = os.environ.copy()
        code = 0
        try:
            os.chdir(cwd)
            if env:
                os.environ.update(env)
            try:
                result = main(args)
                code = result if result is not None else 0
            except SystemExit as exc:
                code = int(exc.code or 0)
        finally:
            os.chdir(previous_cwd)
            os.environ.clear()
            os.environ.update(previous_env)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


@pytest.fixture
def run_hook() -> Callable[..., subprocess.CompletedProcess[str]]:
    """Run `python -m scribe hook <event>` with a JSON (or raw) payload on stdin."""

    def run(
        event: str,
        payload: dict | str | bytes,
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if isinstance(payload, bytes):
            stdin_text = payload.decode("utf-8", errors="replace")
        elif isinstance(payload, str):
            stdin_text = payload
        else:
            stdin_text = json.dumps(payload)
        return subprocess.run(
            [sys.executable, "-m", "scribe", "hook", event],
            input=stdin_text,
            cwd=str(cwd),
            env={**os.environ, **(env or {})},
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )

    return run


@pytest.fixture
def set_config() -> Callable[..., Path]:
    """Write switches such as SCRIBE_GATES="enforce" into <root>/.claude/scribe/config.json."""

    def write(root: Path, **switches: str) -> Path:
        return write_config(root, **switches)

    return write
