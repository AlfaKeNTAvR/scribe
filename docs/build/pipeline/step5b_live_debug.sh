#!/usr/bin/env bash
# Step 5b: the step 5 live test with the raw event stream captured, so a
# blocked Edit shows which permission rule or hook produced the block.
# Restores src/scribe/index.py afterwards. Output goes to the job tmp dir.
set -u
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
cd /home/alfakentavr/scribe || exit 1
PROMPT="Append the line '# scribe live test' to the end of src/scribe/index.py using the Edit tool. Then reply with exactly one line: INJECTION SEEN followed by the record aliases you saw, if a block mentioning 'retrieval candidates' or 'D-260908' appeared in your context around the edit; otherwise INJECTION NOT SEEN."
env -u CLAUDECODE timeout 300 claude -p --plugin-dir /home/alfakentavr/scribe --permission-mode acceptEdits --model sonnet --output-format stream-json --verbose "$PROMPT" > "$OUT/step5b-stream.jsonl" 2> "$OUT/step5b-live.err"
echo "claude exit $?"
grep -o -E '"is_error":true[^}]{0,400}' "$OUT/step5b-stream.jsonl" | head -5
grep -o -E '(blocked|denied|permission)[^"]{0,300}' "$OUT/step5b-stream.jsonl" | head -8
echo "--- index.py tail"
tail -1 src/scribe/index.py
git -C /home/alfakentavr/scribe checkout -q -- src/scribe/index.py
