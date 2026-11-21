# Final integration readiness (STRIPEFORGE)

Updated 2026-11-21 after verification against the running system. Statuses: PASS / PARTIAL / BLOCKED / NOT TESTED.
Contract details: `STRIPEFORGE_DATA_CONTRACT.md`. Run and demo instructions: `../README.md`.

## 1. Status

| Item | Status | Evidence |
|---|---|---|
| Vendored Member 1 `871e2956` / Member 2 `ff827ba8` | PASS | 29/29 files re-hashed against `git show <commit>:<file>` |
| Worker on real images (both modules) | PASS | authorized fixture + field photograph; artifacts produced; no path leakage |
| API → worker → private Storage → DB (rolled-back transaction) | PASS | `test_real_fastapi_combined_analyses_with_live_supabase_storage` |
| Persisted analyses on live Supabase | BLOCKED | migration `a8d3f2c91b40` not applied |
| Frontend analysis UI against live backend | PARTIAL | renders, shows the real unavailable reason; submit path covered by unit/integration tests only |
| Gemini assistant (live) | PARTIAL | live answers grounded in the real (empty) DB summary, no fabricated values, multi-turn works; record-grounded explanation of a stored analysis BLOCKED |
| 3D hide viewer | PASS | organiser-provided Zebra 1 OBJ/MTL/PNG rendered (2,174,061 vertices, 724,687 faces) in headless Chromium |
| Recognition capability (MegaDescriptor v1) | PASS (capability) | `/identifications/capabilities` available, checkpoint SHA-256 verified; live demo needs gallery data |

## Test results (2026-11-21, after all changes)

| Suite | Total | Passed | Failed | Skipped |
|---|---:|---:|---:|---:|
| Requested backend set (`test_science_adapter`, `test_exif_orientation`, `test_api_analyses`, `test_api_assistant`, `-v`) | 36 | 36 | 0 | 0 |
| Full backend `pytest` | 329 | 328 | 1 (`test_migration_at_head`, expected until migration applied) | 0 |
| `ruff check app tests scripts` | — | pass | — | — |
| Frontend `npm test` | 18 | 18 | 0 | 0 |
| Frontend `npm run lint` / `npm run build` | — | 0 errors, 0 warnings / built | — | — |
| Browser release check (headless Chromium, live servers) | 26 checks | all routes, explorer unavailable state, live Gemini answer, Zebra 1 scan, mobile | — | — |

An earlier full run (before these fixes) had one additional intermittent failure that did not recur; its name was not captured.

## 2. Migration review — `a8d3f2c91b40_add_stripe_analyses.py`

| Check | Result |
|---|---|
| Revision chain | `7f6be5c92a8f → 4fa9f00adf31 → a8d3f2c91b40` (single head) |
| Live revision (`alembic current`, read-only) | `4fa9f00adf31` |
| Table | `stripe_analyses`; columns match `app/models/stripe_analysis.py` |
| FK | `image_asset_id → image_assets.id ON DELETE RESTRICT` |
| Constraints | CHECK `kind`, `status`, `roi_mode` enums; `failed_has_error`; `completed_has_time`; `time_order` |
| Indexes | `ix_stripe_analyses_image_created (image_asset_id, created_at)`, `ix_stripe_analyses_status_created (status, created_at)` |
| RLS / grants | `ENABLE ROW LEVEL SECURITY`; `REVOKE ALL … FROM anon, authenticated` (same posture as `4fa9f00adf31`) |
| Downgrade | drops both indexes and the table (RLS/grants go with the table) |
| Compatibility | additive only; no existing table altered |

Defects found and fixed in this review (the migration had never been applied, so editing it is safe):
- `app/models/enums.py:str_enum` had been changed to `length=30`. Live enum columns are `VARCHAR(20)`, so after
  applying this migration `alembic check` would have failed with type drift on `zebras.status`, `image_assets.kind`,
  `gallery_entries.side`, `identification_runs.status`, `verifications.decision`. Restored to 20; the migration's
  `kind`/`status`/`roi_mode` now use `VARCHAR(20)` (longest value `stripe_morphology`, 17 chars).
- `id`/`created_at`/`updated_at` defaults now match the ORM mixins and earlier tables
  (`gen_random_uuid()`, `clock_timestamp()` instead of none / `now()`).
