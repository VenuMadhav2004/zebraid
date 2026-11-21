# Existing Application Test Report — STRIPEFORGE / ZebraID

**Audit Date:** 2026-11-21
**Workspace:** `/home/users/venumadhav/workspace/zebra hack/ZebraID`
**Sibling Research Repo:** `/home/users/venumadhav/workspace/zebra hack/stripecode-ai`
**Mode:** Read-only / non-destructive baseline audit (zero production DB rows modified or added; zero application code changed).

---

## 1. Executive Summary & GO / NO-GO Recommendation

| Dimension | Status | Summary |
|---|---|---|
| **Backend Core & Tests** | **PASS** | `259 passed, 0 failed, 0 skipped` (`pytest`); `ruff check` clean; 27 OpenAPI operations live. |
| **Database & Migrations** | **PASS (Empty DB)** | Supabase PostgreSQL 17.12 reachable (`~376 ms` latency); Alembic at head `4fa9f00adf31` with zero drift. All 7 domain tables currently have **0 rows**. |
| **Supabase Private Storage** | **PASS** | Private bucket `zebra_images` verified (`public: false`, `10 MB` limit, `image/jpeg`, `image/png`, `image/webp`). |
| **Frontend Lint & Build** | **PASS** | `npm run lint` (0 errors) and `npm run build` (`vite build`, 5.36 s) pass cleanly. |
| **Browser / Playwright Suite** | **NOT AVAILABLE ON HOST** | No Playwright package, Chromium/Firefox binary, or browser test files are installed in this container. All 8 frontend routes returned HTTP `200` via Vite dev server, and Vite `/api` proxy calls to FastAPI succeeded with HTTP `200`. |
| **Scientific & Demo Readiness** | **NOT READY (Expected Baseline)** | Member 1 & Member 2 research modules are not yet vendored/installed; `/api/v1/analyses/*` endpoints and `stripe_analyses` table do not exist; `/identify` has no inference submission endpoint; `/hide-viewer`, `/assistant`, and `/reports` are `PlaceholderPage` stubs; `GEMINI_API_KEY` is empty; no 3D `.obj`/`.mtl` assets are present in the workspace. |

### GO / NO-GO Recommendation
- **Baseline Health for Integration:** **GO (Proceed to Implementation Phases)** — The existing FastAPI + SQLAlchemy + Supabase + React 19 foundation is rock-solid, passes 100% of its 259 backend tests, lints cleanly, and builds cleanly.
- **Current Demo Readiness:** **NO-GO as-is** — Scientific stripe analysis (Member 1 & Member 2), identification inference, 3D Hide Viewer, Gemini Assistant, and seeded demo data are not yet wired.

---

## 2. Repository & Environment Baseline

### Git Status
- `ZebraID/` itself is **not a Git repository** (no `.git` directory).
- Sibling repository `../stripecode-ai` **is** a Git repository:
  - Current branch: `feat/venu-skeleton` (head `e3a8bf5`, clean working tree).
  - Required teammate PR refs are already present locally:
    - `origin/pr/12` → `96a69a45f754a4b6ea2c2cad46de26115eb72303` (Member 2 `safe_analyze`)
    - `origin/pr/13` → `127b563da6e380a293bbfddc451f237b89a7056e` (Member 1 `analyze_stripes`, lightweight-import commit)

### Environment Configuration (Key Presence Only — No Secrets Printed)
- `backend/.env`:
  - `APP_NAME`: `<SET>`
  - `ENVIRONMENT`: `<SET>`
  - `DATABASE_URL`: `<SET>`
  - `SUPABASE_URL`: `<SET>`
  - `SUPABASE_SERVICE_ROLE_KEY`: `<SET>`
  - `SUPABASE_STORAGE_BUCKET`: `<SET>`
  - `CORS_ORIGINS`: `<SET>`
  - **`GEMINI_API_KEY`: `<EMPTY>`** *(Blocker for Gemini Assistant live calls)*
- `frontend/.env`:
  - `VITE_API_BASE_URL`: `<SET>`
  - `VITE_PROXY_TARGET`: `<SET>`

### Runtime Versions & Installed Scientific Dependencies
- Backend Python: `3.10.12` (`backend/.venv`)
  - Installed core packages: `fastapi 0.115.6`, `SQLAlchemy 2.0.36`, `psycopg 3.2.3`, `alembic 1.14.0`, `httpx 0.28.1`, `pillow 12.3.0`, `pydantic 2.14.4`, `pytest 8.3.4`, `ruff 0.17.6`.
  - Scientific packages (`numpy`, `scipy`, `opencv-python-headless`, `scikit-image`, `matplotlib`): **Not yet installed** in `backend/.venv`.
