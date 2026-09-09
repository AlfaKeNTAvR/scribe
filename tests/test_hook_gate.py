import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from scribe import policy
from scribe.hooks import pre_tool_use_gate, reconcile
from scribe.hooks.launcher import POLICY_ADVISORY, POLICY_GATE
from scribe.record import Record
from scribe.state import load_state, session_entry, update_state
from scribe.store import Store

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "hooks"
RECORD_FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "records"
GATE_SESSION = "session_fixture_gate"

RunHook = Callable[..., subprocess.CompletedProcess[str]]
SetConfig = Callable[..., Path]


def load_fixture(name: str, cwd: Path) -> dict:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    payload["cwd"] = str(cwd)
    return payload


def gate_log_path(root: Path) -> Path:
    return root / ".claude" / "scribe" / "gate-log.jsonl"


def gate_log_lines(root: Path) -> list[dict]:
    path = gate_log_path(root)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def session_state(root: Path, session_id: str = GATE_SESSION) -> dict:
    return load_state(root)["sessions"][session_id]


def write_ratified_action_record(root: Path, rule_name: str) -> None:
    """A ratified one-way-door record whose affects claims `rule_name` (plan 4.7 item 2)."""
    record = Record.load(RECORD_FIXTURES / "action_affects_valid.md")
    record.path = root / "docs" / "decisions" / "D-260908-allow-the-action.md"
    record.data.update(
        {
            "id": "01M21BVB05VVF1XV54Y66AWV6F",
            "alias": "D-260908-allow-the-action",
            "review_state": "ratified",
            "ratified_by": "@tester",
            "ratified_at": "2026-09-08T21:00:00Z",
            "reversibility": "one-way-door",
            "affects": [{"type": "action", "pattern": rule_name}],
        }
    )
    record.save()
    attestation = {
        "id": record.data["id"],
        "alias": record.data["alias"],
        "verdict": "ratified",
        "by": "@tester",
        "at": "2026-09-08T21:00:00Z",
        "via": "cli",
        "body_sha256": record.body_sha256(),
    }
    (root / "docs" / "decisions" / "RATIFICATIONS.jsonl").write_text(
        json.dumps(attestation) + "\n", encoding="utf-8"
    )


def seed_session(root: Path, **fields: object) -> None:
    def mutate(state: dict) -> None:
        session_entry(state, GATE_SESSION).update(fields)

    update_state(root, mutate)


# --- policy: denylist ---------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git push --force origin main", "git-push-force"),
        ("git push -f", "git-push-force"),
        ("git push origin main --force", "git-push-force"),
        ("git status && git push --force", "git-push-force"),
        ("git branch -D feature", "git-branch-delete-force"),
        ("git reset --hard origin/main", "git-reset-hard-remote"),
        ("rm -rf /tmp/scratch", "rm-rf-outside-worktree"),
        ("rm -fr ~/scratch", "rm-rf-outside-worktree"),
        ("rm -r -f ../sibling", "rm-rf-outside-worktree"),
        ("rm -rf build /tmp/other", "rm-rf-outside-worktree"),
        ("sudo rm -rf --no-preserve-root /", "rm-rf-outside-worktree"),
        ("alembic upgrade head", "alembic-migrate"),
        ("npx prisma migrate deploy", "prisma-migrate-deploy"),
        ("flyway -url=jdbc:postgresql://db migrate", "flyway-migrate"),
        ("terraform apply -auto-approve", "terraform-apply-destroy"),
        ("terraform destroy", "terraform-apply-destroy"),
        ("kubectl apply -f deploy.yaml", "kubectl-apply-delete"),
        ("kubectl delete pod web-0", "kubectl-apply-delete"),
        ("helm upgrade --install web ./chart", "helm-install-upgrade"),
        ("docker push registry/app:1.0", "docker-push"),
        ("npm publish --access public", "npm-publish"),
        ("& npm.cmd publish", "npm-publish"),
        ("cargo publish", "cargo-publish"),
        ("twine upload dist/*", "twine-upload"),
        ("uv publish", "uv-publish"),
        ("gh release create v1.0.0 --notes x", "gh-release-create"),
        ("gh pr merge 12 --squash", "gh-pr-merge"),
        ("curl -X POST https://api.example.invalid/items", "http-write"),
        ("curl -XDELETE https://api.example.invalid/items/1", "http-write"),
        ("curl --data @body.json https://api.example.invalid", "http-write"),
        ("http --request put https://api.example.invalid", "http-write"),
    ],
)
def test_denylist_matches(command: str, expected: str) -> None:
    assert policy.denied_rule(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "git push --force-with-lease origin main",
        "git push --force-if-includes",
        "git push origin main",
        "git branch -d feature",
        "git reset --hard HEAD~1",
        "git reset origin/main",
        "git   push\n  --force",
        "rm build\nprintf '%s\\n' -rf /tmp/example",
        "rm -rf build",
        "rm -rf ./build",
        "rm -r build/",
        "alembic history",
        "prisma migrate dev",
        "terraform plan",
        "kubectl get pods",
        "docker build .",
        "npm run publish-docs",
        "cargo publish-check",
        "uv run pytest -q",
        "gh pr view 12",
        "curl -s https://example.invalid",
        "wget https://example.invalid/file.tar.gz",
        "",
    ],
)
def test_denylist_allows(command: str) -> None:
    assert policy.denied_rule(command) is None


