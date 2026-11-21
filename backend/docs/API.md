# ZebraID API v1 (Phase 3.2)

Base path: `/api/v1`. Interactive docs with full request/response schemas: `GET /docs`.
Through the Vite dev proxy the browser uses the same paths (`/api/v1/...`).

No authentication exists yet: every endpoint is open to anyone who can reach the server.
`uploaded_by`, `registered_by`, `verified_by` and `observer` are client-supplied text, not verified identities.

## Conventions

**Lists** return one envelope, newest/ordered as noted per endpoint:

```json
{"items": [...], "total": 42, "limit": 20, "offset": 0}
```

`limit` 1-100 (default 20), `offset` >= 0. `total` counts every match across all pages.

**Errors** use the envelope from Phase 3.1:

```json
{"error": {"code": "zebra_code_exists", "message": "zebra code 'ZB-0001' already exists",
           "details": {"zebra_id": "…"}, "request_id": "…"}}
```

| Status | `code` values |
|---|---|
| 404 | `not_found`, `storage_object_not_found` |
| 409 | `zebra_code_exists`, `zebra_in_use`, `duplicate_image`, `image_in_use`, `image_already_in_gallery`, `integrity_conflict`, `storage_bucket_mismatch` |
| 413 | `image_too_large` |
| 415 | `unsupported_image_type` |
| 422 | `validation_error`, `invalid_reference` (a body id points at nothing), `inconsistent_reference`, `domain_rule_violation`, `invalid_image` |
| 502 | `storage_error` |
| 503 | `database_unavailable`, `storage_not_configured` |
| 500 | `internal_error` |

**PATCH** changes only the fields sent. Required columns (`status`, `attributes`, `observed_at`, `metadata`, …) cannot be sent as `null`.

**Transactions**: each write endpoint is one database transaction. A failure rolls everything back.

## Zebras

| Method | Path | Notes |
|---|---|---|
| POST | `/zebras` | `code` unique (`^[A-Za-z0-9_.-]+$`, max 40). 409 `zebra_code_exists` |
| GET | `/zebras` | filters: `status`, `search` (code/name substring), `species`, `sex` (exact, case-insensitive). `sort`: `code` (default) or `-created_at` (newest first) |
| GET | `/zebras/{id}` | |
| PATCH | `/zebras/{id}` | `code` is immutable (ignored) |
| DELETE | `/zebras/{id}` | 204. 409 `zebra_in_use` if sightings, candidates or verifications reference it; retire with `status: inactive/deceased`. Gallery links are removed, images kept |

```bash
curl -X POST localhost:8000/api/v1/zebras -H 'Content-Type: application/json' \
  -d '{"code": "ZB-0001", "name": "Kito", "species": "Equus quagga"}'
curl 'localhost:8000/api/v1/zebras?search=ZB-&status=active&limit=10'
curl -X PATCH localhost:8000/api/v1/zebras/<id> -H 'Content-Type: application/json' -d '{"status": "inactive"}'
```

## Images

| Method | Path | Notes |
|---|---|---|
| POST | `/images` | `multipart/form-data`, see below. 201 |
| GET | `/images` | filters: `kind`, `sha256`. Newest first |
| GET | `/images/{id}` | metadata only |
| GET | `/images/{id}/url` | `expires_in` 1-3600 s (default 60). Returns `{url, expires_in, expires_at}` |
| DELETE | `/images/{id}` | 204. 409 `image_in_use` while crops, gallery entries, runs, candidates or sightings use it |

Upload form fields:

| Field | Required | Notes |
|---|---|---|
| `file` | yes | JPEG, PNG or WebP; at most `STORAGE_MAX_UPLOAD_BYTES` (10 MB). Type is detected from content and must match the part's Content-Type |
| `kind` | yes | `query` (to identify), `reference` (known zebra), `crop` (region of another image) |
| `source_image_id`, `crop_bbox` | crop only | `crop_bbox` JSON `{"x":0,"y":0,"width":256,"height":256}` in source pixels; must lie inside the source |
| `captured_at` | no | ISO 8601 |
| `uploaded_by` | no | max 120 chars |
| `metadata` | no | JSON object |

Width and height are read from the image (not trusted from the client). The SHA-256 of the bytes is stored;
uploading identical bytes with the same `kind` again returns 409 `duplicate_image` with `existing_image_id`.

```bash
curl -X POST localhost:8000/api/v1/images -F kind=reference -F file=@zebra.jpg;type=image/jpeg
curl -X POST localhost:8000/api/v1/images -F kind=crop -F source_image_id=<id> \
  -F 'crop_bbox={"x":120,"y":80,"width":400,"height":300}' -F file=@crop.png;type=image/png
curl 'localhost:8000/api/v1/images/<id>/url?expires_in=300'
```

Responses never include the bucket, object path, service key or a permanent URL. Signed URLs expire; do not store them.

## Gallery (application records only)

