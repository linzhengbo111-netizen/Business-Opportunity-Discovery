#!/bin/bash
#
# Stage-definition parity check.
#
# src/lib/project_phase.ts (TS, website + worker) and
# crawler/project_phase.py (Python, crawler) each hold the 10 stage term
# definitions used for AI phase matching. If they drift, the website and
# the crawler classify the same project differently.
#
# This renders both prompt blocks and diffs them byte-for-byte.
# Exit 0 = identical. Exit 1 = drift (fix both sides).
#
# Run: ./scripts/check_stage_parity.sh

set -uo pipefail
cd "$(dirname "$0")/.."

TS_OUT=$(mktemp)
PY_OUT=$(mktemp)
trap 'rm -f "$TS_OUT" "$PY_OUT"' EXIT

if ! node_modules/.bin/jiti scripts/print_stage_block.ts > "$TS_OUT" 2>/dev/null; then
    echo "FAIL: could not render TS stage block (src/lib/project_phase.ts)"
    exit 1
fi

if ! python3 -c "
import sys
sys.path.insert(0, 'crawler')
from project_phase import stage_prompt_block
sys.stdout.write(stage_prompt_block())
" > "$PY_OUT" 2>/dev/null; then
    echo "FAIL: could not render Python stage block (crawler/project_phase.py)"
    exit 1
fi

if diff -u "$TS_OUT" "$PY_OUT" > /tmp/stage_parity.diff 2>&1; then
    echo "PASS: stage definitions identical in TS and Python ($(wc -l < "$TS_OUT") lines)"
    exit 0
fi

echo "FAIL: stage definitions differ between TS and Python"
echo "  TS:     src/lib/project_phase.ts    (STAGE_DEFINITIONS)"
echo "  Python: crawler/project_phase.py    (STAGE_DEFINITIONS)"
echo
head -40 /tmp/stage_parity.diff
exit 1
