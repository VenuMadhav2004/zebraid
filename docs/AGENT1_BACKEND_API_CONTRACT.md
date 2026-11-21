# Agent 1 — Backend & ML API Contract (STRIPEFORGE AI)

Published for Agent 2 (Frontend) coordination. All endpoints are served under `/api/v1` (proxied via Vite `/api/v1` -> `http://127.0.0.1:8000/api/v1`).

---

## 1. Scientific Stripe Analyses (Member 1 + Member 2)

Pinned source commits:
- **Member 1 (Morphology):** `871e2956a3cda8d3fb08433a8450a3718e9e312f` (`research.member1.models.api.analyze_stripes`, schema `1.0.0`)
- **Member 2 (Spatial Frequency):** `ff827ba826f4fa8e34acf3ba41528f91a0252c1e` (`research.member2.science.safe_analyze`, schema `stripecode.science.v1`)

### Endpoints
| Method | Path | Status | Description |
| --- | --- | --- | --- |
| `GET` | `/api/v1/analyses/capabilities` | `200` | Runtime availability, pinned commits, pixel/queue/timeout limits |
| `POST` | `/api/v1/analyses/stripe-morphology` | `202` | Queue Member 1 job (`roi` optional -> `mask` or `auto`) |
| `POST` | `/api/v1/analyses/spatial-frequency` | `202` | Queue Member 2 job (`roi` optional -> `box`) |
| `POST` | `/api/v1/analyses/combined` | `202` | **New:** Atomically queue both Member 1 + Member 2 jobs on the same `image_id` and `roi` |
| `GET` | `/api/v1/analyses` | `200` | Paged list (`image_id`, `kind`, `status`, `limit`, `offset`) |
| `GET` | `/api/v1/analyses/{analysis_id}` | `200` | Poll job status (`pending` → `running` → `completed` \| `failed`) & sanitized JSON result |
| `GET` | `/api/v1/analyses/{analysis_id}/artifacts/{artifact_name}/url` | `200` | Short-lived signed URL (`expires_in` 1–3600s, default 60s) for private PNG artifact |
| `DELETE` | `/api/v1/analyses/{analysis_id}` | `204` | Delete job + private storage PNGs (`409` while `running`) |

### `GET /api/v1/analyses/capabilities` — Sample Actual Response
```json
{
  "stripe_morphology": {
    "available": true,
    "reason": null,
    "source_commit": "871e2956a3cda8d3fb08433a8450a3718e9e312f",
    "schema_version": "1.0.0"
  },
  "spatial_frequency": {
    "available": true,
    "reason": null,
    "source_commit": "ff827ba826f4fa8e34acf3ba41528f91a0252c1e",
    "schema_version": "stripecode.science.v1"
  },
  "limits": {
    "max_pixels": 4000000,
    "max_source_pixels": 12000000,
    "max_dimension": 8192,
    "queue_limit": 3,
    "timeout_seconds": 120
  }
}
```

### `POST /api/v1/analyses/combined` — Request & Response (`202 Accepted`)
Request (`extra="forbid"`):
```json
{
  "image_id": "<uuid>",
  "roi": {"x": 64, "y": 64, "width": 384, "height": 384},
  "morphology_config": {
    "clahe_clip_limit": 3.0,
    "adaptive_block_size": 51,
    "min_stripe_area": 40,
    "orientation_sigma": 3.0,
    "min_branch_length": 15
  },
  "frequency_options": {
    "filter_type": "gaussian",
    "cutoff_cpp": 0.06,
    "band_low_cpp": 0.03
  }
}
```
Response (`202 Accepted`):
```json
{
  "stripe_morphology": { "...AnalysisJobRead (kind='stripe_morphology', roi_mode='mask' | 'auto')..." },
  "spatial_frequency": { "...AnalysisJobRead (kind='spatial_frequency', roi_mode='box')..." },
  "roi_semantics_note": "Member 1 (stripe_morphology) applies the ROI as a mask on the full canonical image, whereas Member 2 (spatial_frequency) crops and analyses only the ROI pixel box."
}
```
> **Note:** Combined submission requires 2 free slots in `analysis_queue_limit` (default 3); returns `503 analysis_busy` if fewer than 2 slots are available, or `503 analysis_unavailable` if the `stripe_analyses` migration (`a8d3f2c91b40`) has not yet been applied to live Supabase.

