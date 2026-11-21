# ML integration audit: Member 1 + Member 2 scientific pipelines

Date: 2026-11-21. Audit only: no application file was changed (this report is the only new file).
The application referred to as STRIPEFORGE in the brief is this repository (ZebraID: `backend/`, `frontend/`).

## 0. Sources inspected (exact commits)

| Item | Ref | Commit |
|---|---|---|
| Member 1 (Dhanushya) | PR #13 head | `6ada2d61da5479862e110171e1d703598199d3a0` "Deliver Zebra 1 3D scan processing, stripe segmentation, morphology analysis, and public API" |
| Member 2 (Nisan) | PR #12 head | `79df3caf7ef4a448d46309fd7b71017a89a97fd5` "Verify scientific interface and prepare Member 2 handoff" |
| Common base | merge-base of both | `3c0c20c` |

Both PR heads were fetched read-only into the local clone as `refs/remotes/origin/pr/12` and `pr/13` and extracted with
`git archive` into an isolated scratch directory. Nothing was merged, checked out over a branch, or pushed.
`integration/v1/` (the MegaDescriptor v1 pipeline) is byte-identical in both PRs and unchanged from the base; it was not modified and is out of scope.

Verification method: both public functions were executed in a throwaway virtualenv (Python 3.10.12, numpy 1.26.4,
scipy 1.14.1, opencv-python-headless 4.11.0, scikit-image 0.24.0, matplotlib 3.9.4, jsonschema 4.26.0) on one real
field photograph from the shared dataset (`/home/projects/engshare/ZeHack/extracted/images/img-0000326.jpg`, 2235×1253),
a synthetic stripe image, and the documented error cases. Outputs were written only to scratch space. All numbers below
come from those runs unless marked "doc".

---

## 1. Existing application (Step 1)

| Area | Current state |
|---|---|
| Python | 3.10.12 (backend `.venv`, created with virtualenv) |
| Backend deps | fastapi 0.115.6, uvicorn 0.32.1, pydantic-settings 2.6.1, SQLAlchemy 2.0.36, psycopg 3.2.3, alembic 1.14.0, httpx 0.28.1, python-multipart 0.0.20, pillow 12.3.0. **No numpy / scipy / OpenCV / scikit-image / torch.** |
| Layout | `app/api/v1/endpoints/*` (thin routers) → `app/services/*` (business rules, commit) → `app/repositories/*` (queries, flush) → `app/models/*`; `app/integrations/supabase_storage.py`; `app/core/*` (errors, logging, middleware) |
| Upload workflow | `POST /api/v1/images` (multipart) → `validate_image` (type sniff, 10 MB) → Pillow decode check → duplicate check (sha256+kind) → `image_storage.store_image` (upload to private bucket `zebra_images` at `<kind>/<YYYY>/<MM>/<uuid>.<ext>`, insert row, delete object if insert fails) → commit (delete object if commit fails). Reads only via signed URLs (`GET /images/{id}/url`, 1–3600 s). |
| Image kinds | `ImageAsset.kind` ∈ `query`, `reference`, `crop` (DB CHECK). Crops carry `source_image_id` + `crop_bbox {x,y,width,height}`. `content_type` ∈ jpeg/png/webp (DB CHECK). |
| Identification models | `identification_runs` (status pending/running/completed/failed, `processing_metadata` JSONB, `predicted_unknown` tri-state), `identification_candidates` (rank, `similarity_score`, `score_type`, `evidence` JSONB, `matched_reference_image_id`), `verifications` (append-only human decisions). Only read + review endpoints exist; no inference endpoint. |
| Alembic head | `4fa9f00adf31`; `alembic check` clean |
| React routes | `/`, `/identify`, `/identify/runs/:runId`, `/zebras`, `/zebras/:zebraId`, `/sightings`, `/sightings/:sightingId`, `/stripes`, `/hide-viewer` (placeholder), `/assistant` (placeholder), `/reports` (placeholder), `/ui` (dev only) |
| Frontend services | `services/api.js` (Axios `api` + `apiV1`, error normalisation), `services/zebraid.js` (zebras/images/gallery/sightings), `services/identification.js` (runs/verification adapter, ML capability probe), `services/stripeAnalysis.js` (stripe-analysis adapter; currently always "unavailable") |
| Integration point already in place | Stripe Explorer (`pages/explorer/StripeExplorerPage.jsx`) has ROI selection in image pixels `{x,y,width,height}`, "Stripe characteristics" / "Analysis evidence" panels and an "Analyse region" button wired to `stripeAnalysis.analyzeRegion()`. |