- Read-only model vs live schema comparison after the fix: no differences except the not-yet-created table.

Not executed: upgrade/downgrade were not run anywhere (no local PostgreSQL available; live DB must not be altered).
The SQL was reviewed with offline mode (no connection):
`cd backend && .venv/bin/alembic upgrade 4fa9f00adf31:a8d3f2c91b40 --sql`.

### Preflight (all read-only)

```bash
cd backend
.venv/bin/alembic current                      # expect 4fa9f00adf31
.venv/bin/alembic heads                        # expect a8d3f2c91b40 (head)
.venv/bin/alembic upgrade 4fa9f00adf31:a8d3f2c91b40 --sql   # review the exact SQL
.venv/bin/python -c "import sys; sys.path.insert(0,'.'); from sqlalchemy import text; from app.database.session import get_engine; print(get_engine().connect().execute(text(\"select to_regclass('public.stripe_analyses')\")).scalar())"   # expect None
```

### Apply (only after explicit approval)

```bash
cd backend && .venv/bin/alembic upgrade a8d3f2c91b40
```

Expected changes: one new table `public.stripe_analyses` with the constraints/indexes above, RLS on, API-role grants
revoked, `alembic_version` → `a8d3f2c91b40`. No existing rows or tables change.

### Verify after applying

```bash
.venv/bin/alembic current            # a8d3f2c91b40 (head)
.venv/bin/alembic check              # "No new upgrade operations detected."
curl -s localhost:8000/api/v1/analyses/capabilities    # both modules "available": true
.venv/bin/pytest -q tests/integration/test_database.py tests/integration/test_api_analyses.py tests/integration/test_real_scientific_and_recognition.py
```
Then run one combined analysis from the Stripe Explorer and ask Gemini about it.

### Rollback

```bash
cd backend && .venv/bin/alembic downgrade 4fa9f00adf31
```
Drops `stripe_analyses` and **its rows**; stored artifact PNGs under `analysis/` in the bucket are not deleted by the
migration (delete analyses through the API first if they must go).

## 3. Changes made in this pass

| File | Change |
|---|---|
| `backend/app/models/enums.py` | enum column length back to 20 (prevents schema drift) |
| `backend/alembic/versions/a8d3f2c91b40_add_stripe_analyses.py` | VARCHAR(20); server defaults aligned |
| `backend/app/services/stripe_analyses.py` | capabilities report unavailable while the table is missing; dispatcher marks a job failed if execution crashes outside the worker |
| `backend/app/api/v1/endpoints/analyses.py` | capabilities endpoint passes the DB session |
| `backend/app/integrations/science/worker.py` | replaced unreliable `Queue.empty()` with a bounded `get(timeout=5)` |
| `backend/app/services/assistant.py` | prompt rules: no identity claims from region measurements; state confidence/limitations, no invented threshold |
| `backend/tests/unit/test_analysis_dispatcher.py` (new), `test_science_adapter.py`, `tests/integration/test_api_analyses.py` | crash-path tests; order-independent "no research import" check; capability tests for missing/present table |
| `frontend/src/lib/analysisResults.js` (+ test, new) | pinned commits, same-ROI pairing, retry request, Member 2 filter keys, "unavailable" formatting |
| `frontend/src/services/stripeAnalysis.js` | combined via `POST /analyses/combined` (atomic); authoritative fallback commits |
| `frontend/src/components/explorer/ScientificResults.jsx` | actual Member 2 filter keys; recorded commits only; no fabricated status; observed-vs-interpretation labels; FFT caveats; region-only note |
| `frontend/src/components/explorer/AnalysisDrawer.jsx` | authoritative commits; combined description |
| `frontend/src/pages/explorer/StripeExplorerPage.jsx` | no mixing of unrelated runs; retry uses the failed job's image/ROI/parameters |
| `docs/STRIPEFORGE_DATA_CONTRACT.md`, `README.md`, this file | rewritten to the implementation |

## 4. Remaining blockers

1. Apply `a8d3f2c91b40` (needs approval) → then verify per §2.
2. `test_migration_at_head` fails until then (expected; not weakened).
3. No authentication / authorization.
4. Ryzen 3 / 8 GB laptop performance not measured.
5. The shared database is empty; demo data (zebras with reference photographs) must be registered before the demo.
