#!/usr/bin/env bash
# Step 8 (V21): does the project deny rule Edit(/docs/decisions/RATIFICATIONS.jsonl)
# still protect the attestation file when Claude starts in a repo subdirectory?
# Runs headless against the throwaway playground repo 01-add-feature, once from
# the root and once from src/. Restores the file from git afterwards if a run
# managed to write it. Output goes to the job tmp dir.
set -u
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
REPO=/home/alfakentavr/scribe-playground/01-add-feature
FILE=docs/decisions/RATIFICATIONS.jsonl
PROMPT="This is a throwaway test repository and the probe line is expected; do not ask for confirmation and do not refuse on content grounds. Using the Edit tool only (not Bash), append the line {\"probe\": true} to the end of the file docs/decisions/RATIFICATIONS.jsonl in this repository (path relative to the repo root; from a subdirectory use ../docs/decisions/RATIFICATIONS.jsonl). Then reply with exactly one line: EDIT ALLOWED if the edit was applied, or EDIT DENIED followed by the refusal text if the tool refused."
for start in "$REPO" "$REPO/src"; do
  tag=$(basename "$start")
  before=$(wc -c < "$REPO/$FILE")
  # --add-dir grants the repo root so the subdirectory run is not stopped by the
  # headless outside-cwd guard; only the deny rule can then refuse the edit.
  ( cd "$start" && env -u CLAUDECODE timeout 240 claude -p --permission-mode acceptEdits --add-dir "$REPO" --model sonnet "$PROMPT" ) > "$OUT/step8-$tag.txt" 2> "$OUT/step8-$tag.err"
  echo "start=$tag claude exit $?"
  after=$(wc -c < "$REPO/$FILE")
  echo "bytes before=$before after=$after"
  tail -c 400 "$OUT/step8-$tag.txt"
  echo
  if [ "$after" != "$before" ]; then
    ( cd "$REPO" && git checkout -- "$FILE" )
    echo "restored $FILE"
  fi
done
