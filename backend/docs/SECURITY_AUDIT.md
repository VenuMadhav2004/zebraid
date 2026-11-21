# Security audit (Phase 2.5)

No credential values appear in this document.

## Credentials

| Check | Result |
|---|---|
| Real credentials in source | none. Repo-wide scan (excluding `.env`, `.venv`, `node_modules`) for the DB password, `sb_secret`, JWT prefixes and the project ref found nothing |
| `.env` excluded | `ZebraID/.gitignore` ignores `.env` and `.env.*` and keeps `.env.example`. **Note:** `ZebraID/` itself is not a git repository; the copy pushed to the team repo (`feat/venu-skeleton`) contained no `.env` (verified at push) |
| `.env.example` | placeholders only (`<project-ref>`, `<db-password>`, empty keys) |
| Service-role key | read only by `app/config.py` → `SupabaseStorage` on the backend; never logged; error messages are tested to exclude it |
| Frontend | `frontend/.env` holds only `VITE_API_BASE_URL` and `VITE_PROXY_TARGET`; no Supabase keys or DB URLs in `frontend/src` |
| Exposure history | the DB password was pasted into chat in an earlier session. **Rotate it** (Project Settings → Database) and update `backend/.env` |

## Database access

- **Connections:** lazy engine with `pool_pre_ping`, a bounded pool (5 + 5 overflow), `pool_recycle=1800`, and a connect timeout. The transaction-pooler port (6543) disables prepared statements automatically.
- **Sessions:** `get_db()` rolls back on exception and always closes; `session_scope()` commits or rolls back and then closes. Tests cover yield/close and rollback.
- **SQL injection:** all queries go through ORM/Core bound parameters. Raw `text()` is used only for constants (`select version()`, health) and for migration DDL with hard-coded table names. Search `ILIKE` input is escaped (D5).
- **Fixed info leak:** `/health/db` returned the first line of the driver exception, which can contain the pooler host and DB username. It now returns only `{status, error type, "database unreachable"}` and logs details server-side. Unit-tested.

## Storage

Private bucket, no storage policies, MIME and size limits enforced in both the client and the bucket, magic-byte checks, server-generated keys, no overwrite, bounded signed-URL TTL, and signed URLs never stored. See `STORAGE_AUDIT.md`.

## Row Level Security: current state

| Item | State |
|---|---|
| RLS enabled | all 8 `public` tables (7 domain tables + `alembic_version`); `storage.objects`, `storage.buckets` |
| Policies | **none** in `public`; **none** in `storage` |
| Table grants to `anon` / `authenticated` | **revoked** by migration `4fa9f00adf31` (previously Supabase's default `ALL`, including `TRUNCATE`, which RLS does not cover) |
| Backend role | connects as `postgres`, the table owner with `BYPASSRLS`, so it reads and writes normally |
| `service_role` | `BYPASSRLS`; keeps its grants; used only by the backend for Storage |

**Allowed access paths today:**
1. Browser → FastAPI → PostgreSQL as `postgres`.
2. FastAPI → Storage API with the service-role key.

**Denied:**
- Supabase REST/GraphQL with the anon or authenticated key on any `public` table. Tests switch to `anon` and `authenticated` inside a rolled-back transaction and get `permission denied` on every table.
- Any anonymous Storage read. A live test covers this.

**Is RLS appropriate?** Yes, for a backend-only architecture. RLS-on with no policies is deny-by-default, and revoking the grants removes paths RLS does not govern. Do not add permissive policies just to "make RLS do something".

**When authentication is introduced, decide the model first:**
- **Backend-only (recommended).** Keep the current posture. FastAPI verifies the Supabase JWT, derives the user and scopes queries itself. This needs an `owner_id` / org column via a new migration, and authorization checks in the repositories or services.
- **Direct client access.** Only if the browser must use Supabase directly. Re-grant the minimal privileges to `authenticated` per table and add policies such as `USING (owner_id = auth.uid())`, or org membership through a join table. Add `WITH CHECK` on insert/update. Keep `verifications` insert-only (no update/delete policy). For Storage, add `storage.objects` policies scoped to `bucket_id = 'zebra_images' AND (storage.foldername(name))[1] = auth.uid()::text`, which requires changing the key scheme to start with the user or org.
- **Future tables.** Supabase default privileges re-grant `anon`/`authenticated` on every new table that `postgres` creates. Each new migration must `ENABLE ROW LEVEL SECURITY` and `REVOKE ALL … FROM anon, authenticated`. `tests/integration/test_security_db.py` fails if a migration forgets.

## Residual risks

- The DB password has been exposed in chat: rotate it.
- The service-role key on the backend is all-powerful for Storage; protect the host and the `.env` file (mode 600 is set).
- CORS `allow_credentials=True` with an explicit origin list. Keep the origins explicit; never use `*`.
- `/health/db` still reports the Postgres version string (low sensitivity). Restrict it if the API becomes public.
