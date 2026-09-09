#!/usr/bin/env bash
# Step 13: write the Batch C deferral records (V7, V13, V23) and the rebase
# post-commit proposal from the specs in specs/, registering each for the next
# commit's Decision trailer. Sequential: each run takes the ledger lock.
set -u
cd /home/alfakentavr/scribe || exit 1
SESSION=session_01A6tVoZuuWqu56QxEqtAjRw
SPECS=("$@")
if [ ${#SPECS[@]} -eq 0 ]; then
  SPECS=(v7-history-replay-deferred v13-staged-content-deferred v23-test-fixtures-deferred rebase-post-commit-skip)
fi
for spec in "${SPECS[@]}"; do
  uv run --frozen scribe new --spec "docs/build/pipeline/specs/$spec.json" --register --session "$SESSION"
  echo "spec=$spec exit=$?"
done
