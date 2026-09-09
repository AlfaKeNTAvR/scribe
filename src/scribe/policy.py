"""Gate policy: the irreversible-action denylist and the plan-exit heuristics (plan 4.7).

`RULES` is the denylist consumed by the Bash|PowerShell gate; `RULE_NAMES` is
the set of names an `affects` entry `{type: action, pattern: <name>}` may carry
(F2) and the set `scribe lint` checks with `unknown_action`. `POLICY_AREAS`
maps each README 10.4 policy area to the keywords the ExitPlanMode gate scans
a plan for.

Every regex runs over the command after whitespace is collapsed to single
spaces, so tokens are always separated by exactly one space. `TOKEN` is one
shell word that stops at a command separator (`;`, `&`, `|`), so a rule never
reads across `git push origin main && git status`.

UNVERIFIED: plan register item U2 (whether PreToolUse Bash hooks fire for
skill-injected `!` commands) concerns this module; no rule here covers a
scribe command, so nothing depends on it in this run.
"""

from __future__ import annotations

import re

TOKEN = r"[^ ;&|]+"
# End of a flag token: a space, the end of the command or a separator. Excludes
# `--force-with-lease` and `--force-if-includes` from a bare `--force` match.
FLAG_END = r"(?= |$|[;&|])"
# Sub-command position: any number of intermediate tokens on the same segment.
ARGS = rf"(?: {TOKEN})*?"

HTTP_METHODS = r"(?i:POST|PUT|PATCH|DELETE)"

RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "git-push-force",
        re.compile(rf"\bgit push{ARGS} (?:-f|--force){FLAG_END}"),
    ),
    (
        "git-branch-delete-force",
        re.compile(rf"\bgit branch{ARGS} -D{FLAG_END}"),
    ),
    (
        "git-reset-hard-remote",
        re.compile(rf"\bgit reset(?=[^;&|]* --hard{FLAG_END})[^;&|]*\borigin/"),
    ),
    (
        # rm with both a recursive and a force flag (any order, combined or not)
        # and any target that starts with `/`, `~` or `..`.
        "rm-rf-outside-worktree",
        re.compile(
            r"\brm"
            r"(?=[^;&|]* (?:-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)(?= |$|[;&|]))"
            r"(?=[^;&|]* (?:-[a-zA-Z]*f[a-zA-Z]*|--force)(?= |$|[;&|]))"
            r"[^;&|]* (?:/|~|\.\.)"
        ),
    ),
    (
        "alembic-migrate",
        re.compile(rf"\balembic{ARGS} (?:upgrade|downgrade)\b"),
    ),
    (
        "prisma-migrate-deploy",
        re.compile(rf"\bprisma{ARGS} migrate deploy\b"),
    ),
    (
        "flyway-migrate",
        re.compile(rf"\bflyway{ARGS} migrate\b"),
    ),
    (
        "terraform-apply-destroy",
        re.compile(rf"\bterraform{ARGS} (?:apply|destroy)\b"),
    ),
    (
        "kubectl-apply-delete",
        re.compile(rf"\bkubectl{ARGS} (?:apply|delete)\b"),
    ),
    (
        "helm-install-upgrade",
        re.compile(rf"\bhelm{ARGS} (?:install|upgrade)\b"),
    ),
    (
        "docker-push",
        re.compile(rf"\bdocker{ARGS} push\b"),
    ),
    (
        # `npm.cmd publish` is how PowerShell resolves npm on Windows.
        "npm-publish",
        re.compile(rf"\b(?:npm|pnpm|yarn)(?:\.cmd|\.exe)?{ARGS} publish{FLAG_END}"),
    ),
    (
        "cargo-publish",
        re.compile(rf"\bcargo{ARGS} publish{FLAG_END}"),
    ),
    (
        "twine-upload",
        re.compile(rf"\btwine{ARGS} upload{FLAG_END}"),
    ),
    (
        "uv-publish",
        re.compile(rf"\buv{ARGS} publish{FLAG_END}"),
    ),
    (
        "gh-release-create",
        re.compile(r"\bgh release create\b"),
    ),
    (
        "gh-pr-merge",
        re.compile(r"\bgh pr merge\b"),
    ),
    (
        "http-write",
        re.compile(
            r"\b(?:curl|wget|http)(?= (?:[^;&|]* )?"
            rf"(?:(?:-X ?|--request[ =]){HTTP_METHODS}\b|--data\b))"
        ),
    ),
]

RULE_NAMES: frozenset[str] = frozenset(name for name, _ in RULES)

# README 10.4 plan-approval policy areas -> keywords (matched case-insensitively
# as substrings, so `deviat` covers deviate, deviates, deviation).
POLICY_AREAS: dict[str, tuple[str, ...]] = {
    "dependency": ("dependency", "add package"),
    "public-api": ("public api",),
    "schema": ("schema", "migration"),
    "storage": ("storage",),
    "concurrency": ("concurrency", "thread"),
    "safety": ("safety",),
    "interface": ("interface",),
    "deviation": ("deviat",),
}


def collapse_whitespace(command: str) -> str:
    """Join every run of whitespace (including newlines) into one space."""
    return " ".join(command.split())


def matching_rules(command: str) -> list[str]:
    """Names of every denylist rule the command triggers, in `RULES` order.

    Rules may scan arguments in either order, but never borrow an option or a
    target from a later shell command.  Newlines are command separators too.
    """
    segments = [collapse_whitespace(part) for part in re.split(r"\r?\n|;|&&|\|\||\|", command)]
    return [
        name for name, pattern in RULES
        if any(pattern.search(segment) for segment in segments)
    ]


def denied_rule(command: str) -> str | None:
    """The first denylist rule the command triggers, or None when it is allowed."""
    matched = matching_rules(command)
    return matched[0] if matched else None


def decision_worthy_areas(plan: str) -> list[str]:
    """Policy areas whose keywords appear in the plan text, in `POLICY_AREAS` order."""
    lowered = plan.lower()
    return [
        area
        for area, keywords in POLICY_AREAS.items()
        if any(keyword in lowered for keyword in keywords)
    ]
