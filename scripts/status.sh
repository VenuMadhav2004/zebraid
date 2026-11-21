#!/usr/bin/env bash
# Read-only health report: toolchain, configuration (names only), services, features, database migration state.
source "$(dirname "$0")/lib.sh"
set +e

info "Toolchain"
[ -x "$PY" ] && ok "$("$PY" --version) (backend/.venv)" || warn "backend/.venv missing: scripts/setup.sh"
NB="$(find_node_bin)" && ok "node $("$NB/node" -v)" || warn "Node.js >= 18 not found"
[ -x "$PY" ] && { "$PY" -m pip check >/dev/null 2>&1 && ok "pip check clean" || warn "pip check reports problems"; }

info "Configuration (backend/.env; values are never shown)"
for k in DATABASE_URL SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY GEMINI_API_KEY RECOGNITION_MODEL_PATH HIDE_SCANS_DIR; do
  env_has "$BACKEND/.env" "$k" && ok "$k set" || warn "$k not set"
done
[ -d "$BACKEND/third_party/stripecode" ] && { "$PY" "$BACKEND/scripts/vendor_stripecode.py" --check >/dev/null 2>&1 && ok "vendored research code verified" || warn "vendored research code verification FAILED"; }

info "Services"
API="http://127.0.0.1:$API_PORT"
for u in "$API/health" "$API/health/db"; do c="$(http_code "$u" 15)"; [ "$c" = 200 ] && ok "$u" || warn "$u -> $c"; done
for p in "$WEB_PORT" "$DEV_PORT"; do c="$(http_code "http://127.0.0.1:$p/")"; [ "$c" = 200 ] && ok "UI on port $p (proxy /api: $(http_code "http://127.0.0.1:$p/api/health"))"; done

if [ "$(http_code "$API/health")" = 200 ]; then
  info "Features"
  "$PY" "$ROOT/scripts/features.py" "$API"
fi

info "Database migrations (read-only)"
cur="$(cd "$BACKEND" && "$PY" -m alembic current 2>/dev/null | tail -1 | awk '{print $1}')"
head="$(cd "$BACKEND" && "$PY" -m alembic heads 2>/dev/null | tail -1 | awk '{print $1}')"
if [ -n "$cur" ] && [ "$cur" = "$head" ]; then ok "database at head ($head)"
else warn "database at '${cur:-unknown}', code head is '${head:-unknown}': pending migration (see scripts/migrate.sh)"; fi