### Real Sample Result Highlights (`tests/fixtures/zebra1/flank_left_mid.png`, ROI `[64, 64, 384, 384]`)
- **Member 1 (`stripe_morphology`, artifacts: `["mask", "orientation", "width", "overlay"]`):**
  - `segmentation_status`: `"SUCCESS"`
  - `width_statistics.mean_px`: `13.97` (`median_px`: `14.0`, `std_px`: `6.22`, `sample_count`: `4489`)
  - `spacing_statistics.mean_px`: `19.12` (`median_px`: `18.39`, `std_px`: `9.5`, `sample_count`: `4503`)
  - `orientation_statistics`: `dominant_angle_deg: 13.15`, `mean_coherence: 0.7851`, `angular_convention: "axial_0_to_180_deg"`
  - `curvature_statistics`: `mean_curvature: 0.0491`, `curvature_unit: "inverse_pixels"`
  - `stripe_density`: `black_stripe_fraction: 0.4329`, `width_to_spacing_ratio: 0.7611`
  - `quality_metrics.confidence_score`: `0.9509` *(segmentation quality heuristic, NOT identity probability)*
- **Member 2 (`spatial_frequency`, artifacts: `["original_roi", "filtered", "intensity_mask", "orientation", "spectrum"]`):**
  - `frequency.cycles_per_pixel`: `0.01584`, `period_pixels`: `63.13`, `confidence`: `0.0981` *(FFT peak strength, NOT identity probability)*
  - `measurements`: `mean_intensity: 0.2409`, `intensity_std: 0.2332`, `dark_fraction: 0.5458`, `orientation_valid_fraction: 0.7584`

---

## 2. MegaDescriptor-L-384 v1 Recognition & Human Verification

Pinned model: `BVRA/MegaDescriptor-L-384@33b3c6f4ee0c386a4126cc3dcd23843920613fa1` (CPU-only, SHA-256 verified, cached gallery via `CpuGalleryIndex`).

### Endpoints
| Method | Path | Status | Description |
| --- | --- | --- | --- |
| `GET` | `/api/v1/identifications/capabilities` | `200` | **New:** Check MegaDescriptor CPU availability, checkpoint revision/SHA-256, preprocessing |
| `POST` | `/api/v1/identifications` | `201` | **New:** Run CPU MegaDescriptor candidate retrieval against active gallery |
| `GET` | `/api/v1/identifications` | `200` | List identification runs (paged, filterable by `status`, `query_image_id`) |
| `GET` | `/api/v1/identifications/{run_id}` | `200` | Get run + ranked `candidates` |
| `GET` | `/api/v1/identifications/{run_id}/candidates` | `200` | Ranked candidates only |
| `GET` | `/api/v1/identifications/{run_id}/verifications` | `200` | Append-only human review history |
| `POST` | `/api/v1/identifications/{run_id}/verifications` | `201` | Submit human review (`confirmed` \| `rejected` \| `unknown`) |

### `GET /api/v1/identifications/capabilities` — Actual Response
```json
{
  "available": true,
  "model_name": "BVRA/MegaDescriptor-L-384",
  "model_revision": "33b3c6f4ee0c386a4126cc3dcd23843920613fa1",
  "checkpoint_sha256": "ccfe757f50f7984a115ffe00921cd4c09e260e645215463b23814586040227a3",
  "preprocessing": "model_card",
  "device": "cpu",
  "gallery_cache_enabled": true,
  "reason": null
}
```

