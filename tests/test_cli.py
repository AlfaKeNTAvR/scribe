from collections.abc import Callable
from pathlib import Path

import scribe


def test_version(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    code, stdout, stderr = run_cli(["--version"], tmp_repo)
    project_root = Path(__file__).resolve().parents[1]

    assert code == 0
    assert stdout == f"scribe {scribe.__version__} ({project_root})\n"
    assert stderr == ""
