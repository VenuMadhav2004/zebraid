# ZebraID / STRIPEFORGE

AI-assisted zebra identification and stripe-science research platform.

- `backend/` — FastAPI + SQLAlchemy 2.0 + Alembic on Supabase PostgreSQL (psycopg 3) and a private Supabase Storage bucket.
- `frontend/` — React 19 + Vite 6 + Tailwind CSS v4 + Three.js.
- Scientific modules (vendored, unmodified): Member 1 stripe morphology `871e2956a3cd`, Member 2 spatial frequency
  `ff827ba826f4` — see [`backend/third_party/stripecode/PROVENANCE.md`](backend/third_party/stripecode/PROVENANCE.md).
- Recognition: MegaDescriptor-L-384 v1 on CPU (checkpoint is not in the repo; licence CC BY-NC 4.0).
- Gemini assistant (`gemini-2.5-flash`), grounded only in persisted records.

## Quick start (automated)

```bash
scripts/setup.sh --science   # once: venv + Python deps (+ CPU torch/science), npm deps, .env templates, vendor check
nano backend/.env            # fill DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (+ optional GEMINI_API_KEY,
                             #   RECOGNITION_MODEL_PATH, HIDE_SCANS_DIR)
scripts/start.sh             # API on 127.0.0.1:8000 + UI on 127.0.0.1:4173; prints URLs and the SSH tunnel command
scripts/status.sh            # read-only health: toolchain, config names, services, features, migration state
scripts/check.sh             # ruff + backend unit tests + frontend tests, lint, build   (--full: whole backend suite)
scripts/stop.sh              # stops only what start.sh started
scripts/migrate.sh           # read-only preview of pending DB migrations (--apply asks you to type the revision)
```

`make setup | start | start-dev | stop | status | check | check-full | migrate-plan` run the same scripts.
`scripts/start.sh --dev` runs the Vite dev server (hot reload, port 5173) instead of the production build; over an
SSH tunnel prefer the default (far fewer requests). Already-running healthy servers are reused, never duplicated.
Ports: `API_PORT`, `WEB_PORT`, `DEV_PORT` environment variables. Logs: `.run/logs/`.

## Known blockers (read first)

1. **Migration `a8d3f2c91b40` (`stripe_analyses`) is prepared but NOT applied to live Supabase.** Until it is approved
   and applied, scientific analyses cannot be stored: the Stripe Explorer shows "Analysis runtime unavailable" with
   this reason, and Gemini cannot explain stored analysis results. Review and commands:
   [`docs/FINAL_INTEGRATION_READINESS.md`](docs/FINAL_INTEGRATION_READINESS.md).
2. No authentication: anyone who can reach the API can read and change data. Use only on a trusted network / SSH tunnel.
3. Spatial measurements are in pixels (no physical calibration).

## Requirements

- Python **3.10** (tested 3.10.12).
- Node.js **18, 20 or ≥ 22** (Vite 6). On the lab host the default `node` is v12 and will not work:
  `export PATH=~/.nvm/versions/node/v22.23.4/bin:$PATH` (tested with 22.23.4).
- Supabase project: Postgres connection string, service-role key, private bucket `zebra_images`.

## Backend

