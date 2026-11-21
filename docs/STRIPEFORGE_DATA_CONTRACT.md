# STRIPEFORGE scientific analysis data contract (as implemented)

**Status: implemented; live persistence blocked.** Updated 2026-11-21 from the code in `backend/app` and `frontend/src`.
The results table migration `a8d3f2c91b40` is **prepared but NOT applied** to live Supabase (awaiting approval), so on the
live system `/api/v1/analyses/capabilities` reports both modules unavailable and submissions return 503. Everything
below is verified against the code and tests listed in §17.

## 1. Status summary

| Area | State |
|---|---|
| Vendored Member 1 + Member 2 code | 29/29 files byte-identical to the authoritative commits (independently re-verified) |
| Worker (spawned process) on real images | Verified: both modules, artifacts produced, no path leakage |
| API + worker + private Storage + rolled-back DB transaction | Verified by `test_real_fastapi_combined_analyses_with_live_supabase_storage` |
| Persisted analyses in live Supabase | **Blocked**: table missing until `a8d3f2c91b40` is applied |
| Frontend (explorer drawer, results, artifacts, history, assistant link) | Implemented; live submit disabled by capability state |

## 2. Authoritative scientific sources

| Module | Function | Commit | Library schema |
|---|---|---|---|
| Member 1 stripe morphology (PR #13) | `research.member1.models.api.analyze_stripes` | `871e2956a3cda8d3fb08433a8450a3718e9e312f` | `1.0.0` |
| Member 2 spatial frequency (PR #12) | `research.member2.science.safe_analyze` | `ff827ba826f4fa8e34acf3ba41528f91a0252c1e` | `stripecode.science.v1` (envelope `stripecode.science.envelope.v1`) |

Constants: `backend/app/integrations/science/constants.py`; frontend mirror: `frontend/src/lib/analysisResults.js`
(`PINNED_COMMITS`). Earlier hashes (`127b563…`, `96a69a45…`) are superseded and appear nowhere in the code.
MegaDescriptor v1 (`integration/v1/`) is not vendored or modified.

## 3. Provenance and vendored package

- Location: `backend/third_party/stripecode/` with `PROVENANCE.md` (file, source commit, SHA-256 for 29 files).
- Produced by `backend/scripts/vendor_stripecode.py` (refuses to run without `--approve`).
- Shared files (`member1_dhanushya/`, `member2_nisan/`, `research/__init__.py`, `research/member2/**`) come from
  `ff827ba`; `research/member1/**` from `871e295`. No file is edited.
- Runtime dependencies: `backend/requirements-science.txt` (numpy, scipy, opencv-python-headless, scikit-image,
  matplotlib). No torch is required for these two modules.
- The web process never imports `research`, `member1_dhanushya` or `member2_nisan`; only the worker does
  (`app/integrations/science/__init__.py`, covered by `test_probe_capabilities_*`).

## 4. Image input contract

- Input is always a **stored image**: `image_id` = `image_assets.id` (UUID). Images enter via the existing
  `POST /api/v1/images` (JPEG/PNG/WebP, ≤ 10 MB). No upload or file path is accepted by analysis endpoints.
- The worker downloads the bytes from the private bucket and decodes them with Pillow
  (`app/integrations/science/decode.py:decode_canonical_rgb`):
  `ImageOps.exif_transpose` → `convert("RGB")` → C-contiguous `uint8 (H, W, 3)`. No resizing.
  Alpha is discarded (no compositing).
- `image_assets.width/height` are stored EXIF-oriented, so ROI validation and decoding use the same pixel grid
  (`tests/unit/test_exif_orientation.py`).

## 5. ROI convention and validation

Request shape `{"x": int, "y": int, "width": int, "height": int}`: image pixels of the EXIF-oriented image, origin
top-left, x right, y down, half-open (`x … x+width-1`). Validation order:
1. Pydantic (`CropBox`): `x, y ≥ 0`, `width, height ≥ 2` → 422 `validation_error`.
2. Service (`validate_and_resolve_roi`): `width, height ≥ 16`, rectangle inside the image → 422 `validation_error`.
3. Limits (§15) → 422 `analysis_limit_exceeded` with `details`.

Omitted `roi` = whole image `{0, 0, W, H}` stored on the job. `roi_mode` records how each module used it:

| Module | ROI given | ROI omitted | Library call |
|---|---|---|---|
| Member 1 | `mask` | `auto` | full image + `(H, W)` uint8 mask, 255 inside the rectangle; `auto` passes `roi=None` (Member 1's own `gray > 12` background mask) |
| Member 2 | `box` | `box` | `roi=[x, y, width, height]` plain ints; Member 2 crops and analyses only the box |

Member 1's pre-processing (illumination correction, CLAHE, Otsu) runs on the whole image, so pixels outside the ROI
can influence its results; Member 2 sees only the box. Outputs of the two modules are never merged.

## 6. Morphology request and response

`POST /api/v1/analyses/stripe-morphology`
```json
{"image_id": "<uuid>", "roi": {"x": 0, "y": 0, "width": 512, "height": 512}, "config": {"clahe_clip_limit": 3.0}}
```
`config` (all optional, extra keys rejected): `clahe_clip_limit` (>0, finite), `adaptive_block_size` (int ≥ 3; Member 1
bumps even values to odd), `min_stripe_area` (int ≥ 1), `orientation_sigma` (>0, finite), `min_branch_length` (int ≥ 1).
Library defaults: 3.0 / 51 / 40 / 3.0 / 15. Only supplied keys are stored in `parameters.config`.

`result` = Member 1 output verbatim except the four `*_reference` fields, which hold artifact names:
`schema_version`, `input_and_region_metadata` (`source_id`, `content_hash`, `image_dimensions`, `valid_roi_pixels`,
`roi_coverage_ratio`), `segmentation_status` (`SUCCESS` | `WARNING`), `quality_metrics` (`contrast_ratio`,
`edge_sharpness`, `confidence_score`), `stripe_mask_reference` → `mask`, `orientation_map_reference` → `orientation`,
`width_map_reference` → `width`, `visualization_reference` → `overlay`, `width_statistics` and `spacing_statistics`
(`mean_px`, `median_px`, `std_px`, `min_px`, `max_px`, `p10_px`, `p90_px`, `sample_count`), `orientation_statistics`
(`dominant_angle_deg`, `mean_angle_deg`, `circular_variance`, `mean_coherence`, `orientation_entropy`,
`angular_convention`), `curvature_statistics` (`mean_curvature`, `median_curvature`, `std_curvature`, `p90_curvature`,
`curvature_unit`), `branching_statistics` (`junction_count`, `endpoint_count`, `branch_count`,
`junction_density_per_kpx`), `stripe_density` (`black_stripe_fraction`, `width_to_spacing_ratio`),
`measurement_units`, `warnings`, `processing_time_seconds`.

Member 1 failure (`status: "FAILED"`; since `871e295` also `segmentation_status: "FAILED"`) → job `failed`,
`error_code: analysis_failed`, generic message (Member 1 messages can contain paths and are only logged).

## 7. Spatial-frequency request and response

`POST /api/v1/analyses/spatial-frequency`
```json
{"image_id": "<uuid>", "roi": {"x": 32, "y": 32, "width": 256, "height": 256},
 "options": {"filter_type": "bandpass", "cutoff_cpp": 0.12, "band_low_cpp": 0.03}}
```
`options` mirrors `request_schema_v1.json` without `roi`/`source_reference`: `filter_type` ∈ `gaussian|butterworth|bandpass`
(default `gaussian`), `cutoff_cpp` 1e-5–0.5 (default 0.06), `band_low_cpp` 1e-5–0.5 (default 0.03), and for band-pass
`band_low_cpp < cutoff_cpp` (422 otherwise). The server sets `source_reference` to the image id.

`result` = Member 2 `result` object verbatim except `files`, which becomes `{name: name}` for the five artifacts
(`analysis.json` is never stored or returned): `schema_version`, `source_reference`, `roi`, `files`, `frequency`
(`cycles_per_pixel`, `period_pixels`, `confidence`, `caveat`), `spectrum` (`radial_bins_cycles_per_pixel`,
`radial_energy_fraction`, `orientation_bins_radians`, `orientation_energy_fraction`), `negative_control` (`method`,
`seed`, `spectrum`), `measurements` (`mean_intensity`, `intensity_std`, `dark_fraction`, `orientation_valid_fraction`),
`filter`, `ranking` (null), `candidate_evidence` (null), `warnings` (4 fixed caveats).

`filter` keys differ by type: Gaussian/Butterworth → `mode: "exploratory"`, `filter`, `cutoff_cycles_per_pixel`,
`filter_parameters`, … and its own `warnings`; band-pass → `mode: "image_space_bandpass"`, `low_cycles_per_pixel`,
`high_cycles_per_pixel`, `display_midpoint`.

**The dominant frequency, spectrum, orientation and measurements are computed on the unfiltered ROI crop**
(`interface_v1.py`); the filter only produces the `filtered` artifact. Observed on real images: band-pass
0.03–0.12 cycles/pixel with a reported dominant 0.0078–0.011 cycles/pixel.

Member 2 `ok: false` → job `failed`, `error_code` = Member 2 `error.type`; the message is passed through only for
`ValueError`/`TypeError` without path characters, otherwise generic.

## 8. Combined analysis

`POST /api/v1/analyses/combined`
```json
{"image_id": "<uuid>", "roi": {"x": 32, "y": 32, "width": 256, "height": 256},
 "morphology_config": {}, "frequency_options": {"filter_type": "gaussian", "cutoff_cpp": 0.06}}
```
One request validates the ROI for both modules, checks queue capacity for **two** jobs, and inserts both in one
transaction (all or nothing). Response 202:
`{"stripe_morphology": <job>, "spatial_frequency": <job>, "roi_semantics_note": "<text>"}`.
The jobs run sequentially through the single worker and are reported separately. The frontend shows a "combined"
banner only for the two jobs of one submission (same image and ROI); after a reload it re-pairs jobs only when image
and ROI match and `created_at` differs by ≤ 2 s (`inferPairFromHistory`). Unrelated runs are never shown as one analysis.

## 9. Endpoints and status codes

Prefix `/api/v1/analyses`:

| Method | Path | Success | Errors |
|---|---|---|---|
| GET | `/capabilities` (`?refresh=true` re-probes) | 200 | — |
| POST | `/stripe-morphology` | 202 job | 404 `not_found` (image), 422 `validation_error` / `analysis_limit_exceeded`, 503 `analysis_unavailable` / `analysis_busy` |
| POST | `/spatial-frequency` | 202 job | same |
| POST | `/combined` | 202 `{stripe_morphology, spatial_frequency, roi_semantics_note}` | same |
| GET | `` (list; `image_id`, `kind`, `status`, `limit` 1–100, `offset`) | 200 `Page` | 422, 503 `analysis_unavailable` (table missing) |
| GET | `/{id}` | 200 job | 404, 422, 503 |
| GET | `/{id}/artifacts/{name}/url` (`expires_in` 1–3600) | 200 `{url, expires_in, expires_at}` | 404 (job/artifact/object), 422, 502 `storage_error`, 503 |
| DELETE | `/{id}` | 204 | 404, 409 `analysis_running`, 503 |

Capabilities: `{stripe_morphology: {available, reason, source_commit, schema_version}, spatial_frequency: {…},
limits: {max_pixels, max_source_pixels, max_dimension, queue_limit, timeout_seconds}}`. A module is `available` only if
the vendored entrypoint exists, the scientific packages are importable, **and** the `stripe_analyses` table exists
(otherwise reason: migration `a8d3f2c91b40` pending).

## 10. Job object and lifecycle

`AnalysisJobRead`: `id`, `image_id`, `kind` (`stripe_morphology` | `spatial_frequency`), `status`, `roi`, `roi_mode`,
`parameters` (`{"config": …}` or `{"options": …}`), `provider` (`function`, `library_schema_version`,
`source_commit`), `result` (null until completed), `artifacts` (names only), `error_code`, `error_message`,
`created_at`, `started_at`, `completed_at`, `updated_at`. Storage paths are never serialised.

`pending` → `running` → `completed` | `failed`. A single dispatcher (asyncio task in the API process) claims the oldest
pending job (`FOR UPDATE SKIP LOCKED`) and runs it in a fresh spawned process. Failure codes: `analysis_failed`,
Member 2 error types (`ValueError`, `TypeError`, …), `timeout`, `worker_error` (worker exit without output, or any crash
outside the worker — the job is marked failed instead of staying `running`), `storage_error`, `interrupted` (job was
`running` when the API restarted; recovered at startup). Member 1 `WARNING` results are `completed`.

Polling (frontend `waitForAnalysis`): `GET /{id}` after 1 s, interval ×1.5 up to 5 s, paused while the tab is hidden,
stops on `completed`/`failed`, abort, or after `timeout_seconds + 30 s` per job (combined: ×2).

## 11. Error format

All errors use the application envelope
`{"error": {"code", "message", "details"?, "request_id"}}` with the `X-Request-ID` header; library exception text
and paths are only logged.

## 12. Database persistence

Table `stripe_analyses` (migration `a8d3f2c91b40`, revises `4fa9f00adf31`): UUID PK (`gen_random_uuid()` default),
`image_asset_id` FK → `image_assets.id` ON DELETE RESTRICT, `kind`/`status`/`roi_mode` VARCHAR(20) with CHECKs,
`roi`/`parameters`/`provider`/`result`/`artifacts` JSONB, `error_code` VARCHAR(80), `error_message` TEXT,
`started_at`, `completed_at`, `created_at`/`updated_at` (`clock_timestamp()`), CHECKs `failed_has_error`,
`completed_has_time`, `time_order`, indexes `(image_asset_id, created_at)` and `(status, created_at)`, RLS enabled,
all privileges revoked from `anon`/`authenticated`. An image with analyses cannot be deleted (409 `image_in_use`).
**Not applied to live Supabase**; see `FINAL_INTEGRATION_READINESS.md` for the review and commands.

## 13. Private artifact storage

- Worker writes PNGs into a private temp dir (`mkdtemp(prefix="sf-")`, mode 0700; Member 2 gets a new child dir) that
  is always deleted. Only files inside that dir, by the expected names, are read back.
- Upload to the private bucket `zebra_images` at `analysis/<YYYY>/<MM>/<job id>/<artifact>.png` (non-overwriting).
  If any upload fails, already-uploaded objects are deleted and the job fails with `storage_error`.
- `artifacts` column = `{name: storage_path}`; clients only see names and get short-lived signed URLs
  (default 60 s; the explorer requests 600 s and refreshes once on image error). Deleting a job deletes its objects
  after the commit.
- Artifact names: Member 1 `mask`, `orientation`, `width`, `overlay` (full image size); Member 2 `original_roi`,
  `filtered`, `intensity_mask`, `orientation`, `spectrum` (ROI size; `spectrum` is a frequency plot).

## 14. Measurements, units and interpretation

| Field | Unit / meaning |
|---|---|
| Member 1 width/spacing statistics | pixels (`measurement_units.spatial`: physical scale not calibrated) |
| Member 1 orientation angles | degrees, axial [0, 180) (`angular_convention`) |
| Member 1 curvature | 1/pixels (`curvature_unit: inverse_pixels`) |
| Member 1 density ratios | dimensionless [0, 1] |
| Member 1 `quality_metrics.confidence_score` | segmentation-quality heuristic (contrast, sharpness, density) — not an identity probability |
| Member 1 `content_hash` | 16 hex chars of SHA-256 over the first 65,536 bytes of decoded pixels — not the stored file hash |
| Member 2 `cycles_per_pixel`, `period_pixels` | image space, unfiltered ROI; not physical widths |
| Member 2 `frequency.confidence` | FFT peak strength, not a probability; no threshold defined by Member 2 |

The UI shows missing values as "unavailable", labels the results "Observed measurements", shows Member 1 warnings and
all Member 2 caveats, and states that region measurements neither identify an individual nor show that two regions
belong to different zebras. The Gemini assistant is instructed with the same rules (§16).

## 15. Worker, limits and queue

| Setting (`backend/.env`) | Default |
|---|---|
| `ANALYSIS_MAX_PIXELS` — pixels analysed (Member 1: whole image; Member 2: ROI) | 4,000,000 |
| `ANALYSIS_MAX_SOURCE_PIXELS` / `ANALYSIS_MAX_DIMENSION` — decode guard | 12,000,000 / 8192 |
| `ANALYSIS_QUEUE_LIMIT` — pending jobs (combined needs 2 free) | 3 |
| `ANALYSIS_TIMEOUT_SECONDS` — hard kill of the worker process | 120 |
| `ANALYSIS_TMP_DIR`, `SCIENCE_VENDOR_DIR` | system temp, `backend/third_party/stripecode` |

Worker environment: `OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `MPLBACKEND=Agg`,
`cv2.setNumThreads(2)`; one job at a time. Measured worker runs (spawn + import + analysis, this host): Member 1 on the
512×512 fixture 14.0 s on the first (cold) run, 2.4 s on a field photograph with a 512×512 ROI; Member 2 on a 256×256 ROI
1.1–3.4 s. Ryzen 3 / 8 GB timings are not measured.

## 16. Frontend integration

| File | Role |
|---|---|
| `src/services/stripeAnalysis.js` | All `/analyses` calls; combined via `POST /analyses/combined`; polling; error messages |
| `src/lib/analysisResults.js` | Pinned commits, same-ROI pairing, retry request, Member 2 filter description, "unavailable" formatting (unit-tested) |
| `src/components/explorer/AnalysisDrawer.jsx` | Morphology / Frequency / Combined tabs, config forms, limits, unavailable reason, progress, retry |
| `src/components/explorer/ScientificResults.jsx` | Separate Member 1 and Member 2 panels, provenance, warnings, spectra with negative control |
| `src/components/explorer/ArtifactGallery.jsx`, `AnalysisHistory.jsx` | Signed-URL artifacts / overlays; per-image history |
| `src/pages/explorer/StripeExplorerPage.jsx` | Orchestration; "Explain with Gemini" → `/assistant?image=<id>&analyses=<ids>` |

Retry resubmits the failed job's own image, ROI (`null` for `auto`) and parameters.
Gemini (`POST /api/v1/assistant/ask`): context is built server-side only from persisted records; analyses are
included only when the table exists (`analysis_ids` without it → 503 `analysis_unavailable`).

## 17. Test evidence (2026-11-21)

| Check | Result |
|---|---|
| Vendored files vs commits `871e295` / `ff827ba` | 29/29 identical (independent `git show` + SHA-256) |
| Requested backend set (`test_science_adapter`, `test_exif_orientation`, `test_api_analyses`, `test_api_assistant`) | 36 passed |
| Full backend suite | 329: 328 passed, 1 failed (`test_migration_at_head`, expected), 0 skipped |
| Real worker on `tests/fixtures/zebra1/flank_left_mid.png` (Member 1 fixture, SHA-256 matches `871e295`) and a field photograph | both modules `ok`, all artifacts, no path leakage |
| Frontend `npm test` / lint / build | 18 passed / 0 errors, 0 warnings / built |
| Browser (headless Chromium, live servers) | all routes render; explorer shows the unavailable reason and authoritative commits; assistant answers with both sections |

## 18. Known limitations and blockers

1. **Migration `a8d3f2c91b40` not applied** → no persisted analyses on the live system; the full UI analysis flow and
   a record-grounded Gemini explanation cannot be demonstrated live.
2. `tests/integration/test_database.py::test_migration_at_head` fails until the migration is applied (expected).
3. Analysis integration tests create `stripe_analyses` inside their rolled-back transaction on the live database
   (transactional DDL; nothing persists).
4. Physical scale is uncalibrated: all spatial values are pixels.
5. No authentication: analyses and artifacts are reachable by anyone who can reach the API.
6. Ryzen 3 / 8 GB performance not measured.
