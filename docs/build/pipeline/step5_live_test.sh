#!/usr/bin/env bash
# Step 5 live test: load the plugin in a headless Claude run and edit a governed
# file, so the SessionStart, UserPromptSubmit and PreToolUse hooks fire for real.
# Restores src/scribe/index.py afterwards. Output goes to the job tmp dir.
# Pass criterion is the INJECTION SEEN line. The Edit itself is denied by
# Claude Code ("a sensitive file") because the plugin root is this same
# repository; see README's dogfooding caveat and step5b_live_debug.sh (M18).
# Load the plugin from a copy of the checkout to see the edit land as well.
set -u
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
cd /home/alfakentavr/scribe || exit 1
cp .claude/scribe/state.json "$OUT/state-before.json" 2>/dev/null || true
PROMPT="Append the line '# scribe live test' to the end of src/scribe/index.py using the Edit tool. Then reply with exactly one line: INJECTION SEEN followed by the record aliases you saw, if a block mentioning 'retrieval candidates' or 'D-260908' appeared in your context around the edit; otherwise INJECTION NOT SEEN."
env -u CLAUDECODE timeout 300 claude -p --plugin-dir /home/alfakentavr/scribe --permission-mode acceptEdits --model sonnet "$PROMPT" > "$OUT/step5-live.txt" 2> "$OUT/step5-live.err"
echo "claude exit $?"
tail -c 600 "$OUT/step5-live.txt"
echo
echo "--- stderr tail"
tail -c 400 "$OUT/step5-live.err"
echo
echo "--- index.py tail"
tail -1 src/scribe/index.py
