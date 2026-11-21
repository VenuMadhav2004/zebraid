#!/usr/bin/env bash
# Stop only the servers that scripts/start.sh started (PID files in .run/). Other processes are untouched.
source "$(dirname "$0")/lib.sh"
stopped=0
for name in web api; do
  f="$RUN_DIR/$name.pid"
  [ -f "$f" ] || continue
  pid="$(cat "$f")"
  if kill -0 "$pid" 2>/dev/null && grep -qaE 'uvicorn|vite' "/proc/$pid/cmdline" 2>/dev/null; then
    kill "$pid" && ok "stopped $name (pid $pid)" && stopped=1
  else
    warn "$name pid $pid is not running (stale PID file removed)"
  fi
  rm -f "$f"
done
[ "$stopped" = 1 ] || info "nothing started by scripts/start.sh is running"