---

## 2. Member 1 interface (actual)

**Location:** `research/member1/models/api.py` → `analyze_stripes`. Implementation: `segmentation.py` (`StripeSegmenter`), `morphology.py` (`StripeMorphologyAnalyzer`). Classical image processing (CLAHE, adaptive + Otsu threshold, connected components, skeleton, structure tensor). **No model weights are used by this function.**

```python
analyze_stripes(
    image: np.ndarray | str,               # RGB uint8 (H,W,3) or (H,W) gray, or a file path (read with cv2.imread, BGR->RGB)
    roi: np.ndarray | str | None = None,   # binary mask (H,W) uint8 (>0 = valid) or mask file path; resized nearest-neighbour if size differs
    config: dict | None = None,            # see below; unknown keys ignored
    save_artifacts: bool = True,
    artifacts_dir: str | None = None,      # default "research/member1/results/api_artifacts" (relative to CWD)
) -> dict                                  # schema_version "1.0.0"
```

`config` keys and defaults (from source): `clahe_clip_limit` 3.0, `adaptive_block_size` 51 (even values are bumped to odd — verified 50 → no error), `min_stripe_area` 40, `orientation_sigma` 3.0, `min_branch_length` 15.

**Exceptions that escape** (verified): `FileNotFoundError` (missing image path), `TypeError` (unsupported input type), `ValueError` (undecodable file / empty array). Failures *inside* segmentation or morphology are caught and returned as a different shape:
`{"schema_version":"1.0.0","status":"FAILED","error_message":"...","processing_time_seconds":…}` — note `status`, not `segmentation_status` (not triggered in the probe; read from source).

**Success response keys** (verified): `schema_version`, `input_and_region_metadata`, `segmentation_status` (`SUCCESS` | `WARNING` when any warning), `quality_metrics`, `stripe_mask_reference`, `orientation_map_reference`, `width_map_reference`, `visualization_reference`, `width_statistics`, `spacing_statistics`, `orientation_statistics`, `curvature_statistics`, `branching_statistics`, `stripe_density`, `measurement_units`, `warnings`, `processing_time_seconds`.

**Artifacts** (`save_artifacts=True`; verified 4 PNGs written): `stripe_<hash16>_<UTC yyyymmdd_HHMMSS>_{mask,orientation,width,overlay}.png`. The response contains **basenames only** (`*_reference`), `null` when `save_artifacts=False`.
- `mask`: binary, 255 = dark stripe.
- `orientation`: HSV-encoded (hue = angle, saturation = coherence) colour image.
- `width`: TURBO colour map of local width.
- `overlay`: RGB visualization of segmentation on the input.

**Units** (from `measurement_units`): spatial = pixels (not physical), angles = degrees in [0,180) axial, curvature = 1/pixels, density = ratio in [0,1].

**Warning codes** (from source; prefix before `:`): `ROI_TOO_SMALL`, `LOW_CONTRAST`, `BLUR_DETECTED`, `ABNORMAL_STRIPE_DENSITY`, `TEXTURE_SEAM_SUSPECTED`, `SPARSE_WIDTH_MEASUREMENTS`. Verified: 4×4 image → `ROI_TOO_SMALL`, `SPARSE_WIDTH_MEASUREMENTS`; uniform white → `LOW_CONTRAST`, `BLUR_DETECTED`, `ABNORMAL_STRIPE_DENSITY`, `SPARSE_WIDTH_MEASUREMENTS`. Warnings do not make the call fail; all statistics are then 0.