- Frontend Node.js: `v22.23.4` (`~/.nvm/versions/node/v22.23.4/bin`)

---

## 3. Exact Test Commands & Results

| Suite | Exact Command | Passed | Failed | Skipped | Warnings / Notes |
|---|---|---:|---:|---:|---|
| **Alembic Status** | `cd backend && .venv/bin/alembic current && .venv/bin/alembic heads && .venv/bin/alembic check` | Pass | 0 | 0 | Current = Head = `4fa9f00adf31`; `No new upgrade operations detected.` |
| **Backend Lint** | `cd backend && .venv/bin/ruff check app tests` | Pass | 0 | 0 | `All checks passed!` |
| **Backend Tests** | `cd backend && .venv/bin/pytest -v --tb=short` | **259** | **0** | **0** | 137.18 s; 1 Starlette/AnyIO `DeprecationWarning`. Includes unit, DB integration, API integration, and live Supabase Storage tests. |
| **Frontend Lint** | `cd frontend && npm run lint` | Pass | 0 | 0 | `eslint .` exited 0 (no errors/warnings). |
| **Frontend Build** | `cd frontend && npm run build` | Pass | 0 | 0 | `vite build` succeeded in 5.36 s (`dist/assets/index-BdNv3sMy.js`, 451.99 kB). |
| **Live API & Proxy Probes** | `uvicorn app.main:app --host 127.0.0.1 --port 8000` + `npm run dev -- --port 5173` + `curl` probes | Pass | 0 | 0 | `/`, `/health`, `/health/db`, `/docs`, `/api/v1/`, `/openapi.json`, and Vite proxy `/api/*` all returned HTTP `200`; zero errors in server logs. |
| **Playwright Browser Tests** | Checked `playwright`, `chromium`, `firefox`, `~/.cache/ms-playwright`, repo files | N/A | N/A | N/A | **Not runnable in this environment**: neither Playwright nor a system browser binary (`chromium`/`chrome`/`firefox`) nor Playwright test scripts exist in this workspace. Previously reported 31/31 and 42/42 counts could not be re-executed here without installing Playwright + Chromium. |

---

## 4. Backend, Database & Storage Status

### Backend API (`http://127.0.0.1:8000`)
- Startup: Clean, zero errors or warnings in startup logs.
- `GET /` → `200 OK` (`{"name":"ZebraID API","docs":"/docs","health":"/health","api":"/api/v1"}`)
- `GET /health` → `200 OK` (`{"status":"ok","service":"ZebraID API","environment":"development"}`)
- `GET /health/db` → `200 OK` (`PostgreSQL 17.12`, `latency_ms: 376.2`)
- `GET /docs` → `200 OK`
- `GET /openapi.json` → **27 operations** verified:
  - Operational/meta (4): `GET /`, `GET /health`, `GET /health/db`, `GET /api/v1/`
  - Zebras (5): `GET/POST /api/v1/zebras`, `GET/PATCH/DELETE /api/v1/zebras/{zebra_id}`
  - Images (5): `GET/POST /api/v1/images`, `GET/DELETE /api/v1/images/{image_id}`, `GET /api/v1/images/{image_id}/url`
  - Gallery (3): `GET/POST /api/v1/zebras/{zebra_id}/gallery`, `DELETE /api/v1/gallery/{gallery_entry_id}`
  - Sightings (5): `GET/POST /api/v1/sightings`, `GET/PATCH/DELETE /api/v1/sightings/{sighting_id}`
  - Identifications (5): `GET /api/v1/identifications`, `GET /api/v1/identifications/{run_id}`, `GET /api/v1/identifications/{run_id}/candidates`, `GET/POST /api/v1/identifications/{run_id}/verifications`
- **Missing API surface (expected prior to integration):**
  - No `POST /api/v1/identifications` inference submission endpoint (explicitly tested as absent by `test_no_inference_or_run_creation_endpoint`).
  - No `/api/v1/analyses/*` endpoints (capabilities, `stripe-morphology`, `spatial-frequency`, job polling, artifact signed URLs, delete).
  - No Gemini Assistant backend endpoint (`/api/v1/assistant/*`).

### Database (Supabase PostgreSQL)
- Connection & Alembic: Healthy (`4fa9f00adf31` head).
- Live row counts (read-only query):
  - `zebras`: **0**
  - `image_assets`: **0**
  - `gallery_entries`: **0**
  - `sightings`: **0**
  - `identification_runs`: **0**
  - `identification_candidates`: **0**
  - `verifications`: **0**
