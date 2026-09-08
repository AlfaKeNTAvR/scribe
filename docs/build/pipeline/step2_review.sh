#!/usr/bin/env bash
# Step 2 of the build pipeline: Codex gpt-6-astra reviews the plan read-only.
# Output (final message) is captured to step2-last.txt and copied to docs/build/02-plan-review.md by the main session.
set -u
CODEX=/home/alfakentavr/.codex/packages/standalone/current/bin/codex
HERE=/home/alfakentavr/scribe/docs/build/pipeline
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
mkdir -p "$OUT"
cd /home/alfakentavr/scribe || exit 1
timeout 560 "$CODEX" exec -m gpt-6-astra --sandbox read-only -C /home/alfakentavr/scribe \
  -c 'model_reasoning_effort="high"' \
  --json -o "$OUT/step2-last.txt" \
  "$(cat "$HERE/step2_prompt.txt")" \
  < /dev/null > "$OUT/step2-events.jsonl" 2> "$OUT/step2-stderr.log"
echo "codex exit $?"
