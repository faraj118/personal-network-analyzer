#!/usr/bin/env bash
# Reject tool/assistant attribution in commit messages and PR text (see CONTRIBUTING.md).
# Usage: check_attribution.sh [file]   (reads stdin when no file is given)
set -euo pipefail

pattern='^[[:space:]]*co-authored-by:|🤖|^[[:space:]]*generated (with|by) \[|^[[:space:]]*[a-z-]*session:[[:space:]]*https?://'

if grep -inE "$pattern" "${1:--}"; then
  echo "error: attribution trailer/footer found — not allowed in this repo (CONTRIBUTING.md)." >&2
  exit 1
fi