- Note: Database is currently completely clean/empty (no demo zebra records, images, or runs seeded yet).

### Storage (Supabase Storage)
- Private bucket verified via `SupabaseStorage.from_settings().get_bucket()`:
  - `id` / `name`: `zebra_images`
  - `public`: `False` (private)
  - `file_size_limit`: `10485760` (10 MB)
  - `allowed_mime_types`: `['image/jpeg', 'image/png', 'image/webp']`
- Live storage integration tests in `tests/integration/test_api_storage_live.py` and `test_storage_integration.py` all **PASSED** inside the 259-test run.

---

## 5. Route-by-Route & Feature Classification

Classification legend:
- **Real Data**: Connected to live FastAPI / Supabase Postgres / Supabase Storage APIs.
- **Mock Data**: Uses hardcoded/fake results. *(None found — the existing codebase strictly avoids fabricating data.)*
- **UI-Only Placeholder**: Renders `PlaceholderPage` or explicit "Unavailable" shell waiting for backend integration.
- **Broken**: Runtime or logic defect.

| Route | HTTP (Vite) | Classification | Verified Current Behavior |
|---|---|---|---|
| `/` (Overview Dashboard) | `200` | **Real Data** | Live stats from `/api/v1/zebras`, `/images`, `/sightings`, `/identifications` + `/health` & `/health/db` status card + activity feed. Currently renders clean empty states because DB has 0 rows. |
| `/zebras` (Zebra Gallery) | `200` | **Real Data** | Full search, status/species filtering, sorting, URL-synced pagination, and Zebra Registration dialog backed by `/api/v1/zebras`. |
| `/zebras/:zebraId` (Zebra Profile) | `200` | **Real Data** | Profile details, edit/delete dialogs, reference photo upload (`POST /images` + `POST /zebras/{id}/gallery`), signed URL lightbox, and deletion. |
| `/sightings` & `/sightings/:sightingId` | `200` | **Real Data** | Full CRUD, location/zebra/date filtering, pagination, image attachment, and detail view backed by `/api/v1/sightings`. |
| `/identify` & `/identify/runs/:runId` | `200` | **Partial (Real Read/Review + Unavailable Submit)** | Run history, candidate comparison viewer, and human verification submission (`POST /identifications/{id}/verifications`) work against real APIs. **However**, `getMlCapability()` inspects `/openapi.json` for `POST /api/v1/identifications` and disables new inference submission (`MlUnavailableError`) because no inference endpoint exists. |
| `/stripes` (Stripe Explorer) | `200` | **Partial (Real Image/ROI/Crop + Unavailable Analysis)** | Real local/library image loading, pan/zoom/1:1/fit, pixel-accurate ROI selection, save to library, and save region as crop (`POST /images kind=crop`). **However**, `stripeAnalysis.js` hardcodes `UNAVAILABLE`; "Stripe characteristics" and "Analysis evidence" panels show "Unavailable" and "Analyse region" is disabled. |
| `/hide-viewer` (3D Hide Viewer) | `200` | **UI-Only Placeholder** | Renders `PlaceholderPage` ("Explore 3D hide scans", badge `Planned`). No Three.js/WebGL viewer or 3D assets exist. |
| `/assistant` (Gemini Assistant) | `200` | **UI-Only Placeholder** | Renders `PlaceholderPage` ("Ask questions about your research data", badge `Planned`). No chat UI, no backend Gemini endpoint, and `GEMINI_API_KEY` is empty. |
| `/reports` (Research Reports) | `200` | **UI-Only Placeholder** | Hidden route rendering `PlaceholderPage`. |

---

## 6. Critical Bugs & Demo Blockers

### Critical Bugs (Existing Code)
1. **EXIF Orientation Dimension Mismatch (`backend/app/services/images.py:inspect_image`)**
   - `inspect_image()` records pre-EXIF-rotation `(width, height)` via `Image.open(...).size`, whereas browsers decode `<img>` and report `naturalWidth/naturalHeight` **after** EXIF rotation.
   - For phone/field photos with EXIF orientations 5–8, axes are swapped, causing ROI coordinates drawn in Stripe Explorer and `crop_bbox` validation in `repositories/images.py` to fail or misalign.
   - Fix: Apply `ImageOps.exif_transpose` dimensions during `inspect_image` (while preserving original stored bytes) and apply `ImageOps.exif_transpose` during canonical scientific decoding.

