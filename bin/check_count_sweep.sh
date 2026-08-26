#!/bin/bash
set -euo pipefail
cd ~/cryptobot-train

# Drift guard: fail if any judge-facing surface claims a stale test count.
# Exact expected figure verified live: 130 = 59 cryptobot + 71 options.
# NOTE: css color rgba(255,107,107) is NOT a count â€” only match count-like contexts.
BAD=$(grep -rEn "(107|117|98|93|92|90|89)[[:space:]]*TESTS?[[:space:]]*PASS|\(107 tests|107 passing|107 offline|107-test" \
  --include="*.md" --include="*.html" \
  SUBMISSION.md presentation slides posts README.md 2>/dev/null | grep -v "\.bak-" || true)

if [ -n "$BAD" ]; then
  echo "STALE TEST-COUNT CLAIMS FOUND:"
  echo "$BAD"
  exit 1
fi

# Also verify the canonical suite count matches what surfaces claim.
COUNT=$(cryptobot/.venv/bin/python -m pytest cryptobot/tests options/tests --collect-only -q 2>/dev/null | tail -1 | grep -oE '^[0-9]+' || echo 0)
echo "canonical suite count: $COUNT"
if [ "$COUNT" != "130" ]; then
  echo "WARNING: canonical count is $COUNT, docs claim 130 -- re-sweep needed"
  exit 1
fi
echo "count sweep clean: 130 everywhere"
