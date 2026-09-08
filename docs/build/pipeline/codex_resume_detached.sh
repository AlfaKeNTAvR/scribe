#!/usr/bin/env bash
# Run codex_resume.sh fully detached from the calling tool (setsid + nohup) so the
# harness's low-memory guard cannot kill it. Writes <OUT>/<tag>.done with the exit
# code when the slice finishes. Wait on that file, never on this script.
# Usage: bash codex_resume_detached.sh <step-tag> [message-or-file]
set -u
HERE=/home/alfakentavr/scribe/docs/build/pipeline
OUT=/home/alfakentavr/.claude/jobs/f4c38b72/tmp/build
TAG=${1:?step tag required}
MSG=${2:-}
rm -f "$OUT/$TAG.done"
setsid nohup bash -c "bash '$HERE/codex_resume.sh' '$TAG' '$MSG' > '$OUT/$TAG-detached.log' 2>&1; echo \$? > '$OUT/$TAG.done'" \
  < /dev/null > /dev/null 2>&1 &
disown
echo "detached, waiting file: $OUT/$TAG.done"
