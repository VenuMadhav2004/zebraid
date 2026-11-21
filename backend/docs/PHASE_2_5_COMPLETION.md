# Phase 2.5 completion report: database and storage hardening

Date: 2026-11-21. Scope: audit, validation and verified fixes only. No new API endpoints, no frontend changes, no ML integration.

## Changes

### Database (migration `4fa9f00adf31`, revises `7f6be5c92a8f`)
- `ck_identification_candidates_score_finite` replaces `ck_identification_candidates_score_not_nan`.
- `uq_identification_candidates_id_zebra` + `fk_verifications_candidate_zebra`.
- `image_assets.content_type` set `NOT NULL`; added `ck_image_assets_content_type_allowed` and `ck_image_assets_path_safe`.
- `REVOKE ALL` from `anon` and `authenticated` on all 8 public tables.
- Pre-check aborts if existing rows would violate the new rules. Applied with 0 rows; downgrade/upgrade round-trip tested.

### Storage (bucket config only; name and privacy unchanged)
- `file_size_limit = 10485760`; `allowed_mime_types = [image/jpeg, image/png, image/webp]`.

### Code
| File | Change |
|---|---|
| `app/models/identification.py` | finite score CHECK, `(id, zebra_id)` unique |
| `app/models/verification.py` | composite FK `(candidate_id, zebra_id)` |
| `app/models/image_asset.py` | `content_type` required + allowlist CHECK, path-safety CHECK |
| `app/schemas/image_asset.py` | `content_type` Literal allowlist (required); rejects `..`, `\` and control characters in paths |
| `app/repositories/zebras.py` | `ILIKE` wildcard escaping |
| `app/api/health.py` | `/health/db` no longer returns raw driver errors |
| `app/config.py` | `STORAGE_MAX_UPLOAD_BYTES`, `STORAGE_SIGNED_URL_DEFAULT_TTL`, `STORAGE_SIGNED_URL_MAX_TTL` |
| `app/integrations/supabase_storage.py` | **new**: validated, non-overwriting Storage client with signed URLs |
| `app/services/image_storage.py` | **new**: orphan-safe `store_image` / `remove_image` / `discard_objects` |
| `alembic/versions/4fa9f00adf31_harden_integrity_and_revoke_public_api_.py` | **new** migration |
| `requirements.txt` | `httpx==0.28.1` |
| `pytest.ini` | test paths and markers (`unit`, `integration`, `storage`) |
| `tests/` | split into `unit/` and `integration/`; new `unit/test_storage_unit.py`, `unit/test_health_unit.py`, `integration/test_integrity_flow.py`, `integration/test_security_db.py`, `integration/test_storage_integration.py`; existing tests updated for required `content_type` |
| `docs/DATABASE_AUDIT.md`, `docs/STORAGE_AUDIT.md`, `docs/SECURITY_AUDIT.md`, this file | **new** |

## Tests (executed 2026-11-21, `.venv/bin/pytest -q`)

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| unit (`-m unit`, no network; HTTP and DB mocked) | 52 | 0 | 0 |
| integration (`-m integration`, live Supabase DB + Storage) | 101 | 0 | 0 |
| **full run** | **153** | **0** | **0** |

Post-run state: 0 rows in all 7 domain tables; 0 objects in `zebra_images`; 0 under `_healthcheck/`. `alembic current` = `4fa9f00adf31 (head)`; `alembic check` reports no drift. `/health` and `/health/db` return 200.

Integration tests run inside rolled-back transactions. Storage tests track every path they write and delete it in teardown; the teardown asserts that nothing is left.

## Definition of done

- [x] Existing database schema audited (`DATABASE_AUDIT.md`)
- [x] ORM relationships validated (full-flow test)
- [x] Foreign keys and constraints verified (named-constraint assertions)
- [x] Alembic state consistent (single head, current = head, no drift, round-trip)
- [x] Database integrity tests pass
- [x] Supabase Storage validated
- [x] Private storage access verified (anonymous reads refused)
- [x] Signed URL generation and expiry tested
- [x] Security review documented (`SECURITY_AUDIT.md`)
- [x] No real credentials exposed in code or docs
- [x] Existing tests still pass
- [x] Temporary records and objects cleaned up
- [x] Completion report generated

## Remaining risks

1. Rotate the database password: it was exposed in chat earlier.
2. Commit-after-upload window can orphan an object; add an orphan sweep before production.
3. Some business rules exist only in repositories (gallery image kind, run image kind, matched reference ownership, run state machine).
4. No auth or ownership model yet. RLS posture must be revisited when auth lands (see `SECURITY_AUDIT.md`).
5. EXIF/GPS metadata is not stripped from uploads.
6. Schema conflict risk with Nisan's `member3_venu` schema on `stripecode-ai/main`: do not migrate both into one database.
7. `ZebraID/` is not under version control; the team repo branch has the Phase 1 copy only.

Phase 2.5 is complete. Phase 3 has not been started.
