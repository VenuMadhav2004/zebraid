# STRIPEFORGE unified architecture (scientific integration)

Status: design, 2026-11-21. Nothing in this document is implemented yet. No application code was changed,
no PR was merged and no dependency was installed into the application environment.
"STRIPEFORGE" is this repository (ZebraID `backend/` + `frontend/`).

Related: `STRIPEFORGE_DATA_CONTRACT.md` (image, ROI, request/response), `STRIPEFORGE_UI_INTEGRATION_PLAN.md`,
`FINAL_INTEGRATION_READINESS.md` (blockers, file list, order), `ML_INTEGRATION_AUDIT.md` (first audit; §10 items 1, 2, 4 are superseded below).

## 1. Sources (exact commits)

| Source | Commit | Used for |
|---|---|---|
| Member 2, PR #12 head | `96a69a45f754a4b6ea2c2cad46de26115eb72303` | `research.member2.science.safe_analyze` (module byte-identical to the audited `79df3ca`) |
| Member 1, PR #13 head | `127b563da6e380a293bbfddc451f237b89a7056e` "CPU-portable morphology runtime" | `research.member1.models.api.analyze_stripes` — the **lightweight-import commit** |
| Common base | `3c0c20c` | `member1_dhanushya/`, `member2_nisan/`, `research/__init__.py`, `integration/v1/` (unchanged by both PRs) |

Member 2's own combined-import test used Member 1 `6ada2d6`, not `127b563`. The combination specified here
(`96a69a4` + Member 1 subtree from `127b563`) was built and tested for this design (see §4).

## 2. Current application (unchanged)

```
React (Vite)  ──/api──►  FastAPI app (uvicorn, 1 process)
  pages: Overview, Identify, Zebra Gallery,        app/api/v1/endpoints/*   thin routers
  Sightings, Stripe Explorer, placeholders         app/services/*           rules + commit
  services: api.js (Axios), zebraid.js,            app/repositories/*       SQLAlchemy queries
  identification.js, stripeAnalysis.js             app/integrations/supabase_storage.py
                                                   app/core/*               errors, logging, request ids
                         ┌───────────────┬──────────────────┐
                         ▼               ▼                  ▼
                 Supabase Postgres   private bucket     (no ML runtime today)
                 Alembic 4fa9f00adf31  zebra_images
```

Python 3.10.12; backend deps: fastapi 0.115.6, SQLAlchemy 2.0.36, psycopg 3.2.3, alembic 1.14.0,
httpx 0.28.1, python-multipart 0.0.20, pillow 12.3.0. No numpy/scipy/OpenCV/scikit-image/torch.

## 3. Target architecture

```
React Stripe Explorer ──POST /api/v1/analyses/{stripe-morphology|spatial-frequency}──► FastAPI
        ▲  poll GET /api/v1/analyses/{id}                                                  │ 202 + job row (pending)
        │  GET  …/artifacts/{name}/url  → signed URL (private bucket)                       ▼
        │                                                        AnalysisDispatcher (asyncio task, 1 per app)
        │                                                          │ picks oldest pending job from DB
        │                                                          ▼
        │                                         spawn ONE worker process per job (multiprocessing "spawn")
        │                                           - sys.path → backend/third_party/stripecode (combined tree)
        │                                           - decode image (canonical RGB uint8, EXIF-oriented)
        │                                           - analyze_stripes(...) or safe_analyze(...)
        │                                           - writes PNGs + sanitized result.json into private temp dir
        │                                                          │ exit / hard timeout → terminate
        │                                                          ▼
        └──────────── signed URLs ◄── upload PNGs to bucket `analysis/YYYY/MM/<job id>/<name>.png`,
                                       store sanitized result + artifact map in `stripe_analyses`,
                                       delete temp dir (always)
```

Design rules:
- The web process **never imports** `research`, `member1_dhanushya` or `member2_nisan`. Only the worker process
  does, after inserting the vendored root into `sys.path`. App startup, memory and the existing 259 tests are unaffected
  when the scientific stack is absent; the capability endpoint then reports "unavailable".
- Jobs are rows in Postgres (durable queue). No Redis/Celery. One dispatcher, one worker process at a time.
- Inputs are **stored images only** (`ImageAsset` ids). Uploads keep using `POST /api/v1/images`.
- Library outputs are stored **verbatim** except server paths, which are replaced by artifact names.
- No filesystem path, bucket path or library exception text that may contain paths reaches the client.

## 4. Combined research package layout (no PR merge)