```bash
cd backend
python3 -m virtualenv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
# Scientific analyses + CPU recognition (optional; app runs without them and reports "unavailable"):
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch==2.4.1 torchvision==0.19.1
.venv/bin/pip install -r requirements-science.txt
.venv/bin/pip check
cp .env.example .env      # DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY; optional GEMINI_API_KEY, RECOGNITION_MODEL_PATH
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Do **not** run `alembic upgrade head` against the shared Supabase database without approval (see blocker 1).
`alembic current` (read-only) shows the applied revision.

Checks:

```bash
.venv/bin/ruff check app tests scripts
.venv/bin/pytest -q            # full suite; uses the configured DB inside rolled-back transactions and the private bucket
```

## Frontend

```bash
cd frontend
export PATH=~/.nvm/versions/node/v22.23.4/bin:$PATH   # if your default node is older than 18
npm install
cp .env.example .env      # VITE_API_BASE_URL=/api, VITE_PROXY_TARGET=http://127.0.0.1:8000
npm run dev               # http://localhost:5173 (Vite proxies /api → backend)
npm test && npm run lint && npm run build
```

Frontend env vars are bundled into the browser: never put the service-role key, DB credentials or the Gemini key there.
Remote access: `ssh -N -L 5173:127.0.0.1:5173 -L 8000:127.0.0.1:8000 <user>@<host>`.

## API (prefix `/api/v1`)

| Area | Endpoints |
|---|---|
| Health | `GET /health`, `GET /health/db` |
| Zebras / images / gallery | `/zebras`, `/zebras/{id}`, `/images`, `/images/{id}`, `/images/{id}/url`, `/zebras/{id}/gallery`, `/gallery/{id}` |
| Sightings | `/sightings`, `/sightings/{id}` |
| Identification (MegaDescriptor v1) | `GET /identifications/capabilities`, `GET\|POST /identifications`, `/identifications/{id}`, `/candidates`, `GET\|POST /verifications` |
| Stripe science | `GET /analyses/capabilities`, `POST /analyses/stripe-morphology`, `POST /analyses/spatial-frequency`, `POST /analyses/combined`, `GET /analyses`, `GET\|DELETE /analyses/{id}`, `GET /analyses/{id}/artifacts/{name}/url` |
| Assistant | `GET /assistant/status`, `POST /assistant/ask` |
| 3D scans | `GET /hide-scans`, `GET /hide-scans/{scan_id}/files/{file_name}` (loopback clients only; set `HIDE_SCANS_DIR`) |

Interactive docs: `http://localhost:8000/docs`. Scientific contract: [`docs/STRIPEFORGE_DATA_CONTRACT.md`](docs/STRIPEFORGE_DATA_CONTRACT.md).
Errors: `{"error": {"code", "message", "details", "request_id"}}` with an `X-Request-ID` header.

## Judge demo (≈ 8 minutes)

Before: start both servers; open `http://localhost:5173`; have a zebra flank photograph ready (e.g. the authorized
fixture `backend/tests/fixtures/zebra1/flank_left_mid.png`) and, for step 10, the organiser-provided Zebra 1 scan
(`Zebra1_flat64_model.obj`, `.mtl`, `.png`).
Preparation (the shared database may be empty): in **Zebra Gallery → Register zebra**, register at least two zebras,
each with a real reference photograph, so that identification has a gallery to search. Use only photographs you are
authorized to use.

1. **Overview** (`/`): live counts from the database, API and database status badges.
   *Say:* every number comes from the API; nothing is mocked.
2. **Identify Zebra** (`/identify`): show the upload panel, capability state and identification history.
   *Say:* results are ranked candidates with similarity scores, not probabilities; a researcher must confirm.
3. **Zebra Gallery** (`/zebras`): open a profile and its reference photographs (private storage, signed URLs).
4. **Stripe Explorer** (`/stripes`) → **Library** → pick the photograph. Show real dimensions, zoom, pan, and the
   **Region** tool with a 256 × 256 ROI.
5. **Scientific analysis** card: switch between **Morphology**, **Frequency** and **Combined**; show the config fields
   and pinned commits (`871e295`, `ff827ba`).
   - *If migration `a8d3f2c91b40` is applied:* run Combined. Show progress, then the separate Member 1 panel (width,
     spacing in px; orientation in degrees, axial 0–180; curvature 1/px; branching; density; quality heuristic;
     warnings) with mask, orientation, width and overlay artifacts, and the Member 2 panel (cycles/pixel, period, FFT
     peak strength with its caveat, negative-control spectra) with its five artifacts.
   - *If not applied (current state):* show the card's exact reason and explain the pending approval. Do not claim results.
6. *Say:* Member 1 masks the full image, Member 2 crops the ROI; the panels are reported separately; region
   measurements do not identify individuals; frequency and spectrum use the unfiltered ROI.
7. **Explain with Gemini** (toolbar) → `/assistant` pre-filled with the image (and analyses when stored).
8. Ask: "What stripe measurements are recorded for this image? Do not guess values." Show the two labelled sections
   (*Observed Measurements & Recorded Data* / *Interpretation & Hypotheses*) and that missing data is stated as missing.
9. Ask a follow-up to show multi-turn history.
10. **3D Hide Viewer**: open `/hide-viewer?scan=zebra-1` (auto-loads) or click a scan under **Authorized scans on server**
    (Zebra 1–7, organiser-provided, served from `HIDE_SCANS_DIR` to loopback clients only). Show textured / clay /
    wireframe, camera presets, orbit and zoom, and the telemetry (Zebra 1: 2,174,061 vertices, 724,687 faces,
    uncalibrated model units). Local OBJ/MTL/texture files can still be loaded with the file button.
11. **Limitations** to state: analysis persistence blocked pending migration approval; pixel units only; no
    authentication; MegaDescriptor checkpoint licence CC BY-NC 4.0; laptop (Ryzen 3 / 8 GB) performance not measured.
