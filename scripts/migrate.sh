#!/usr/bin/env bash
# Database migrations. Usage:
#   scripts/migrate.sh            read-only preflight: current/head revisions, pending SQL (offline), no changes
#   scripts/migrate.sh --apply    apply pending migrations to the configured (live) database; asks to type the target revision
# Rollback of the stripe analysis table: cd backend && .venv/bin/alembic downgrade 4fa9f00adf31
source "$(dirname "$0")/lib.sh"
cd "$BACKEND"
A=("$PY" -m alembic)
cur="$("${A[@]}" current 2>/dev/null | tail -1 | awk '{print $1}')"
head="$("${A[@]}" heads 2>/dev/null | tail -1 | awk '{print $1}')"
[ -n "$cur" ] || die "cannot read the current revision (check DATABASE_URL)"
info "database revision: $cur   code head: $head"
if [ "$cur" = "$head" ]; then ok "nothing to apply"; exit 0; fi
info "pending SQL (offline render, nothing executed):"
"${A[@]}" upgrade "$cur:$head" --sql 2>/dev/null | grep -vE '^(--|$)'
if [ "${1:-}" != "--apply" ]; then
  warn "not applied. This changes the shared database; get approval, then run: scripts/migrate.sh --apply"
  exit 0
fi
printf 'Type the target revision (%s) to apply it to the configured database: ' "$head"
read -r answer
[ "$answer" = "$head" ] || die "confirmation did not match; nothing applied"
"${A[@]}" upgrade "$head"
"${A[@]}" current
"${A[@]}" check && ok "migration applied and schema matches the models"
