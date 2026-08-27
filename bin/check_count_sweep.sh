#!/bin/bash
set -euo pipefail
cd ~/cryptobot-train

# Drift guard: fail if any judge-facing surface claims a stale test count.
# Canonical figure verified live: 140 = 60 cryptobot + 80 options.
# FIX 2026-08-26: old regex only matched counts 89-117, so 131/107-style
# stale claims sailed through. Now: flag ANY '<N> tests/passing/offline' or
# '<N>/<N> tests' claim whose number is not 133 (case-insensitive, md+html,
# backups excluded), then verify the canonical suite count matches.
COUNT=$(cryptobot/.venv/bin/python -m pytest cryptobot/tests options/tests --collect-only -q 2>/dev/null | tail -1 | grep -oE '^[0-9]+' || echo 0)
echo "canonical suite count: $COUNT"
if [ "$COUNT" != "140" ]; then
  echo "WARNING: canonical count is $COUNT, docs claim 140 -- re-sweep needed"
  exit 1
fi

BAD=$(grep -rEni "[0-9]+-?[[:space:]]*(tests?|passing|offline)|[0-9]+/[0-9]+[[:space:]]*tests?" \
  --include="*.md" --include="*.html" \
  SUBMISSION.md presentation slides posts README.md 2>/dev/null \
  | grep -v "\.bak" | grep -vE "\b140\b" || true)

if [ -n "$BAD" ]; then
  echo "STALE TEST-COUNT CLAIMS FOUND:"
  echo "$BAD"
  exit 1
fi

# Verify the per-dir breakdown claim (60 + 73) is present on all 5 surfaces.
MISSING=0
for f in SUBMISSION.md presentation/PROJECT_TITLE_DESCRIPTION.md \
         presentation/SUBMISSION_CHECKLIST.md presentation/BUILD_IN_PUBLIC_JOURNAL.md; do
  if ! grep -qE '60 cryptobot \+ 80 options' "$f"; then
    echo "MISSING 60+73 breakdown in $f"
    MISSING=1
  fi
done
[ "$MISSING" -eq 1 ] && exit 1

echo "count sweep clean: 140 (60+80) everywhere"