def test_rule_names_match_rules_and_action_regex() -> None:
    from scribe.schema import ACTION_RE

    assert policy.RULE_NAMES == {name for name, _ in policy.RULES}
    assert len(policy.RULE_NAMES) == len(policy.RULES) == 18
    assert all(ACTION_RE.match(name) for name in policy.RULE_NAMES)
    assert "git-push-force" in policy.RULE_NAMES


def test_matching_rules_reports_every_hit_in_order() -> None:
    assert policy.matching_rules("git push -f && npm publish") == [
        "git-push-force",
        "npm-publish",
    ]


# --- policy: plan areas -------------------------------------------------------


@pytest.mark.parametrize(
    ("plan", "expected"),
    [
        ("Add package httpx and change the DB schema.", ["dependency", "schema"]),
        ("Expose a new Public API on the service.", ["public-api"]),
        ("Move the queue to a second thread.", ["concurrency"]),
        ("This deviates from the approved plan.", ["deviation"]),
        ("Write a migration for the storage layer.", ["schema", "storage"]),
        ("Rename a local variable.", []),
        ("", []),
    ],
)
def test_decision_worthy_areas(plan: str, expected: list[str]) -> None:
    assert policy.decision_worthy_areas(plan) == expected


# --- gate hook: Bash and PowerShell -------------------------------------------


def test_gate_module_declares_gate_policy_and_names_the_switch() -> None:
    assert pre_tool_use_gate.POLICY == POLICY_GATE
    source = (
        PROJECT_ROOT / "src" / "scribe" / "hooks" / "pre_tool_use_gate.py"
    ).read_text(encoding="utf-8")
    assert "SCRIBE_GATES" in source