**Semantics to preserve in the UI:**
- `quality_metrics.confidence_score` is a heuristic of contrast, edge sharpness and density (`segmentation.py:152`), clipped to [0,1]. It is **not** an identity confidence or a probability; label it "segmentation quality score (heuristic)".
- `content_hash` is SHA-256 of only the first 65,536 bytes of decoded pixels, truncated to 16 hex chars: not a file hash; do not use it for deduplication (the app already stores the real `sha256`).
- Handoff doc §6: spacing is inflated (+20–50 %) on tight crops; orientation is axial (use `dominant_angle_deg`, not arithmetic means).

**Measured behaviour** (real 2235×1253 photo, CPU): 16–17 s per full-image call; 3.9 s with a quarter-image ROI mask; ≈585 MB peak RSS after the Member 1 runs. RGBA arrays were accepted and gave the same result as RGB. A non-existent ROI **path** is silently ignored (whole image analysed, no warning).

## 3. Member 2 interface (actual)

**Location:** `research/member2/science/interface_v1.py` → `safe_analyze` (wrapper around `analyze_image`); depends on the top-level package `member2_nisan` (`zebra_vision.simulator`, `stripe_analysis.features`).

```python
safe_analyze(
    image,                        # NumPy RGB or gray; uint8, uint16, or float in [0,1]. RGBA is rejected.
    output_dir,                   # must NOT exist; created; files are never overwritten
    *, roi=None,                  # [x, y, width, height] Python ints, width/height >= 16, must fit; None = whole image
    filter_type='gaussian',       # 'gaussian' | 'butterworth' | 'bandpass'
    cutoff_cpp=.06,               # 1e-5 .. 0.5 cycles/pixel (high cutoff for bandpass)
    band_low_cpp=.03,             # bandpass only: 1e-5 <= low < cutoff_cpp
    source_reference=None,        # caller label, echoed back
    recognizer=None,              # optional research AlikedResearchMatcher (see §4)
    candidate_identity=None,      # requires recognizer
) -> dict                         # envelope "stripecode.science.envelope.v1"
```

Max image dimension 8192 px (raises). Envelope: `{"schema_version":"stripecode.science.envelope.v1","ok":true,"result":{…}}` or `{"…","ok":false,"error":{"type","message"}}`. Only `ValueError`, `TypeError`, `FileNotFoundError`, `FileExistsError`, `OSError` are converted to `ok:false`; any other exception propagates.

**Verified error cases** (all returned `ok:false`, all envelopes validated against `schema_v1.json`):

| Input | `error.type` / `message` |
|---|---|
| existing `output_dir` | `FileExistsError` — message contains the **full server path** |
| ROI larger than image | `ValueError` "ROI must fit image and be at least 16x16" |
| ROI with floats | `ValueError` "roi must contain four integer coordinates" |
| bandpass low ≥ high | `ValueError` "band low cutoff must be positive and below high cutoff" |
| RGBA array | `ValueError` "Expected grayscale or RGB image with height and width >= 2" |
| unknown filter | `ValueError` "filter_type must be gaussian, butterworth or bandpass" |

**Result keys:** `schema_version` ("stripecode.science.v1"), `source_reference`, `roi`, `files` (absolute local paths: `original_roi`, `filtered`, `intensity_mask`, `orientation`, `spectrum`, all PNG; plus `analysis.json` in the directory), `frequency` (`cycles_per_pixel`, `period_pixels`, `confidence`, `caveat`), `spectrum` (radial + orientation energy fractions with bins), `negative_control` (seeded pixel-shuffle spectrum), `measurements` (`mean_intensity`, `intensity_std`, `dark_fraction`, `orientation_valid_fraction`), `filter` (parameters + its own `warnings`), `ranking`, `candidate_evidence` (both `null` without a recognizer), `warnings` (4 fixed caveats).

