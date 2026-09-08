from collections.abc import Callable
from pathlib import Path


def test_version(
    run_cli: Callable[..., tuple[int, str, str]],
    tmp_repo: Path,
) -> None:
    code, stdout, stderr = run_cli(["--version"], tmp_repo)
    project_root = Path(__file__).resolve().parents[1]

    assert code == 0
    assert stdout == f"scribe 0.1.0 ({project_root})\n"
    assert stderr == ""