def test_force_push_shadow_logs_deny_and_exits_zero(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    result = run_hook(
        "gate", load_fixture("gate_bash_force_push.json", tmp_repo), tmp_repo
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    (entry,) = gate_log_lines(tmp_repo)
    assert entry["event"] == "gate_verdict"
    assert entry["verdict"] == "deny"
    assert entry["tool"] == "Bash"
    assert entry["command_head"] == "git push --force origin main"
    assert "'git-push-force' is on the irreversible-action denylist" in entry["reason"]
    assert "/scribe:decide" in entry["reason"]
    assert "at" in entry


def test_force_push_enforce_exits_two_with_reason(
    run_hook: RunHook, tmp_repo: Path, set_config: SetConfig
) -> None:
    set_config(tmp_repo, SCRIBE_GATES="enforce")
    result = run_hook(
        "gate", load_fixture("gate_bash_force_push.json", tmp_repo), tmp_repo
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "irreversible-action denylist" in result.stderr
    assert gate_log_lines(tmp_repo)[0]["verdict"] == "deny"


def test_ratified_one_way_door_action_allows_force_push(
    run_hook: RunHook, tmp_repo: Path, set_config: SetConfig
) -> None:
    set_config(tmp_repo, SCRIBE_GATES="enforce")
    write_ratified_action_record(tmp_repo, "git-push-force")
    result = run_hook(
        "gate", load_fixture("gate_bash_force_push.json", tmp_repo), tmp_repo
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    (entry,) = gate_log_lines(tmp_repo)
    assert entry["verdict"] == "allow"
    assert entry["reason"] == ""


def test_ratified_record_for_another_action_does_not_allow(
    run_hook: RunHook, tmp_repo: Path, set_config: SetConfig
) -> None:
    set_config(tmp_repo, SCRIBE_GATES="enforce")
    write_ratified_action_record(tmp_repo, "npm-publish")
    result = run_hook(
        "gate", load_fixture("gate_bash_force_push.json", tmp_repo), tmp_repo
    )
    assert result.returncode == 2


def test_compound_command_denies_when_only_one_matched_rule_is_ratified(
    run_hook: RunHook, tmp_repo: Path, set_config: SetConfig
) -> None:
    set_config(tmp_repo, SCRIBE_GATES="enforce")
    write_ratified_action_record(tmp_repo, "git-push-force")
    payload = load_fixture("gate_bash_force_push.json", tmp_repo)
    payload["tool_input"]["command"] = "git push --force origin main && npm publish"

    result = run_hook("gate", payload, tmp_repo)

    assert result.returncode == 2
    assert "'npm-publish' is on the irreversible-action denylist" in result.stderr
    (entry,) = gate_log_lines(tmp_repo)
    assert entry["matched_rules"] == ["git-push-force", "npm-publish"]
    assert entry["uncovered_rules"] == ["npm-publish"]


def test_unratified_or_two_way_door_action_record_does_not_allow(
    tmp_repo: Path,
) -> None:
    from scribe.store import Store

    write_ratified_action_record(tmp_repo, "git-push-force")
    path = tmp_repo / "docs" / "decisions" / "D-260908-allow-the-action.md"
    record = Record.load(path)
    record.data["reversibility"] = "two-way-door"
    record.save()
    assert not pre_tool_use_gate.action_is_ratified(Store(tmp_repo), "git-push-force")


@pytest.mark.parametrize("change", ["unattested", "expired", "superseded", "body_hash_mismatch"])
def test_action_authority_requires_live_matching_attestation(tmp_repo: Path, change: str) -> None:
    write_ratified_action_record(tmp_repo, "git-push-force")
    path = tmp_repo / "docs" / "decisions" / "D-260908-allow-the-action.md"
    if change == "unattested":
        (tmp_repo / "docs" / "decisions" / "RATIFICATIONS.jsonl").write_text("", encoding="utf-8")
    else:
        record = Record.load(path)
        if change == "expired":
            record.data["effective_state"] = "expired"
        elif change == "superseded":
            record.data["effective_state"] = "superseded"
        else:
            record.body += "changed\n"
        record.save()
    assert not pre_tool_use_gate.action_is_ratified(Store(tmp_repo), "git-push-force")
    record = Record.load(path)
    record.data.update({"reversibility": "one-way-door", "review_state": "unreviewed"})
    record.save()
    assert not pre_tool_use_gate.action_is_ratified(Store(tmp_repo), "git-push-force")


def test_force_with_lease_is_allowed(
    run_hook: RunHook, tmp_repo: Path, set_config: SetConfig
) -> None:
    set_config(tmp_repo, SCRIBE_GATES="enforce")
    result = run_hook(
        "gate", load_fixture("gate_bash_force_with_lease.json", tmp_repo), tmp_repo
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    (entry,) = gate_log_lines(tmp_repo)
    assert entry["verdict"] == "allow"
    assert entry["command_head"].startswith("git push --force-with-lease")


def test_safe_command_is_allowed_and_logged(run_hook: RunHook, tmp_repo: Path) -> None:
    result = run_hook("gate", load_fixture("gate_bash_safe.json", tmp_repo), tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    (entry,) = gate_log_lines(tmp_repo)
    assert (entry["verdict"], entry["tool"]) == ("allow", "Bash")


def test_powershell_npm_publish_is_denied(run_hook: RunHook, tmp_repo: Path) -> None:
    result = run_hook(
        "gate", load_fixture("gate_powershell_publish.json", tmp_repo), tmp_repo
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    (entry,) = gate_log_lines(tmp_repo)
    assert entry["verdict"] == "deny"
    assert entry["tool"] == "PowerShell"
    assert "'npm-publish'" in entry["reason"]
    assert len(entry["command_head"]) <= 80


def test_command_head_is_capped_at_eighty_chars(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    payload = load_fixture("gate_bash_safe.json", tmp_repo)
    payload["tool_input"]["command"] = "echo " + "x" * 200
    run_hook("gate", payload, tmp_repo)
    (entry,) = gate_log_lines(tmp_repo)
    assert len(entry["command_head"]) == 80


def test_gate_without_store_is_silent(run_hook: RunHook, tmp_repo: Path) -> None:
    for path in (tmp_repo / "docs" / "decisions").iterdir():
        path.unlink()
    (tmp_repo / "docs" / "decisions").rmdir()
    result = run_hook(
        "gate", load_fixture("gate_bash_force_push.json", tmp_repo), tmp_repo
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not gate_log_path(tmp_repo).exists()


def test_gate_malformed_stdin_is_silent(run_hook: RunHook, tmp_repo: Path) -> None:
    result = run_hook("gate", (FIXTURES / "malformed.txt").read_text(), tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not gate_log_path(tmp_repo).exists()


def test_gate_missing_tool_input_allows(run_hook: RunHook, tmp_repo: Path) -> None:
    payload = load_fixture("gate_bash_force_push.json", tmp_repo)
    del payload["tool_input"]
    result = run_hook("gate", payload, tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert gate_log_lines(tmp_repo)[0]["verdict"] == "allow"


# --- gate hook: ExitPlanMode ---------------------------------------------------


def test_exit_plan_mode_denies_and_flags_when_nothing_is_pending(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    result = run_hook(
        "gate", load_fixture("gate_exit_plan_mode.json", tmp_repo), tmp_repo
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    (entry,) = gate_log_lines(tmp_repo)
    assert entry["verdict"] == "deny"
    assert entry["tool"] == "ExitPlanMode"
    assert entry["areas"] == ["dependency"]
    assert entry["reason"] == (
        "scribe: plan touches dependency; run /scribe:decide before leaving plan mode"
    )
    flag = session_state(tmp_repo)["decision_worthy"]
    assert flag["areas"] == ["dependency"]
    assert flag["prompt_id"] == "prompt_fixture_gate"
    assert flag["set_at"]


def test_exit_plan_mode_enforce_exits_two(
    run_hook: RunHook, tmp_repo: Path, set_config: SetConfig
) -> None:
    set_config(tmp_repo, SCRIBE_GATES="enforce")
    result = run_hook(
        "gate", load_fixture("gate_exit_plan_mode.json", tmp_repo), tmp_repo
    )
    assert result.returncode == 2
    assert "run /scribe:decide before leaving plan mode" in result.stderr


def test_exit_plan_mode_allows_with_pending_decision_but_still_flags(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    seed_session(tmp_repo, pending_decisions=["01M21BVB05VVF1XV54Y66AWV6E"])
    result = run_hook(
        "gate", load_fixture("gate_exit_plan_mode.json", tmp_repo), tmp_repo
    )
    assert result.returncode == 0
    (entry,) = gate_log_lines(tmp_repo)
    assert entry["verdict"] == "allow"
    assert session_state(tmp_repo)["decision_worthy"]["areas"] == ["dependency"]


def test_exit_plan_mode_plain_plan_allows_without_flag(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    payload = load_fixture("gate_exit_plan_mode.json", tmp_repo)
    payload["tool_input"]["plan"] = "Rename a local variable and fix a typo."
    result = run_hook("gate", payload, tmp_repo)
    assert result.returncode == 0
    (entry,) = gate_log_lines(tmp_repo)
    assert (entry["verdict"], entry["areas"]) == ("allow", [])
    assert GATE_SESSION not in load_state(tmp_repo)["sessions"]


def test_exit_plan_mode_falls_back_to_last_prompt_id(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    seed_session(tmp_repo, prompt_ids=["prompt_newest", "prompt_older"])
    payload = load_fixture("gate_exit_plan_mode.json", tmp_repo)
    del payload["prompt_id"]
    run_hook("gate", payload, tmp_repo)
    assert session_state(tmp_repo)["decision_worthy"]["prompt_id"] == "prompt_newest"


# --- reconcile hook: TaskCompleted ----------------------------------------------


def test_reconcile_selects_policy_by_event() -> None:
    assert reconcile.select_policy({"hook_event_name": "TaskCompleted"}) == POLICY_GATE
    assert reconcile.select_policy({"hook_event_name": "Stop"}) == POLICY_ADVISORY
    assert reconcile.select_policy({}) == POLICY_ADVISORY


def test_task_completed_reports_capture_missing_once(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    run_hook("gate", load_fixture("gate_exit_plan_mode.json", tmp_repo), tmp_repo)
    flagged_at = session_state(tmp_repo)["decision_worthy"]["set_at"]

    result = run_hook(
        "reconcile", load_fixture("task_completed.json", tmp_repo), tmp_repo
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    events = gate_log_lines(tmp_repo)[1:]
    assert [entry["event"] for entry in events] == ["capture_missing", "gate_verdict"]
    missing, verdict = events
    assert missing["session_id"] == GATE_SESSION
    assert missing["task_id"] == "task_fixture_0001"
    assert missing["task_subject"] == "Swap urllib for httpx in the fetcher"
    assert missing["areas"] == ["dependency"]
    assert missing["flagged_at"] == flagged_at
    assert verdict["verdict"] == "deny"
    assert verdict["tool"] == "TaskCompleted"
    assert verdict["reason"] == (
        "scribe: task 'Swap urllib for httpx in the fetcher' flagged decision-worthy "
        "(dependency) but no record was written"
    )
    assert session_state(tmp_repo)["decision_worthy"] is None

    again = run_hook(
        "reconcile", load_fixture("task_completed.json", tmp_repo), tmp_repo
    )
    assert again.returncode == 0
    assert len(gate_log_lines(tmp_repo)) == 3


def test_task_completed_enforce_exits_two(
    run_hook: RunHook, tmp_repo: Path, set_config: SetConfig
) -> None:
    run_hook("gate", load_fixture("gate_exit_plan_mode.json", tmp_repo), tmp_repo)
    set_config(tmp_repo, SCRIBE_GATES="enforce")
    result = run_hook(
        "reconcile", load_fixture("task_completed.json", tmp_repo), tmp_repo
    )
    assert result.returncode == 2
    assert (
        "flagged decision-worthy (dependency) but no record was written"
        in result.stderr
    )
    assert session_state(tmp_repo)["decision_worthy"] is not None


def test_task_completed_allows_after_record_written(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    run_hook("gate", load_fixture("gate_exit_plan_mode.json", tmp_repo), tmp_repo)
    flagged_at = session_state(tmp_repo)["decision_worthy"]["set_at"]
    seed_session(
        tmp_repo,
        records_written=[{"id": "01M21BVB05VVF1XV54Y66AWV6E", "at": flagged_at}],
    )
    result = run_hook(
        "reconcile", load_fixture("task_completed.json", tmp_repo), tmp_repo
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    events = gate_log_lines(tmp_repo)[1:]
    assert [entry["event"] for entry in events] == ["gate_verdict"]
    assert events[0]["verdict"] == "allow"
    assert session_state(tmp_repo)["decision_worthy"] is None


def test_task_completed_older_record_does_not_satisfy_flag(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    run_hook("gate", load_fixture("gate_exit_plan_mode.json", tmp_repo), tmp_repo)
    seed_session(
        tmp_repo,
        records_written=[
            {"id": "01M21BVB05VVF1XV54Y66AWV6E", "at": "2026-09-01T00:00:00Z"}
        ],
    )
    run_hook("reconcile", load_fixture("task_completed.json", tmp_repo), tmp_repo)
    assert "capture_missing" in {entry["event"] for entry in gate_log_lines(tmp_repo)}


def test_task_completed_without_flag_is_silent(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    result = run_hook(
        "reconcile", load_fixture("task_completed.json", tmp_repo), tmp_repo
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not gate_log_path(tmp_repo).exists()


# --- reconcile hook: Stop ---------------------------------------------------------


def test_stop_logs_one_reconcile_event(run_hook: RunHook, tmp_repo: Path) -> None:
    seed_session(tmp_repo, pending_decisions=["01M21BVB05VVF1XV54Y66AWV6E"])
    result = run_hook("reconcile", load_fixture("stop.json", tmp_repo), tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    (entry,) = gate_log_lines(tmp_repo)
    assert entry["event"] == "stop_reconcile"
    assert entry["session_id"] == GATE_SESSION
    assert entry["pending_decisions"] == ["01M21BVB05VVF1XV54Y66AWV6E"]
    assert entry["has_last_message"] is True
    assert "at" in entry


def test_stop_without_session_state_logs_empty_pending(
    run_hook: RunHook, tmp_repo: Path
) -> None:
    payload = load_fixture("stop.json", tmp_repo)
    payload["last_assistant_message"] = ""
    run_hook("reconcile", payload, tmp_repo)
    (entry,) = gate_log_lines(tmp_repo)
    assert entry["pending_decisions"] == []
    assert entry["has_last_message"] is False


def test_stop_active_is_silent(run_hook: RunHook, tmp_repo: Path) -> None:
    result = run_hook("reconcile", load_fixture("stop_active.json", tmp_repo), tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not gate_log_path(tmp_repo).exists()


def test_reconcile_without_store_is_silent(run_hook: RunHook, tmp_repo: Path) -> None:
    for path in (tmp_repo / "docs" / "decisions").iterdir():
        path.unlink()
    (tmp_repo / "docs" / "decisions").rmdir()
    for name in ("task_completed.json", "stop.json"):
        result = run_hook("reconcile", load_fixture(name, tmp_repo), tmp_repo)
        assert (result.returncode, result.stdout, result.stderr) == (0, "", ""), name
    assert not gate_log_path(tmp_repo).exists()


def test_reconcile_malformed_stdin_is_silent(run_hook: RunHook, tmp_repo: Path) -> None:
    result = run_hook("reconcile", (FIXTURES / "malformed.txt").read_text(), tmp_repo)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not gate_log_path(tmp_repo).exists()
