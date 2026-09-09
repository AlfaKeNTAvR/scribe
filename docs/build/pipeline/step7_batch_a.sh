#!/usr/bin/env bash
# Step 7: Codex gpt-6-astra implements Batch A of docs/build/06-validation-triage.md
# in ~/scribe. Detached, 20-minute hard cap, .git read-only inside the sandbox so
# the main session commits afterwards from the commit queue in
# docs/build/07-batch-a-report.md. Resume a cut-off slice with
# `bash codex_resume_detached.sh step7 <message-or-file>`.
set -u
CODEX=/home/alfakentavr/.codex/packages/standalone/current/bin/codex
HERE=/home/alfakentavr/scribe/docs/build/pipeline
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
mkdir -p "$OUT"
rm -f "$OUT/step7.done"
cd /home/alfakentavr/scribe || exit 1
setsid nohup bash -c "timeout -k 30 1200 '$CODEX' exec -m gpt-6-astra --sandbox workspace-write -C /home/alfakentavr/scribe -c 'model_reasoning_effort=\"high\"' -c 'sandbox_workspace_write.network_access=true' -c 'agents.default_subagent_model=\"gpt-5.6-sol\"' -c 'agents.default_subagent_reasoning_effort=\"medium\"' --json -o '$OUT/step7-last.txt' \"\$(cat '$HERE/step7_prompt.txt')\" < /dev/null > '$OUT/step7-events.jsonl' 2> '$OUT/step7-stderr.log'; echo \$? > '$OUT/step7.done'" \
  < /dev/null > /dev/null 2>&1 &
disown
echo "detached, waiting file: $OUT/step7.done"
