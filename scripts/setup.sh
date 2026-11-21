#!/usr/bin/env bash
# One-time setup. Usage: scripts/setup.sh [--science] [--skip-frontend]
#   --science   also install CPU PyTorch + scientific packages (stripe analysis, MegaDescriptor recognition)
source "$(dirname "$0")/lib.sh"

SCIENCE=0; SKIP_FE=0
for a in "$@"; do
  case "$a" in
    --science) SCIENCE=1 ;;
    --skip-frontend) SKIP_FE=1 ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) die "unknown option $a" ;;
  esac
done

info "Backend (Python)"
if [ ! -x "$PY" ]; then
  P="$(find_python)" || die "Python >= 3.10 not found."
  info "creating $VENV with $("$P" --version)"
  "$P" -m venv "$VENV" 2>/dev/null || "$P" -m virtualenv -q "$VENV" || die "could not create a virtualenv (install python3-venv or 'pip install virtualenv')"
fi
ok "$("$PY" --version) in backend/.venv"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r "$BACKEND/requirements.txt" -r "$BACKEND/requirements-dev.txt"
ok "API dependencies installed"

if [ "$SCIENCE" = 1 ]; then
  info "Scientific stack (CPU only, ~2 GB download the first time)"
  "$PY" -m pip install -q --index-url https://download.pytorch.org/whl/cpu torch==2.4.1 torchvision==0.19.1
  "$PY" -m pip install -q -r "$BACKEND/requirements-science.txt"
  ok "scientific packages installed"
fi
"$PY" -m pip check >/dev/null && ok "pip check: no broken requirements" || warn "pip check reported problems: run '$PY -m pip check'"

if [ ! -f "$BACKEND/.env" ]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  chmod 600 "$BACKEND/.env"
  warn "created backend/.env from the example: fill in DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY"
fi
missing=()
for k in DATABASE_URL SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY; do env_has "$BACKEND/.env" "$k" || missing+=("$k"); done
[ ${#missing[@]} -eq 0 ] && ok "backend/.env has the required settings" || warn "backend/.env is missing: ${missing[*]}"
for k in GEMINI_API_KEY RECOGNITION_MODEL_PATH HIDE_SCANS_DIR; do env_has "$BACKEND/.env" "$k" || warn "optional $k not set (that feature will report unavailable)"; done

if [ -d "$BACKEND/third_party/stripecode" ]; then
  "$PY" "$BACKEND/scripts/vendor_stripecode.py" --check >/dev/null && ok "vendored research code verified (SHA-256)" || warn "vendored research code failed verification"
fi

if [ "$SKIP_FE" = 0 ]; then
  info "Frontend (Node.js)"
  use_node
  ok "node $(node -v), npm $(npm -v)"
  # npm ci wipes node_modules (would break a running dev server), so only use it on a fresh checkout.
  if [ -d "$FRONTEND/node_modules" ] || [ ! -f "$FRONTEND/package-lock.json" ]; then
    (cd "$FRONTEND" && npm install --no-audit --no-fund --loglevel=error)
  else
    (cd "$FRONTEND" && npm ci --no-audit --no-fund --loglevel=error)
  fi
  [ -f "$FRONTEND/.env" ] || cp "$FRONTEND/.env.example" "$FRONTEND/.env"
  ok "frontend dependencies installed"
fi

info "Setup complete. Next: scripts/start.sh   (then scripts/status.sh)"
