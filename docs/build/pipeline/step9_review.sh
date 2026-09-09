#!/usr/bin/env bash
# Step 9: Codex gpt-6-astra reviews Batch A groups 1 and 2 plus the V1 fix,
# read-only sandbox, detached, 20-minute hard cap. Final message lands in
# step9-last.txt and is copied to docs/build/08-codex-review-batch-a.md.
set -u
CODEX=/home/alfakentavr/.codex/packages/standalone/current/bin/codex
HERE=/home/alfakentavr/scribe/docs/build/pipeline
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
mkdir -p "$OUT"
rm -f "$OUT/step9.done"
cd /home/alfakentavr/scribe || exit 1
setsid nohup bash -c "timeout -k 30 1200 '$CODEX' exec -m gpt-6-astra --sandbox read-only -C /home/alfakentavr/scribe -c 'model_reasoning_effort=\"high\"' --json -o '$OUT/step9-last.txt' \"\$(cat '$HERE/step9_review_prompt.txt')\" < /dev/null > '$OUT/step9-events.jsonl' 2> '$OUT/step9-stderr.log'; echo \$? > '$OUT/step9.done'" \
  < /dev/null > /dev/null 2>&1 &
disown
echo "detached, waiting file: $OUT/step9.done"
