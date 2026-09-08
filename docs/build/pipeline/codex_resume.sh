#!/usr/bin/env bash
# Resume the most recent Codex thread for one more slice.
# Usage: bash codex_resume.sh <step-tag> [message]
set -u
CODEX=/home/alfakentavr/.codex/packages/standalone/current/bin/codex
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
TAG=${1:?step tag required}
MSG=${2:-"Continue where you left off. Do not restart from scratch. If you were about to write the final message, write it now in full."}
N=$(find "$OUT" -maxdepth 1 -name "$TAG-resume-*.jsonl" | wc -l)
N=$((N + 1))
cd /home/alfakentavr/scribe || exit 1
timeout -k 30 1200 "$CODEX" exec resume --last -c 'sandbox_workspace_write.network_access=true' --json -o "$OUT/$TAG-last.txt" "$MSG" \
  < /dev/null > "$OUT/$TAG-resume-$N.jsonl" 2> "$OUT/$TAG-resume-$N.stderr"
echo "codex exit $?"
