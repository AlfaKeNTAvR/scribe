#!/usr/bin/env bash
# Step 12 retry: Codex reported "usage limit, try again at 5:27 PM" at 16:26
# EDT. Wait for the reset, relaunch step12_final_validation.sh, then block
# until its .done marker appears and print the exit code and error count.
set -u
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
until [ "$(date +%H%M)" -ge 1728 ]; do sleep 30; done
echo "17:28 reached, relaunching step12"
bash /home/alfakentavr/scribe/docs/build/pipeline/step12_final_validation.sh
until [ -f "$OUT/step12.done" ]; do sleep 5; done
echo "step12 finished exit=$(cat "$OUT/step12.done") errors=$(grep -c -e '"type":"error"' "$OUT/step12-events.jsonl")"
