#!/usr/bin/env bash
# Step 11 (U2, owner question Q2): does a project deny rule Bash(*scribe ratify*)
# block the human-typed /scribe:ratify skill, whose verdict runs as an inline
# `!` command? Runs headless against playground 03 (which has a ratified seed
# record, so the command is idempotent: "already ratified"), once without the
# Bash rules (control) and once with them. Restores settings.json afterwards
# and writes VERIFIED (skill still works) or BLOCKED to step11-u2-result.txt.
set -u
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
REPO=/home/alfakentavr/scribe-playground/03-refactor
ALIAS=D-260909-non-positive-width-height-or-radius-rais
SETTINGS="$REPO/.claude/settings.json"
ORIGINAL=$(cat "$SETTINGS")
RATS_BEFORE=$(wc -l < "$REPO/docs/decisions/RATIFICATIONS.jsonl")
run_case() {
  tag=$1
  ( cd "$REPO" && env -u CLAUDECODE timeout 240 claude -p --plugin-dir /home/alfakentavr/scribe --model sonnet "/scribe:ratify $ALIAS u2 live test" ) > "$OUT/step11-$tag.txt" 2> "$OUT/step11-$tag.err"
  echo "case=$tag claude exit $?"
  tail -c 500 "$OUT/step11-$tag.txt"
  echo
}
run_case control
printf '{\n  "permissions": {\n    "deny": [\n      "Edit(/docs/decisions/RATIFICATIONS.jsonl)",\n      "Bash(*scribe ratify*)",\n      "Bash(*scribe reject*)"\n    ]\n  }\n}\n' > "$SETTINGS"
run_case denied
printf '%s\n' "$ORIGINAL" > "$SETTINGS"
RATS_AFTER=$(wc -l < "$REPO/docs/decisions/RATIFICATIONS.jsonl")
echo "attestation lines before=$RATS_BEFORE after=$RATS_AFTER"
if grep -q -i -e "already ratified" -e "verdict" "$OUT/step11-denied.txt" && ! grep -q -i -e "denied" -e "not allowed" -e "permission" "$OUT/step11-denied.txt"; then
  echo VERIFIED > "$OUT/step11-u2-result.txt"
else
  echo BLOCKED > "$OUT/step11-u2-result.txt"
fi
echo "result: $(cat "$OUT/step11-u2-result.txt")"