### Demo Blockers (Missing Integrations & External Dependencies)
1. **No Scientific Analysis Integration (Member 1 & Member 2) [HIGH — Core Scope]**
   - `backend/third_party/stripecode/` is not vendored; scientific Python packages (`numpy`, `scipy`, `opencv-python-headless`, `scikit-image`, `matplotlib`) are not installed; `stripe_analyses` table/migration, worker/dispatcher, `/api/v1/analyses/*` endpoints, and Stripe Explorer UI integration do not exist yet.
   - *Governance note from `FINAL_INTEGRATION_READINESS.md`*: Needs confirmation to vendor the exact audited files from `../stripecode-ai` commits `127b563` (Member 1) and `96a69a4` (Member 2) and run the `stripe_analyses` Alembic migration.
2. **No Identification Inference Submission (`POST /api/v1/identifications`) [HIGH — Workflow Step 2]**
   - Existing `/identify` page disables submission because `POST /api/v1/identifications` does not exist. Per architecture docs, MegaDescriptor v1 (`integration/v1/`, `member1_dhanushya/recognition/`) must NOT be modified or mounted as part of scientific module integration, and CPU MegaDescriptor-L-384 requires ~3 GiB RAM + checkpoint. Need clarity on whether identification inference is kept out of scope for this phase or integrated via a lightweight/existing adapter.
3. **No Authorized 3D Hide Assets Found Locally [MEDIUM — Priority 7]**
   - Searched workspace and `../stripecode-ai` (including `data/raw/wits_3d`, `pr/12`, `pr/13`): **zero** `.obj`, `.mtl`, `.glb`, or `.gltf` files exist in the local workspace. Per strict rules ("Use actual authorized OBJ/MTL/texture assets. Do not fabricate 3D assets"), the 3D viewer cannot load a real zebra mesh until the authorized asset files are provided/placed in the project.
4. **Gemini API Key Missing (`GEMINI_API_KEY=<EMPTY>`) [MEDIUM — Priority 8]**
   - `backend/.env` has an empty `GEMINI_API_KEY`. The Gemini Assistant backend endpoint and grounded React chat UI can be implemented and gracefully report configuration state if the key is absent, or run live immediately once a valid key is set in `backend/.env`.
5. **Empty Database (0 Records) [MEDIUM — Demo Readiness]**
   - All 7 tables have 0 rows. For a judge demo, we will need to upload/seed at least a few real zebra photographs (e.g., from `../stripecode-ai/tests/fixtures/zebra1/` or provided field photos) via the normal UI/API workflow.
6. **No Headless Browser / Playwright Installed [LOW–MEDIUM — Verification]**
   - Automated browser verification cannot run unless Playwright/Chromium is installed (or verified via HTTP/API + manual browser).

---

## 7. Fix Priority & Time Estimates (~150 min budget)

| Priority | Task | Estimate | Dependencies / Decisions |
|---|---|---:|---|
| **P1** | Fix EXIF orientation dimensions in `backend/app/services/images.py` + unit test | 10 min | None (immediate) |
| **P2** | Vendor exact audited Member 1 (`127b563`) & Member 2 (`96a69a4`) files into `backend/third_party/stripecode/` + `PROVENANCE.md` + install `requirements-science.txt` into `backend/.venv` | 15–20 min | Uses approved commits from `../stripecode-ai` |
| **P3** | Implement `stripe_analyses` Alembic migration, SQLAlchemy model, Pydantic schemas, repository, and `images.usage_counts` update | 20 min | Approved `stripe_analyses` migration |
| **P4** | Implement canonical image decoder, Member 1 & Member 2 adapters, isolated `multiprocessing` spawn worker, bounded `AnalysisDispatcher`, private Supabase artifact upload + signed URLs, and `/api/v1/analyses/*` endpoints + unit/integration tests | 35 min | P1, P2, P3 |
| **P5** | Wire React Stripe Explorer (`stripeAnalysis.js`, `AnalysisDrawer`, typed Member 1 & Member 2 result panels, `ArtifactGallery` with viewport overlays, `AnalysisHistory`) | 25–30 min | P4 |
| **P6** | Implement 3D Hide Viewer route (real Three.js OBJ/MTL/texture loader ready for authorized assets + clear drop/load UX without fabricating meshes) & Gemini Assistant route + grounded backend endpoint (reads real DB/analysis JSON; graceful fallback if `GEMINI_API_KEY` empty) | 20 min | Authorized OBJ/MTL files for P6a; `GEMINI_API_KEY` for live P6b |
| **P7** | End-to-end verification (full `pytest`, `ruff`, `npm run lint`, `npm run build`, live API + real zebra photo analysis parity check) & demo readiness | 15 min | P1–P6 |

**Total Estimated Time:** ~140–150 minutes (fits the remaining 2.5-hour hackathon window tightly if we proceed immediately without scope creep).