| Method | Path | Notes |
|---|---|---|
| POST | `/zebras/{zebra_id}/gallery` | body `{image_asset_id, side?, quality_notes?, registered_by?, metadata?}`. Image must be `reference` or `crop` (422) and in no gallery yet (409 `image_already_in_gallery`) |
| GET | `/zebras/{zebra_id}/gallery` | `include_inactive` (default false), `include_urls` (default false; one batched signing call), `expires_in`. Each item embeds `image` metadata and `image_url` |
| DELETE | `/gallery/{entry_id}` | 204. Unlinks only; image and stored file stay |

No embeddings, ML reference registration or model-gallery sync happen here.

## Sightings

| Method | Path | Notes |
|---|---|---|
| POST | `/sightings` | `observed_at` required. `zebra_id` optional (omit = unidentified; no zebra is created). `latitude`/`longitude` together. Referenced ids must exist (422 `invalid_reference`); a linked run must have been run on the linked image or a crop of it |
| GET | `/sightings` | filters: `zebra_id`, `unidentified_only`, `since` (>=), `until` (<), `location_name` (substring), `min_lat`/`max_lat`/`min_lon`/`max_lon`. Newest observation first |
| GET | `/sightings/{id}` | |
| PATCH | `/sightings/{id}` | `zebra_id: null` un-assigns; `latitude`+`longitude` together (both null clears) |
| DELETE | `/sightings/{id}` | 204. Linked image/run kept |

```bash
curl -X POST localhost:8000/api/v1/sightings -H 'Content-Type: application/json' \
  -d '{"observed_at": "2026-11-20T06:30:00Z", "latitude": -1.52, "longitude": 35.14, "location_name": "Waterhole A"}'
curl 'localhost:8000/api/v1/sightings?unidentified_only=true&since=2026-11-01T00:00:00Z'
```

## Identifications (read + human review)

No endpoint creates runs or candidates; they will come from the ML integration. `similarity_score` is a model
similarity (see `score_type`), not a probability or confidence percentage.

| Method | Path | Notes |
|---|---|---|
| GET | `/identifications` | filters: `status`, `query_image_id`. Newest first |
| GET | `/identifications/{run_id}` | run + candidates ordered by rank |
| GET | `/identifications/{run_id}/candidates` | |
| GET | `/identifications/{run_id}/verifications` | oldest first; the last row is the current decision |
| POST | `/identifications/{run_id}/verifications` | body `{decision, candidate_id?, verified_by, notes?}` |

Review rules: only `completed` runs; `confirmed`/`rejected` need a `candidate_id` of this run; `unknown` must not
have one; only candidates linked to a registered zebra can be confirmed (the zebra is taken from the candidate).
Decisions are append-only. Confirming does not change any sighting; update the sighting explicitly.

```bash
curl -X POST localhost:8000/api/v1/identifications/<run_id>/verifications -H 'Content-Type: application/json' \
  -d '{"decision": "confirmed", "candidate_id": "<candidate_id>", "verified_by": "reviewer@field"}'
```

## Scientific Stripe Analyses (Member 1 + Member 2)

Durable job queue backed by `stripe_analyses` (one isolated `spawn` worker process at a time; private PNG artifacts stored in `zebra_images` under `analysis/YYYY/MM/<job_id>/<name>.png`).

| Method | Path | Notes |
|---|---|---|
| GET | `/analyses/capabilities` | Availability, pinned research commits (`127b563`, `96a69a4`), and configured pixel/queue/timeout limits |
| POST | `/analyses/stripe-morphology` | 202. Member 1 (`analyze_stripes`). Accepts `{image_id, roi?, config?}`. `roi=null` uses `roi_mode=auto`; explicit ROI uses `roi_mode=mask` |
| POST | `/analyses/spatial-frequency` | 202. Member 2 (`safe_analyze`). Accepts `{image_id, roi?, options?}`. `roi_mode=box` (`[x,y,width,height]`, min 16×16) |
| GET | `/analyses` | Filters: `image_id`, `kind`, `status`, pagination (`Page`) |
| GET | `/analyses/{analysis_id}` | Job object with verbatim sanitized `result` and `artifacts` name list (never filesystem or bucket paths) |
| GET | `/analyses/{analysis_id}/artifacts/{artifact_name}/url` | `expires_in` 1–3600 s (default 60). Returns `{url, expires_in, expires_at}` |
| DELETE | `/analyses/{analysis_id}` | 204. Refused with 409 while `running`; deletes row then private artifact objects |

## Grounded Gemini Assistant

| Method | Path | Notes |
|---|---|---|
| GET | `/assistant/status` | `{available, model, reason}`. Explicitly reports unavailable when `GEMINI_API_KEY` is empty |
| POST | `/assistant/ask` | `{question, image_id?, analysis_ids?, zebra_id?, run_id?}`. Grounds Gemini strictly in persisted database records; 503 `assistant_unavailable` when unconfigured |
