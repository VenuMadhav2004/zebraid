# Database audit (Phase 2.5)

Date: 2026-11-21. Target: Supabase PostgreSQL 17.12 (session pooler), database `postgres`, schema `public`.
Credentials are not reproduced here.

## Migration status

| Check | Result |
|---|---|
| `alembic history` | `<base> -> 7f6be5c92a8f` (initial domain schema) `-> 4fa9f00adf31` (hardening) |
| `alembic heads` | single head `4fa9f00adf31` (no branches, no duplicate revisions) |
| `alembic current` | `4fa9f00adf31 (head)` |
| `alembic check` | `No new upgrade operations detected.` (ORM metadata == database) |
| Reproducibility | `alembic upgrade 7f6be5c92a8f:head --sql` and `downgrade 4fa9f00adf31:7f6be5c92a8f --sql` render cleanly; `upgrade head` → `downgrade -1` → `upgrade head` round-trip executed on the live DB with 0 rows present |
| Data | All domain tables had 0 rows before and after; no data was dropped or rewritten |

Never run `alembic downgrade base` or reset commands against this project. Only one-step rollback of `4fa9f00adf31` was exercised.

## Schema

There are 7 domain tables plus `alembic_version`. UUID primary keys, `timestamptz created_at/updated_at` (default `clock_timestamp()`). Enums are stored as `VARCHAR + CHECK`. No `bytea`, array or vector columns exist; a test asserts this.

| Entity | Identity / uniqueness | Required | Optional | Deletion |
|---|---|---|---|---|
| `zebras` | PK `id`; unique `code` | `code`, `status`, `attributes` | `name`, `species`, `sex`, `notes` | cascades its gallery entries; RESTRICT while sightings, candidates or verifications reference it (retire it with `status`) |
| `image_assets` | PK `id`; unique (`storage_bucket`, `storage_path`) | `kind`, bucket, path, **`content_type`** (JPEG/PNG/WebP) | size, w/h, `sha256` (hex, indexed), `captured_at`, `uploaded_by`, crop lineage | RESTRICT while crops, gallery entries or runs reference it; SET NULL from sightings and matched references |
| `gallery_entries` | PK; unique `image_asset_id` (an image belongs to one zebra) | `zebra_id`, `image_asset_id`, `side`, `is_active` | notes, `registered_by` | CASCADE from zebra; deactivate with `is_active=false` |
| `identification_runs` | PK | `query_image_id`, `status`, `model_name` | `model_version`, params/metadata JSONB, `predicted_unknown`, error fields, `requested_by`, start/end | CASCADE to candidates; RESTRICT once verified |
| `identification_candidates` | PK; unique (`run_id`,`rank`); unique (`id`,`run_id`) and (`id`,`zebra_id`) as composite-FK targets | `run_id`, `rank >= 1`, `similarity_score` (**finite**, no range) | `zebra_id` **or** `external_label` (CHECK), `score_type`, `matched_reference_image_id`, `evidence` | CASCADE from run |
| `verifications` | PK; append-only | `run_id`, `decision`, `verified_by` | `candidate_id`, `zebra_id`, `notes` | RESTRICT on every parent |
| `sightings` | PK | `observed_at` | `zebra_id` (unknown individual allowed), lat/lon (paired, ranged), `location_name`, `observer`, image, run | SET NULL from image/run; RESTRICT from zebra |

Indexes: every FK column used for lookups, plus `(kind, created_at)`, `(status, created_at)`, `(zebra_id, is_active)`, `(zebra_id, observed_at)`, `(run_id, created_at)`, `sha256` and `observed_at`.

### Design rules verified

- **Similarity is not probability.** The only constraint is finiteness; negative values and values above 1 are accepted, and tests cover both. `score_type` records the engine's description.
- **Unknown identities** need no fake zebra: use `external_label` for an unmapped ML label, or `Verification(decision='unknown')` with neither candidate nor zebra. A candidate without a registered zebra cannot be confirmed.
- **No checkpoints or embeddings** are stored relationally. Embeddings stay in the recognition engine's cache.
- **Verification ↔ candidate ↔ run.** A composite FK (`candidate_id`,`run_id`) means a candidate must belong to the run. A new composite FK (`candidate_id`,`zebra_id`) means a confirmed zebra must be the candidate's zebra.

## Findings and fixes

| # | Finding | Severity | Fix |
|---|---|---|---|
| D1 | Score CHECK only blocked NaN; `±Infinity` was accepted | medium | `ck_identification_candidates_score_finite` replaces `score_not_nan`; Pydantic also rejects inf |
| D2 | "Confirmed zebra = candidate zebra" was enforced only in Python | medium | `uq_identification_candidates_id_zebra` + `fk_verifications_candidate_zebra` (MATCH SIMPLE, so it applies only when `zebra_id` is set) |
| D3 | `image_assets.content_type` was free text and nullable | medium | `NOT NULL` + `ck_image_assets_content_type_allowed` |
| D4 | `storage_path` allowed `..` segments, backslashes and control characters | medium | `ck_image_assets_path_safe` + Pydantic validator |
| D5 | Zebra search passed `%`/`_` straight into `ILIKE` (not injection, but wildcard abuse) | low | escaped with `ESCAPE '\'` |
| D6 | (Phase 2, retained) ORM nulled children before parent delete, bypassing RESTRICT | fixed earlier | `passive_deletes="all"` on RESTRICT relationships |

## Known limitations (not changed, documented)

- Rules enforced only in the repository layer: gallery images must be `reference`/`crop`; runs only on `query`/`crop`; `matched_reference_image_id` must be a gallery image of the candidate zebra; run state transitions. Raw SQL can bypass them. Triggers can be added if direct SQL writers appear.
- `updated_at` is bumped by the ORM (`onupdate`), not by a DB trigger.
- `zebras.code` uniqueness is case-sensitive (`ZB-1` ≠ `zb-1`).
- There is no dedicated external research ID column (e.g. a GZCD identity); use `attributes` JSONB until a real requirement defines it.
- Who-did-what fields (`uploaded_by`, `verified_by`, …) are free text until auth exists.
