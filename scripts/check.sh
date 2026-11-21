#!/usr/bin/env bash
# Quality gate. Usage: scripts/check.sh [--full]
#   default: ruff + backend unit tests + frontend tests/lint/build
#   --full : whole backend suite (uses the configured DB in rolled-back transactions and the private bucket)
source "$(dirname "$0")/lib.sh"
FULL=0; [ "${1:-}" = "--full" ] && FULL=1
fail=0
step() { info "$1"; shift; if "$@"; then ok "passed"; else warn "FAILED"; fail=1; fi; }
cd "$BACKEND"
step "ruff" "$VENV/bin/ruff" check app tests scripts
if [ "$FULL" = 1 ]; then step "backend tests (full)" "$PY" -m pytest -q -p no:cacheprovider
else step "backend unit tests" "$PY" -m pytest -q -p no:cacheprovider tests/unit; fi
use_node
cd "$FRONTEND"
step "frontend tests" npm test --silent
step "frontend lint" npm run -s lint
step "frontend build" npm run -s build
[ "$fail" = 0 ] && ok "all checks passed" || die "some checks failed (see above)"
