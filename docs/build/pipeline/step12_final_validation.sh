#!/usr/bin/env bash
# Step 12: Codex gpt-6-astra validates everything after its Batch A review
# (group 3, Batch B, the 08-review follow-ups, Q3, Q4) before the v0.1.0 tag.
# Read-only sandbox, detached, 20-minute hard cap. Final message lands in
# step12-last.txt and is copied to docs/build/11-codex-final-validation.md.
set -u
CODEX=/home/alfakentavr/.codex/packages/standalone/current/bin/codex
HERE=/home/alfakentavr/scribe/docs/build/pipeline
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
mkdir -p "$OUT"
rm -f "$OUT/step12.done"
cd /home/alfakentavr/scribe || exit 1
setsid nohup bash -c "timeout -k 30 1200 '$CODEX' exec -m gpt-6-astra --sandbox read-only -C /home/alfakentavr/scribe -c 'model_reasoning_effort=\"high\"' --json -o '$OUT/step12-last.txt' \"\$(cat '$HERE/step12_final_prompt.txt')\" < /dev/null > '$OUT/step12-events.jsonl' 2> '$OUT/step12-stderr.log'; echo \$? > '$OUT/step12.done'" \
  < /dev/null > /dev/null 2>&1 &
disown
echo "detached, waiting file: $OUT/step12.done"
