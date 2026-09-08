#!/usr/bin/env bash
# Step 4 of the build pipeline: Codex gpt-6-astra orchestrator implements the plan in ~/scribe
# with gpt-5.6-sol subagents. Up to 20 minutes per slice (SIGTERM at 20 min, SIGKILL 30 s later), run detached; continue with codex_resume.sh step4 if it stops early.
set -u
CODEX=/home/alfakentavr/.codex/packages/standalone/current/bin/codex
HERE=/home/alfakentavr/scribe/docs/build/pipeline
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
mkdir -p "$OUT"
cd /home/alfakentavr/scribe || exit 1
timeout -k 30 1200 "$CODEX" exec -m gpt-6-astra --sandbox workspace-write -C /home/alfakentavr/scribe \
  -c 'model_reasoning_effort="high"' \
  -c 'agents.default_subagent_model="gpt-5.6-sol"' \
  -c 'agents.default_subagent_reasoning_effort="medium"' \
  -c 'agents.max_concurrent_threads_per_session=3' \
  --json -o "$OUT/step4-last.txt" \
  "$(cat "$HERE/step4_prompt.txt")" \
  < /dev/null > "$OUT/step4-events.jsonl" 2> "$OUT/step4-stderr.log"
echo "codex exit $?"