**Request options schema** `request_schema_v1.json` (draft 2020-12, `additionalProperties:false`): `source_reference` (1–256 chars), `roi` (4 ints, w/h ≥ 16), `filter_type`, `cutoff_cpp` (1e-5–0.5), `band_low_cpp` (1e-5–0.5). The shipped example validates. The schema does not check ROI-fits-image or low < high; the service must.

**Semantics to preserve:** `frequency.confidence` is an FFT-peak strength measure, not a probability; the intensity mask is an Otsu threshold "not a validated anatomical or stripe segmentation"; frequencies are image-space, not physical widths (all stated in the result `warnings`).

**Measured behaviour:** whole 2235×1253 image 2.5 s (gaussian), 2.8 s (bandpass); 256×256 ROI 0.07 s; ≈780 MB peak RSS for the probe process (both modules loaded). Five PNGs written per call, all present.

## 4. Optional Member 2 recognizer (not required for filtering)

`research/member2/models/aliked_adapter.py: AlikedResearchMatcher(checkpoint_dir, device='cuda')` — requires PyTorch, the `lightglue` package (separately pinned source), checkpoints `aliked-n16.pth` and `aliked_lightglue_v0-1_arxiv.pth` with pinned SHA-256, located exactly in the active `torch.hub` checkpoints directory, and CUDA unless `device='cpu'`. Its scores are local match fractions (not cosine similarity, not probability), with no calibrated unknown threshold (doc). **Not available in this environment; not proposed for this phase.**

---

## 5. Compatibility (Step 4)

