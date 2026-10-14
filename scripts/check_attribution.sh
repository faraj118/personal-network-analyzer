#!/usr/bin/env bash
# Reject AI/tool attribution in commit messages and PR text (see CONTRIBUTING.md).
# Human co-authors are welcome; only bot accounts and generic noreply@ vendor addresses fail.
# Usage: check_attribution.sh [file]   (reads stdin when no file is given)
set -euo pipefail

pattern='^[[:space:]]*co-authored-by:.*(\[bot\]|<no-?reply@)|🤖|^[[:space:]]*generated (with|by) \[|^[[:space:]]*[a-z-]*session:[[:space:]]*https?://'

if grep -inE "$pattern" "${1:--}"; then
  echo "error: AI/tool attribution found — not allowed in this repo (CONTRIBUTING.md)." >&2
  exit 1
fi
