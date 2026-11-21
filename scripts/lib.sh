# Shared helpers for STRIPEFORGE scripts. Source it; do not execute.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
VENV="$BACKEND/.venv"
PY="$VENV/bin/python"

API_HOST="${API_HOST:-127.0.0.1}"   # keep 127.0.0.1: the API has no authentication
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-4173}"         # production preview
DEV_PORT="${DEV_PORT:-5173}"         # vite dev server (--dev)

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m !!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# First python >= 3.10 on PATH.
find_python() {
  local c
  for c in python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      command -v "$c"; return 0
    fi
  done
  return 1
}

# Prints the bin dir of a Node.js >= 18 (system first, then nvm installs, newest first).
find_node_bin() {
  local major d
  if command -v node >/dev/null 2>&1; then
    major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
    if [ "$major" -ge 18 ] 2>/dev/null; then dirname "$(command -v node)"; return 0; fi
  fi
  for d in $(ls -d "$HOME"/.nvm/versions/node/v* 2>/dev/null | sort -V -r); do
    major="$("$d/bin/node" -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
    if [ "$major" -ge 18 ] 2>/dev/null; then echo "$d/bin"; return 0; fi
  done
  return 1
}

use_node() {
  local bin
  bin="$(find_node_bin)" || die "Node.js >= 18 not found (Vite 6 needs 18, 20 or >= 22). Install it, e.g. 'nvm install 22'."
  export PATH="$bin:$PATH"
}

# HTTP status code of a URL ("000" when unreachable).
http_code() { curl -s -m "${2:-5}" -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo 000; }

wait_for() { # url seconds label
  local i
  for ((i = 0; i < $2; i++)); do
    [ "$(http_code "$1" 3)" = 200 ] && { ok "$3 ready ($1)"; return 0; }
    sleep 1
  done
  return 1
}

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# Lists variable NAMES present (with a non-empty value) in an env file. Values are never printed.
env_has() { grep -Eq "^$2=.+" "$1" 2>/dev/null; }
