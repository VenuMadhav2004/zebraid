#!/usr/bin/env bash
# Start the API and the web UI. Usage: scripts/start.sh [--dev]
#   default : production UI build on WEB_PORT (4173) - fast over SSH tunnels
#   --dev   : Vite dev server with hot reload on DEV_PORT (5173)
# Already-running healthy servers are reused, never duplicated.
source "$(dirname "$0")/lib.sh"
DEV=0
for a in "$@"; do case "$a" in --dev) DEV=1 ;; -h|--help) sed -n '2,6p' "$0"; exit 0 ;; *) die "unknown option $a" ;; esac; done
[ -x "$PY" ] || die "backend/.venv missing: run scripts/setup.sh first"
[ -f "$BACKEND/.env" ] || die "backend/.env missing: run scripts/setup.sh and fill it in"
mkdir -p "$LOG_DIR"

start_bg() { # name logfile cmd...
  local name="$1" log="$2"; shift 2
  nohup "$@" >"$log" 2>&1 &
  echo $! >"$RUN_DIR/$name.pid"
}

# ---- API -----------------------------------------------------------------------------------
API_URL="http://127.0.0.1:$API_PORT"
if [ "$(http_code "$API_URL/health")" = 200 ]; then
  ok "API already running on port $API_PORT (reused)"
elif port_busy "$API_PORT"; then
  die "port $API_PORT is used by another program that is not the API; set API_PORT=... or stop it"
else
  info "starting API on $API_HOST:$API_PORT (log: .run/logs/api.log)"
  (cd "$BACKEND" && start_bg api "$LOG_DIR/api.log" "$PY" -m uvicorn app.main:app --host "$API_HOST" --port "$API_PORT")
  wait_for "$API_URL/health" 60 "API" || die "API did not start; see .run/logs/api.log"
fi

# ---- UI ------------------------------------------------------------------------------------
use_node
export VITE_PROXY_TARGET="$API_URL"
if [ "$DEV" = 1 ]; then
  PORT="$DEV_PORT"
  if [ "$(http_code "http://127.0.0.1:$PORT/")" = 200 ]; then
    ok "dev UI already running on port $PORT (reused)"
  else
    port_busy "$PORT" && die "port $PORT is busy; set DEV_PORT=..."
    info "starting Vite dev server on 127.0.0.1:$PORT (log: .run/logs/web.log)"
    (cd "$FRONTEND" && start_bg web "$LOG_DIR/web.log" npx vite --host 127.0.0.1 --port "$PORT" --strictPort)
  fi
else
  PORT="$WEB_PORT"
  if [ ! -f "$FRONTEND/dist/index.html" ] || [ -n "$(find "$FRONTEND/src" "$FRONTEND/index.html" "$FRONTEND/vite.config.js" -newer "$FRONTEND/dist/index.html" -print -quit)" ]; then
    info "building the UI (sources changed)"
    (cd "$FRONTEND" && npm run -s build >"$LOG_DIR/build.log" 2>&1) || die "UI build failed; see .run/logs/build.log"
    ok "UI built"
  fi
  if [ "$(http_code "http://127.0.0.1:$PORT/")" = 200 ]; then
    ok "UI already running on port $PORT (reused; serves the latest build from disk)"
  else
    port_busy "$PORT" && die "port $PORT is busy; set WEB_PORT=..."
    info "starting UI on 127.0.0.1:$PORT (log: .run/logs/web.log)"
    (cd "$FRONTEND" && start_bg web "$LOG_DIR/web.log" npx vite preview --host 127.0.0.1 --port "$PORT" --strictPort)
  fi
fi
wait_for "http://127.0.0.1:$PORT/" 60 "UI" || die "UI did not start; see .run/logs/web.log"
[ "$(http_code "http://127.0.0.1:$PORT/api/health")" = 200 ] && ok "UI → API proxy works" || warn "UI cannot reach the API through /api"

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
cat <<MSG

  Open the app:   http://localhost:$PORT
  API docs:       http://localhost:$API_PORT/docs
  From a laptop:  ssh -N -L $PORT:127.0.0.1:$PORT -L $API_PORT:127.0.0.1:$API_PORT $(whoami)@${HOST_IP:-<server>}
  3D scan link:   http://localhost:$PORT/hide-viewer?scan=zebra-1
  Health:         scripts/status.sh      Stop: scripts/stop.sh
MSG
