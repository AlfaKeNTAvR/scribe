#!/usr/bin/env bash
# Step 4b: Codex gpt-6-astra validates the finished implementation read-only.
# Run detached (see codex_resume_detached.sh for the pattern); 20-minute hard cap.
# Final message is captured to step4b-last.txt and copied to docs/build/04b-codex-validation.md.
set -u
CODEX=/home/alfakentavr/.codex/packages/standalone/current/bin/codex
HERE=/home/alfakentavr/scribe/docs/build/pipeline
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
mkdir -p "$OUT"
rm -f "$OUT/step4b.done"
cd /home/alfakentavr/scribe || exit 1
setsid nohup bash -c "timeout -k 30 1200 '$CODEX' exec -m gpt-6-astra --sandbox read-only -C /home/alfakentavr/scribe -c 'model_reasoning_effort=\"high\"' --json -o '$OUT/step4b-last.txt' \"\$(cat '$HERE/step4b_prompt.txt')\" < /dev/null > '$OUT/step4b-events.jsonl' 2> '$OUT/step4b-stderr.log'; echo \$? > '$OUT/step4b.done'" \
  < /dev/null > /dev/null 2>&1 &
disown
echo "detached, waiting file: $OUT/step4b.done"