### `POST /api/v1/identifications` — Request & Sample Real Response (`201 Created`)
Request (`extra="forbid"`):
```json
{
  "query_image_id": "<uuid of stored image with kind='query' or 'crop'>",
  "top_k": 5,
  "requested_by": "researcher-1"
}
```
Sample actual response (`IdentificationRunDetail`):
```json
{
  "id": "<run-uuid>",
  "query_image_id": "<query-image-uuid>",
  "status": "completed",
  "model_name": "BVRA/MegaDescriptor-L-384",
  "model_version": "BVRA/MegaDescriptor-L-384@33b3c6f4ee0c386a4126cc3dcd23843920613fa1:card-384-mean0.5",
  "parameters": {"top_k": 5, "preprocessing": "model_card", "device": "cpu"},
  "processing_metadata": {
    "device": "cpu",
    "preprocessing": "model_card",
    "score_type": "cosine similarity, not probability",
    "margin": 0.468987,
    "inference_seconds": 1.4927,
    "model_load_seconds": 0.0,
    "total_seconds": 1.4999,
    "rss_mb": 1481.68,
    "gallery_reference_count": 2,
    "gallery_identity_count": 2,
    "gallery_cache_hits": 2,
    "gallery_cache_misses": 0,
    "gallery_cache_removals": 0
  },
  "predicted_unknown": null,
  "error_code": null,
  "error_message": null,
  "requested_by": "researcher-1",
  "started_at": "2026-11-21T14:46:10Z",
  "completed_at": "2026-11-21T14:46:12Z",
  "created_at": "2026-11-21T14:46:10Z",
  "updated_at": "2026-11-21T14:46:12Z",
  "candidates": [
    {
      "id": "<candidate-uuid>",
      "run_id": "<run-uuid>",
      "rank": 1,
      "zebra_id": "<zebra-uuid>",
      "external_label": null,
      "similarity_score": 0.869484,
      "score_type": "cosine similarity, not probability",
      "matched_reference_image_id": "<ref-image-uuid>",
      "evidence": {
        "method": "megadescriptor_l_384_v1",
        "preprocessing": "model_card",
        "top1_top2_margin": 0.468987
      },
      "created_at": "2026-11-21T14:46:12Z",
      "updated_at": "2026-11-21T14:46:12Z"
    }
  ]
}
```

### Frontend Integration Requirements for Agent 2
1. **`frontend/src/services/identification.js`:**
   - Check `GET /api/v1/identifications/capabilities` (in addition to or instead of `/openapi.json`) to distinguish `available: false` (checkpoint unconfigured -> `503 recognition_unavailable`) from `available: true`.
   - Implement `runInference(queryImage, { topK = 5, requestedBy })` calling `POST /api/v1/identifications` with `{ query_image_id: queryImage.id, top_k: topK, requested_by: requestedBy }` and timeout `>= 120000` ms (cold model load + uncached gallery encode can take 10–45s on CPU; warm cached queries take ~1.5–2.5s).
   - Handle `422 domain_rule_violation` when no active gallery reference images exist yet, and `503 recognition_unavailable` when checkpoint is missing.
   - Display `similarity_score` strictly as **cosine similarity (not probability)**, never claim accuracy, and require explicit human action (`POST /api/v1/identifications/{run_id}/verifications`).
2. **`frontend/src/services/stripeAnalysis.js`:**
   - Optional combined submission helper: `POST /api/v1/analyses/combined` with `{ image_id, roi, morphology_config, frequency_options }` -> returns `{ stripe_morphology, spatial_frequency, roi_semantics_note }`.
   - Poll both returned job IDs via existing `waitForAnalysis(id)` and display `roi_semantics_note` whenever Member 1 and Member 2 results are shown side by side.
3. **Sightings (`POST /api/v1/sightings`):**
   - Uses `observed_at` (ISO-8601 timestamp), optional `zebra_id`, `image_asset_id`, `identification_run_id`, `latitude`/`longitude` (must be paired), `location_name`, `observer`, `notes`, `metadata`.
