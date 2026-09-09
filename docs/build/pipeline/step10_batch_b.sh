#!/usr/bin/env bash
# Step 10: Codex gpt-5.6-terra (owner's implementation model; gpt-5.6-luna
# subagents for reading and extraction) implements Batch B (owner-decided items V12, V3,
# V8, V19, V21) in ~/scribe. Detached, 20-minute hard cap, .git read-only so
# the main session commits from /tmp/scribe-batch-b-commits item by item.
# Resume a cut-off slice with `bash codex_resume_detached.sh step10 <message-or-file>`.
set -u
CODEX=/home/alfakentavr/.codex/packages/standalone/current/bin/codex
HERE=/home/alfakentavr/scribe/docs/build/pipeline
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
mkdir -p "$OUT"
rm -f "$OUT/step10.done"
cd /home/alfakentavr/scribe || exit 1
setsid nohup bash -c "timeout -k 30 1200 '$CODEX' exec -m gpt-5.6-terra --sandbox workspace-write -C /home/alfakentavr/scribe -c 'model_reasoning_effort=\"high\"' -c 'sandbox_workspace_write.network_access=true' -c 'agents.default_subagent_model=\"gpt-5.6-luna\"' -c 'agents.default_subagent_reasoning_effort=\"medium\"' --json -o '$OUT/step10-last.txt' \"\$(cat '$HERE/step10_prompt.txt')\" < /dev/null > '$OUT/step10-events.jsonl' 2> '$OUT/step10-stderr.log'; echo \$? > '$OUT/step10.done'" \
  < /dev/null > /dev/null 2>&1 &
disown
echo "detached, waiting file: $OUT/step10.done"
