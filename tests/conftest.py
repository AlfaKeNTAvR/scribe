import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from scribe.cli import main


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
        shutil.copy2(source, decisions / source.name)
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