Both PRs define the same regular top-level package `research` with disjoint subtrees; Python resolves only the
first `research` on `sys.path`, so two checkouts cannot be combined by path tricks. A **single combined tree**
is required. Shared files are identical on both sides; the only two shared files that differ were each changed
on one side only (`configs/member1/models.yaml` by #13, `member2_nisan/requirements.txt` by #12) and neither is
needed at runtime. No file conflict exists.

Proposed vendored snapshot (copy of exact files, no edits), `backend/third_party/stripecode/`:

```
third_party/stripecode/
  PROVENANCE.md                         # commits, file list, SHA-256, licence status
  research/__init__.py                  # base 3c0c20c
  research/member1/__init__.py          # 127b563
  research/member1/models/{__init__,api,segmentation,morphology,enhancements,fusion,
                           partial_hide,zebra1_processor,megadescriptor_dinov2}.py   # 127b563
  research/member2/__init__.py          # 96a69a4
  research/member2/science/{__init__.py,interface_v1.py,request_schema_v1.json,schema_v1.json}  # 96a69a4
  member1_dhanushya/__init__.py, member1_dhanushya/recognition/{__init__,engine,local_matching}.py  # base
  member2_nisan/__init__.py, member2_nisan/zebra_vision/{__init__,simulator,video}.py               # base
  member2_nisan/stripe_analysis/{__init__,features,identity_map}.py                                 # base
```

This is exactly the set of 24 repository modules loaded when both public functions are imported (measured),
plus `megadescriptor_dinov2.py` (imported inside `try/except ImportError` by Member 1's package; fails harmlessly
without torch) and the two Member 2 schema files. `__pycache__` is excluded. SHA-256 per file is listed in
`FINAL_INTEGRATION_READINESS.md`. Preferred long-term alternative: the team merges both branches upstream and the
backend pins one upstream commit (git submodule) instead of a copy.

Verified on the combined tree (Python 3.10.12, numpy 1.26.4, scipy 1.14.1, opencv-python-headless 4.11.0.86,
scikit-image 0.24.0, matplotlib 3.9.4, pillow 12.3.0, **no torch/timm/torchvision/pandas/jsonschema installed**):
- both import orders succeed in fresh processes; `torch`/`timm` never loaded; `research.member1.models._HAS_TORCH_MODELS is False`;
- both functions run on a real field photograph with `pandas`, `torch`, `torchvision`, `timm`, `jsonschema` blocked from import.

## 5. Dependencies (scientific worker)

Runtime-required (verified by blocking everything else): `numpy`, `scipy`, `opencv-python-headless`,
`scikit-image` (Member 1 morphology; undeclared in Member 1's original requirements, declared in `requirements-cpu.txt` of `127b563`),
`matplotlib` (imported at module level by `member2_nisan/stripe_analysis/identity_map.py`; pulls in Pillow).
Not required at runtime: torch, torchvision, timm, pandas, jsonschema (used only for tests / optional validation).

Proposed pins (the exact versions tested together with the app's Pillow; `pip check` clean):
`numpy==1.26.4`, `scipy==1.14.1`, `opencv-python-headless==4.11.0.86`, `scikit-image==0.24.0`, `matplotlib==3.9.4`.
Footprint ≈ 515 MB of site-packages. Conflict note: Member 2 `requirements-cpu.txt` pins `Pillow==10.4.0`;
the app uses 12.3.0 and matplotlib/both APIs work with it — do **not** adopt that pin. Do not use the system
Python (numpy 1.22.2, no scikit-image).

Placement: add to `backend/requirements-science.txt` (optional extra), install into the existing backend venv.
The app runs without it (capability reports unavailable).

## 6. Worker model and limits (Ryzen 3 / 8 GB laptop)

Measured on this host (AMD EPYC 7742, threads capped at 2, fresh process per run, one real 2235×1253 photograph
resized to each size; each process ≈ 66 MB before the call; cold import of both modules 0.5 s / 99 MB):

| Input | M1 `analyze_stripes` | M1 peak RSS | M2 `safe_analyze` | M2 peak RSS |
|---|---:|---:|---:|---:|
| 512×512 (0.26 MP) | 0.41 s | 121 MB | 0.57 s | 135 MB |
| 0.5 MP | 0.59 s | 146 MB | 0.73 s | 171 MB |
| 1.0 MP | 1.05 s | 259 MB | 1.12 s | 243 MB |
| 2.0 MP | 1.99 s | 377 MB | 1.94 s | 393 MB |
| 2.8 MP | 3.14 s | 521 MB | 2.91 s | 490 MB |

Roughly linear: ≈1.1 s and ≈165 MB per MP (M1). A Ryzen 3 laptop was not available; budget 1.5–3× these times.
Artifacts at 2.8 MP: M1 ≈ 9.9 MB (4 PNGs, largest 4.9 MB), M2 ≈ 13 MB (5 PNGs, largest 4.9 MB).

Limits (configurable in `Settings`, defaults for an 8 GB laptop running browser + Vite + API):

| Setting | Default | Reason |
|---|---|---|
| `analysis_max_pixels` (pixels actually analysed) | 4,000,000 | ≈0.73 GB M1 peak (extrapolated), same default as Member 2's adapter; largest single PNG stays < 10 MB bucket limit |
| `analysis_max_source_pixels` (decode guard) | 12,000,000 and longest side ≤ 8192 | dataset max seen 8.74 MP; Member 2 rejects > 8192 px |
| worker processes | 1 | 8 GB RAM; one job at a time |
| `analysis_queue_limit` (pending jobs) | 3 | beyond → 503 `analysis_busy` |
| `analysis_timeout_seconds` | 120 | hard kill of the worker process |
| thread env in worker | `OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `cv2.setNumThreads(2)` | leave cores for UI/API |
| `MPLBACKEND` | `Agg` | headless matplotlib |

Why a process per job, not a thread: a thread cannot be killed on timeout, native memory is returned to the OS only
when the process exits, and a crash in native code must not take down the API. Cost: 0.5 s import per job.

## 7. Private artifact storage and signed URLs

- Temp: `Settings.analysis_tmp_dir` (default system temp), per job `tempfile.mkdtemp(prefix="sf-")`, mode 0700;
  Member 2 gets a **new child path** inside it (it requires a non-existent directory). Deleted in `finally`.
- Bucket: existing private `zebra_images`, keys `analysis/<YYYY>/<MM>/<job uuid>/<artifact name>.png`, uploaded with
  the existing non-overwriting `SupabaseStorage.upload` (PNG passes the existing type sniffing and 10 MB limit).
- Record: new table `stripe_analyses` (one Alembic migration) — see data contract §6. Artifacts are **not**
  `ImageAsset` rows (would pollute galleries, duplicate checks and the `kind` CHECK).
- Serving: `GET /api/v1/analyses/{id}/artifacts/{name}/url` → existing `SupabaseStorage.signed_url` (1–3600 s,
  default 60). Only names from the job's stored artifact map are accepted (no path parameters).
- Deletion: `DELETE /api/v1/analyses/{id}` deletes the row, commits, then deletes the objects (same order as images).
  `images.usage_counts` gains `stripe_analyses`, so an analysed image cannot be deleted while analyses exist.
- Quota: ≈10–18 MB per full-size job; on a 1 GB storage plan that is ≈60–100 jobs. Retention is manual (delete).

## 8. MegaDescriptor v1 preservation

- `integration/v1/` (FastAPI router `prefix='/api/v1'`, routes `/model/health`, `/gallery/status`,
  `/gallery/images`, `/gallery/images/{image_id}`, `/identify`, `/vision/simulate`, `/vision/identity-map`) and
  `member1_dhanushya/recognition/` are unchanged in both PRs and are **not modified, not mounted and not vendored as
  routes** by this design.
- The worker imports `member1_dhanushya.recognition` only because Member 1's package imports `fusion` →
  `local_matching`; at import time `engine.py` loads only numpy/cv2/`member2_nisan` (torch/timm are imported inside
  functions), creates no model and loads no checkpoint (verified: no torch module loaded).
- Route namespace: if the v1 router were ever mounted into this app it would share `/api/v1` with existing routes;
  `/api/v1/identify` vs `/api/v1/identifications` and `/api/v1/gallery/images/{id}` vs `/api/v1/gallery/{id}` do not
  collide, but mounting is out of scope. Future identification work should call `load_recognition_model` /
  `CpuGalleryIndex` through a separate adapter feeding the existing `identification_runs` tables.
- Licence: the pinned MegaDescriptor-L-384 checkpoint is CC BY-NC 4.0 (Member 2 doc). Not needed for this phase.
- Recognition on the laptop: Member 2 measured 2.9–3.0 GiB peak RSS for the CPU recognizer; running it alongside
  scientific jobs on 8 GB is not planned in this phase.