| Topic | Finding |
|---|---|
| Python | All code ran on 3.10.12 (same as backend). |
| Declared deps | `member2_nisan/requirements.txt`: numpy ≥1.24,<3; scipy ≥1.10,<2; opencv-python-headless ≥4.7,<5; matplotlib ≥3.7,<4; jsonschema ≥4.18,<5 (PR #12 only); plus pytest/notebook tooling. `member1_dhanushya/requirements.txt` adds torch ≥2.1, torchvision ≥0.16, timm ≥1,<2, Pillow ≥9.1. `research/member2/science/requirements-uv.txt` pins numpy 1.24.4 / numba 0.57.1 / opencv 4.7.0.72 for a *separate* environment. |
| **Undeclared dependency** | `morphology.py` imports `skimage.morphology.skeletonize`; **scikit-image is not declared in any requirements file** of either PR. |
| **Import side effects** | `research/member1/models/__init__.py` eagerly imports `megadescriptor_dinov2` (torch, torchvision), `fusion` (`member1_dhanushya.recognition`), `enhancements`, `zebra1_processor`, `partial_hide`. Importing `research.member1.models.api` normally therefore **requires torch + torchvision** although `analyze_stripes` does not use them. (The probe bypassed the package `__init__`.) |
| Package collision | Both PRs ship the same top-level package `research` with disjoint subtrees (`research/member1/**` only in #13, `research/member2/**` only in #12). Shared code (`member2_nisan/zebra_vision`, `member2_nisan/stripe_analysis`, `research/shared`, `research/__init__.py`) is identical. They cannot be imported from two separate checkouts in one process without path tricks; one combined tree is needed. |
| Conflicts with the app | None found: the app has no numpy/OpenCV/scipy today. Pillow 12.3.0 (app) satisfies `Pillow>=9.1`. System Python has numpy 1.22.2 (too old for `>=1.24`) and no scikit-image — do not reuse it. |
| GPU | `analyze_stripes` and `safe_analyze` (without recognizer) are CPU-only (OpenCV/NumPy/SciPy). GPU is needed only for the optional recognizer / MegaDescriptor models. |
| Input formats | M1: path (anything `cv2.imread` decodes) or RGB/gray uint8 array. M2: RGB/gray uint8/uint16/float[0,1]; RGBA rejected. The app stores JPEG/PNG/WebP; decode server-side with OpenCV or Pillow and convert to RGB uint8. |
| Dimensions | M1 has no size limit (17 s at 2.8 MP). M2 rejects > 8192 px. The app's upload limit is 10 MB (bytes), not pixels. |
| Artifact locations | M1 writes to `artifacts_dir` (default inside the repo tree, relative to CWD) and returns basenames; M2 writes to a caller-supplied new directory and returns absolute paths. Neither uploads anywhere. |
| Repository hygiene | PR #13 commits `__pycache__/*.pyc` (16 files across both extracts). Exclude when vendoring. |
| Private assets not in GitHub | Zebra 1 scan (`Zebra1_flat64_model.obj/.mtl` + texture; docs say private), ALIKED/LightGlue checkpoints, MegaDescriptor checkpoints (`megadescriptor-l-384-33b3c6f4.bin`, `stripecode-megadescriptor-l-384.bin`), DINOv2 weights (`dinov2_vitb14_pretrain.pth`, `megadescriptor-dinov2-518-49d73b44.bin`). **None are needed for `analyze_stripes` or `safe_analyze` without a recognizer.** |

---

## 6. Proposed FastAPI endpoints (based only on the two real functions)

Design principles: reuse the existing image pipeline (analyse **stored** images by `image_id`, not new uploads); server-generated output directories only; artifacts moved into the private bucket and served by signed URL; CPU work off the event loop with a concurrency limit; library error messages are not passed through verbatim (paths); results stored verbatim with provenance.

Because a full-image Member 1 call takes ~17 s, analyses are **jobs**: the POST validates, records a `pending` job, runs it in a worker thread/process, and returns 202. The client polls.

| Method | Path | Calls |
|---|---|---|
| POST | `/api/v1/analyses/stripe-morphology` | `analyze_stripes(rgb, roi=<rect mask>, config=…, save_artifacts=True, artifacts_dir=<server tmp>)` |
| POST | `/api/v1/analyses/spatial-frequency` | `safe_analyze(rgb, <new server tmp dir>, roi=…, filter_type=…, cutoff_cpp=…, band_low_cpp=…, source_reference=<image id>)` |
| GET | `/api/v1/analyses` | list (filters: `image_id`, `kind`, `status`), paged like other lists |
| GET | `/api/v1/analyses/{id}` | stored job + verbatim result + artifact names |
| GET | `/api/v1/analyses/{id}/artifacts/{name}/url` | short-lived signed URL for one artifact |
| DELETE | `/api/v1/analyses/{id}` | delete record + its storage objects |

Error mapping onto the existing envelope: invalid options/ROI → 422 `validation_error`; image not found → 404 / 422 `invalid_reference`; M1 `status:"FAILED"` or M2 `ok:false` after validation → job `failed` with `error_code` = library `error.type` and a sanitised message; analysis worker capacity exhausted → 503.

## 7. Request / response JSON (from the actual schemas and probe runs)

**Stripe morphology request** (proposed body; `config` keys are exactly the five the function reads):
```json
{"image_id": "<uuid>", "roi": {"x": 0, "y": 0, "width": 1117, "height": 626},
 "config": {"clahe_clip_limit": 3.0, "adaptive_block_size": 51, "min_stripe_area": 40,
            "orientation_sigma": 3.0, "min_branch_length": 15}}
```
The rectangle is converted server-side to the `(H,W)` uint8 mask `analyze_stripes` expects (255 inside).

**Stripe morphology result** — actual output on the real photograph, whole image, `save_artifacts=False` (with artifacts on, the four `*_reference` fields are basenames, which the service replaces with artifact names):
```json
{
  "schema_version": "1.0.0",
  "input_and_region_metadata": {"source_id": "numpy_array", "content_hash": "42e097c1e4d33bc1",
    "image_dimensions": {"width": 2235, "height": 1253}, "valid_roi_pixels": 2769276, "roi_coverage_ratio": 0.9889},
  "segmentation_status": "SUCCESS",
  "quality_metrics": {"contrast_ratio": 2.4534, "edge_sharpness": 1587.9, "confidence_score": 0.803},
  "stripe_mask_reference": null, "orientation_map_reference": null, "width_map_reference": null, "visualization_reference": null,
  "width_statistics": {"mean_px": 8.68, "median_px": 8.0, "std_px": 5.06, "min_px": 2.0, "max_px": 37.15, "p10_px": 4.0, "p90_px": 15.18, "sample_count": 109016},
  "spacing_statistics": {"mean_px": 13.96, "median_px": 11.59, "std_px": 9.4, "min_px": 2.0, "max_px": 72.0, "p10_px": 4.39, "p90_px": 26.0, "sample_count": 145584},
  "orientation_statistics": {"dominant_angle_deg": 93.62, "mean_angle_deg": 92.07, "circular_variance": 0.6549, "mean_coherence": 0.5925, "orientation_entropy": 0.7294, "angular_convention": "axial_0_to_180_deg"},
  "curvature_statistics": {"mean_curvature": 0.0605, "median_curvature": 0.0471, "std_curvature": 0.0735, "p90_curvature": 0.14, "curvature_unit": "inverse_pixels"},
  "branching_statistics": {"junction_count": 3762, "endpoint_count": 5539, "branch_count": 1820, "junction_density_per_kpx": 1.3585},
  "stripe_density": {"black_stripe_fraction": 0.3601, "width_to_spacing_ratio": 0.6904},
  "measurement_units": {"spatial": "pixels (calibrated physical dimensions pending scale confirmation)", "angular": "degrees in [0, 180) axial convention", "curvature": "1 / pixels", "density": "dimensionless ratio in [0, 1]"},
  "warnings": [],
  "processing_time_seconds": 16.3436
}
```

**Spatial-frequency request** (fields exactly `request_schema_v1.json`, plus `image_id`; `source_reference` is set by the server):
```json
{"image_id": "<uuid>", "roi": [10, 10, 256, 256], "filter_type": "butterworth", "cutoff_cpp": 0.06}
```

**Spatial-frequency result** — actual `analysis.json` from the probe (ROI `[10,10,256,256]`, butterworth; floats rounded to 4 dp for this report; local paths replaced by `<output_dir>`; spectrum arrays abbreviated with `…`):
```json
{
  "schema_version": "stripecode.science.v1", "source_reference": null, "roi": [10, 10, 256, 256],
  "files": {"original_roi": "<output_dir>/original_roi.png", "filtered": "<output_dir>/filtered.png",
            "intensity_mask": "<output_dir>/intensity_mask.png", "orientation": "<output_dir>/orientation.png",
            "spectrum": "<output_dir>/spectrum.png"},
  "frequency": {"cycles_per_pixel": 0.0078, "period_pixels": 128.0, "confidence": 0.0892,
                "caveat": "global FFT peak; complex scenes, curvature and windows may bias estimate"},
  "spectrum": {"radial_bins_cycles_per_pixel": [0.0, 0.05, …, 0.5], "radial_energy_fraction": [0.9198, 0.0482, …],
               "orientation_bins_radians": [0.0, 0.3927, …, 3.1416], "orientation_energy_fraction": [0.0705, 0.034, …]},
  "negative_control": {"method": "seeded pixel shuffle", "seed": 20261121, "spectrum": {"radial_energy_fraction": [0.0102, 0.0298, …], "…": "…"}},
  "measurements": {"mean_intensity": 0.3851, "intensity_std": 0.0528, "dark_fraction": 0.0458, "orientation_valid_fraction": 0.6479},
  "filter": {"mode": "exploratory", "cutoff_cycles_per_pixel": 0.06, "filter": "butterworth",
             "filter_parameters": {"order": 2, "transfer": "1/(1+(f/fc)^(2n))", "boundary": "periodic"},
             "angle_deg": null, "degrees_per_pixel": null, "acuity_cpd": null, "distance_m": null, "scene_width_m": null,
             "contrast": 1.0, "lighting": "unspecified", "sampling_step": 1,
             "warnings": ["Physical scale is unknown; result is not calibrated to a viewing distance."]},
  "ranking": null, "candidate_evidence": null,
  "warnings": ["Intensity-derived mask is not a validated anatomical or stripe segmentation.",
               "Computational filters do not establish actual zebra perception.",
               "Image-space frequencies are not physical distances or stripe widths.",
               "A single image cannot establish individual discriminability."]
}
```

**Proposed HTTP job response** (application wrapper; the library result is stored and returned verbatim under `result`, except artifact paths → names):
```json
{"id": "<uuid>", "kind": "stripe_morphology", "status": "completed", "image_id": "<uuid>",
 "roi": {"x": 0, "y": 0, "width": 1117, "height": 626},
 "provider": {"module": "research.member1.models.api.analyze_stripes", "schema_version": "1.0.0", "source_commit": "6ada2d6"},
 "artifacts": ["mask", "orientation", "width", "overlay"],
 "result": { "...": "verbatim library output" },
 "error_code": null, "error_message": null, "created_at": "…", "completed_at": "…"}
```

## 8. Artifact storage design

- **Execution:** per job, create a server-generated private temp directory (`tempfile.mkdtemp`) — M2 requires the output directory not to exist, so pass a new child path inside it. Never accept client paths.
- **Persist:** upload each PNG to the existing private bucket under `analysis/<YYYY>/<MM>/<job uuid>/<name>.png` using the existing `SupabaseStorage.upload` (non-overwriting, PNG is an allowed type), then delete the temp directory (also on failure).
- **Record:** analyses are not images of a zebra, so do **not** store artifacts as `ImageAsset` rows (the `kind` CHECK allows only query/reference/crop, and they would pollute galleries/duplicate checks). Proposed new table (requires one Alembic migration — justified because no existing table fits):

  `stripe_analyses`: `id` uuid PK; `image_asset_id` FK → image_assets (RESTRICT); `kind` (`stripe_morphology` | `spatial_frequency`, CHECK); `status` (pending/running/completed/failed, same CHECKs as identification runs); `roi` JSONB; `parameters` JSONB (exact options passed); `provider` JSONB (module, library `schema_version`, source commit); `result` JSONB (verbatim, paths stripped); `artifacts` JSONB `{name: storage_path}`; `warnings` JSONB; `error_code`, `error_message`; `started_at`, `completed_at`; timestamps.
- **Serve:** `GET …/artifacts/{name}/url` → existing `signed_url()`; bucket paths never leave the server.
- **Delete:** deleting an analysis deletes its objects after commit (same order as image deletion). Image deletion must also be blocked (or cascade explicitly) while analyses reference it — add `stripe_analyses` to `images.usage_counts`.
- **Retention:** keep until deleted; no automatic expiry proposed.

## 9. React components requiring integration

| Component | Change |
|---|---|
| `services/stripeAnalysis.js` | Implement `getAnalysisCapability()` (probe `/openapi.json` for the new paths) and job submit/poll; keep the "unavailable" path. |
| `pages/explorer/StripeExplorerPage.jsx` | "Analyse region" → choose analysis type (morphology / spatial frequency), parameters, submit for the current **library** image + ROI, poll, show progress; list previous analyses of the image. Local files must be saved to the library first (already supported). |
| `components/explorer/Panels.jsx` → `AnalysisPanel` | Replace raw JSON with typed renderers: M1 width/spacing/orientation/curvature/branching/density tables with the reported units; M2 frequency, measurements, filter parameters, radial/orientation spectra (with negative control). Show `warnings` as badges (M1 codes; M2 caveats always visible). Label `quality_metrics.confidence_score` "segmentation quality score (heuristic)" and `frequency.confidence` "FFT peak strength"; never present either as identity confidence. |
| New `components/explorer/ArtifactGallery.jsx` | Signed-URL images for M1 `overlay/mask/orientation/width` and M2 `original_roi/filtered/intensity_mask/orientation/spectrum`, optionally overlaid on the viewer at the ROI position. |
| `pages/explorer/...` (optional) | Comparison view of two analyses' numeric outputs. |

The identification workspace (`/identify`) is unaffected: neither function produces identities, candidates or similarity scores.

## 10. Integration blockers

1. **Importing Member 1 requires torch/torchvision** via `research/member1/models/__init__.py`, although `analyze_stripes` does not use them. Options: (a) Member 1 makes the package `__init__` lazy (preferred; one-file change in their repo); (b) install CPU torch + torchvision in the backend (~1 GB+, slower startup); (c) vendor only the three needed modules. Decision needed.
2. **scikit-image is required but undeclared** in both PRs' requirements.
3. **Shared top-level package name `research`** across PRs: the backend needs one combined, pinned source tree (vendored snapshot of `research/member1/models/{api,segmentation,morphology}.py`, `research/member2/science/interface_v1.py` + schemas, `member2_nisan/{zebra_vision,stripe_analysis}`) with commit provenance, or a merged upstream branch. Vendoring is a team decision (licence/ownership).
4. **Cost:** ~17 s CPU and ~0.6 GB RSS per full 2.8 MP Member 1 call → requires background jobs, a concurrency limit and a pixel limit (or a required ROI). Downscaling would change pixel-unit measurements and is not proposed.
5. **Silent fallbacks / leaks to guard in the service:** M1 ignores a missing ROI path; M1 failure shape differs (`status:"FAILED"`); M2 error messages can contain server paths; M2 rejects RGBA (convert first); M2 catches only five exception types.
6. **New table + migration** needed for analysis records (no existing table fits). Requires approval before implementation.
7. **No authentication/authorization** in the app; both handoff documents require authorized access to inputs and artifacts. Analyses of real field photos should not be exposed beyond trusted users.
8. **Scale:** all spatial outputs are in pixels; physical units need calibration metadata that the app does not capture.
9. Optional recognizer evidence (M2) and anything using MegaDescriptor/ALIKED needs private checkpoints not in GitHub — out of scope for this phase.

## 11. Exact implementation sequence (next phase)

1. **Decide blockers 1, 3, 6** (torch-free import route, vendoring vs upstream merge, new table) with the team.
2. **Environment:** add to `backend/requirements.txt` with upper bounds: `numpy>=1.24,<2`, `scipy>=1.10,<1.15`, `opencv-python-headless>=4.7,<5`, `scikit-image>=0.21,<0.25`, `jsonschema>=4.18,<5` (matplotlib only if a vendored module imports it at runtime — `interface_v1` does not). Reinstall `.venv`; run the existing 259 tests.
3. **Vendor** the pinned modules into `backend/third_party/stripecode/` (or install the agreed package) with a `PROVENANCE.md` listing commits `6ada2d6` and `79df3ca` and file SHA-256s; exclude `__pycache__`. No edits to their code.
4. **Adapter** `backend/app/integrations/science/` — `morphology.py` (wraps `analyze_stripes`: RGB decode from bytes, rect → mask, config whitelist, normalises FAILED shape, raises on `status:"FAILED"`), `frequency.py` (wraps `safe_analyze`: validates options with `request_schema_v1.json`, ROI-fits and low<high checks, RGBA→RGB, new temp dir, sanitised errors), unit tests using synthetic images (no network).
5. **Migration** `stripe_analyses` (+ model, schemas, repository with count/list, `images.usage_counts` update). `alembic upgrade head`, `alembic check`.
6. **Service + jobs:** create pending → worker (bounded `ThreadPoolExecutor` or process pool, N=1–2) → download image bytes via `SupabaseStorage.download` → run adapter → upload artifacts → store result/commit → cleanup temp dir; timeouts; failure recording.
7. **Endpoints** from §6 with `error_responses(...)` docs; integration tests against the real DB and an in-memory storage fake; one live-storage test.
8. **Frontend:** implement `stripeAnalysis.js`, typed panels, artifact gallery and job polling in the Stripe Explorer; keep the unavailable state when the capability probe fails.
9. **Validation:** backend tests, ruff, Alembic; frontend lint/build; browser tests on the explorer with a real photograph (results must equal a direct Python call on the same bytes); mobile check.
10. Update `docs/API.md`, `docs/ARCHITECTURE.md`; record library versions and source commits in the analysis `provider` field for every stored result.
