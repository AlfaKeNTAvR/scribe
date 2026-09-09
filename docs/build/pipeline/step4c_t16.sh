#!/usr/bin/env bash
# Step 4c: Codex gpt-6-astra performs plan task T16 (deferred test, final sweep,
# implementation report) in ~/scribe. Detached, 20-minute hard cap, .git is
# read-only inside the sandbox so the main session commits afterwards.
set -u
CODEX=/home/alfakentavr/.codex/packages/standalone/current/bin/codex
HERE=/home/alfakentavr/scribe/docs/build/pipeline
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
mkdir -p "$OUT"
rm -f "$OUT/step4c.done"
cd /home/alfakentavr/scribe || exit 1
setsid nohup bash -c "timeout -k 30 1200 '$CODEX' exec -m gpt-6-astra --sandbox workspace-write -C /home/alfakentavr/scribe -c 'model_reasoning_effort=\"high\"' -c 'sandbox_workspace_write.network_access=true' -c 'agents.default_subagent_model=\"gpt-5.6-sol\"' -c 'agents.default_subagent_reasoning_effort=\"medium\"' --json -o '$OUT/step4c-last.txt' \"\$(cat '$HERE/step4c_prompt.txt')\" < /dev/null > '$OUT/step4c-events.jsonl' 2> '$OUT/step4c-stderr.log'; echo \$? > '$OUT/step4c.done'" \
  < /dev/null > /dev/null 2>&1 &
disown
echo "detached, waiting file: $OUT/step4c.done"
