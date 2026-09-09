"""Wall-clock budget of the PreToolUse injection hook (plan 7 item 5, F19).

Measures the whole registered command, `python3 -I <plugin>/hooks/supervise.py
hook pre-tool-use-edit` (which runs `uv run --frozen --project <plugin> scribe
hook pre-tool-use-edit`), against a store of 100 generated records plus the
three real ones. The two measurements bypass pytest capture so `-q` shows
them too. Fails, never skips, when `uv` or `python3` is not on PATH.
"""

import json
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path

import pytest
from scribe.record import Record

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "hooks"
GENERATED_RECORDS = 100
WARM_RUNS = 3
WARM_MEDIAN_LIMIT_S = 1.0
BYTECODE_COLD_LIMIT_S = 2.0
ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_records(store: Path, count: int) -> None:
    """Clone a real record `count` times with distinct ids, aliases and affects."""
    source = sorted(store.glob("D-*.md"))[0]
    template = Record.load(source)
    for index in range(count):
        record = Record(template.path, dict(template.data), template.body)
        alias = f"D-2609{index % 30 + 1:02d}-generated-{index:03d}"
        suffix = ULID_ALPHABET[index // 32] + ULID_ALPHABET[index % 32]
        record.path = store / f"{alias}.md"
        record.data.update(
            {
                "id": f"01M21BV91NZSW1HMJ127KZ{suffix}0",
                "alias": alias,
                "title": f"Generated decision {index:03d}",
                "review_state": "unreviewed",
                "ratified_by": None,
                "ratified_at": None,
                "effective_state": "implemented" if index % 2 else "proposed",
                "affects": [
                    {"type": "path", "pattern": f"src/module{index:03d}/**"},
                    {"type": "path", "pattern": "src/scribe/*.py"},
                    {
                        "type": "path",
                        "pattern": f"tests/test_{index:03d}.py",
                        "negate": True,
                    },
                ],
                "supersedes": None,
            }
        )
        record.save()


def hook_payload(root: Path) -> str:
    payload = json.loads(
        (FIXTURES / "pre_tool_use_edit_match.json").read_text(encoding="utf-8")
    )
    payload["cwd"] = str(root)
    payload["tool_input"]["file_path"] = str(root / "src" / "scribe" / "index.py")
    return json.dumps(payload)


def timed_hook_run(
    python3: str, root: Path, payload: str, extra_env: dict[str, str] | None = None
) -> tuple[float, subprocess.CompletedProcess[str]]:
    started = time.perf_counter()
    result = subprocess.run(
        [
            python3,
            "-I",
            str(PROJECT_ROOT / "hooks" / "supervise.py"),
            "hook",
            "pre-tool-use-edit",
        ],
        input=payload,
        cwd=str(root),
        env={**os.environ, **(extra_env or {})},
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    return time.perf_counter() - started, result


def assert_injected(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stderr
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "These are retrieval candidates" in context


def remove_bytecode_caches(root: Path) -> int:
    removed = 0
    for cache in root.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
        removed += 1
    return removed


def test_injection_hook_wall_time(
    tmp_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if shutil.which("uv") is None:
        pytest.fail("uv is not on PATH; the timing test needs the real launcher")
    uv = shutil.which("python3")
    if uv is None:
        pytest.fail("python3 is not on PATH; the registered command needs it")
    store = tmp_repo / "docs" / "decisions"
    generate_records(store, GENERATED_RECORDS)
    assert len(list(store.glob("D-*.md"))) == GENERATED_RECORDS + 3
    payload = hook_payload(tmp_repo)

    warm_times = []
    for _ in range(WARM_RUNS):
        elapsed, result = timed_hook_run(uv, tmp_repo, payload)
        assert_injected(result)
        warm_times.append(elapsed)
    warm_median = statistics.median(warm_times)
    with capsys.disabled():
        print(f"\nwarm median: {warm_median:.3f} s")
    assert warm_median < WARM_MEDIAN_LIMIT_S, warm_times

    remove_bytecode_caches(PROJECT_ROOT / "src")
    cold, result = timed_hook_run(
        uv, tmp_repo, payload, {"PYTHONDONTWRITEBYTECODE": "1"}
    )
    assert_injected(result)
    with capsys.disabled():
        print(f"bytecode-cold: {cold:.3f} s")
    assert cold < BYTECODE_COLD_LIMIT_S
