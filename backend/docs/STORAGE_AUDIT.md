# Storage audit (Phase 2.5)

Bucket: `zebra_images` (name unchanged). Validated 2026-11-21 against the live Supabase project.

## Configuration

| Setting | Before | After |
|---|---|---|
| `public` | `false` | `false` |
| `file_size_limit` | none | `10485760` (10 MiB, equal to `STORAGE_MAX_UPLOAD_BYTES`) |
| `allowed_mime_types` | none | `image/jpeg`, `image/png`, `image/webp` |
| `storage.objects` / `storage.buckets` RLS | enabled | enabled (unchanged) |
| Storage policies | none | none (unchanged): only `service_role` can read/write |

The limits were applied with the Storage API `PUT /bucket/zebra_images` using the backend service-role key.

## Code

`app/integrations/supabase_storage.py` (new), backend only:
- `validate_image()`: non-empty, `<= max_bytes`, declared type in the allowlist, **magic bytes must match the declared type** (rejects renamed or spoofed files).
- `generate_storage_path()`: `{prefix/}{kind}/{YYYY}/{MM}/{uuid4hex}.{ext}`. No user input reaches the key; the prefix is checked against `^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$`.
- `SupabaseStorage.upload()`: validates, then uploads with `x-upsert: false`, so it never overwrites.
- `download()` uses authenticated GET. `delete()`, `list()`, `get_bucket()`.
- `signed_url(path, expires_in)`: TTL is bounded to `1..STORAGE_SIGNED_URL_MAX_TTL` (default 60 s, max 3600 s). Returns `expires_at`, and signed URLs must never be persisted. The DB stores only bucket + path.
- Errors map to `StorageConflictError`, `StorageNotFoundError` and `StorageError`; messages never contain the key.

`app/services/image_storage.py` (new) keeps the DB and Storage consistent:
- `store_image()`: validate → build the row schema → upload → insert row in a savepoint. If the upload fails, no row is written. If the insert fails, the uploaded object is deleted.
- `remove_image()` deletes the row (flush); the caller commits and then calls `discard_objects()`.

## Live validation results (`tests/integration/test_storage_integration.py`, prefix `_healthcheck/phase25/`)

| Check | Result |
|---|---|
| Bucket exists, private, limits as above | pass |
| Backend service-role authenticates | pass |
| JPEG, PNG, WebP upload → authenticated download (byte-exact) → delete → 404 | pass (3 formats) |
| Same path uploaded twice | second upload refused (`StorageConflictError`); original bytes intact |
| `text/plain` sent directly to the API (client checks bypassed) | refused by the bucket |
| 10 MiB + 4 B upload | refused by the client, and by the bucket when sent directly |
| Anonymous GET via `/object/public/…`, `/object/…`, `/object/authenticated/…` | all refused |
| Signed URL (TTL 2 s) | downloads before expiry; refused after 4 s |
| Signed URL TTL > max | `ValueError` |
| Signed URL for a missing object | `StorageNotFoundError` |
| `store_image()` happy path | row has path, size, sha256 and MIME; object downloadable |
| DB write fails after upload | object removed, no row |
| Upload fails (nonexistent bucket) | no row written |
| Cleanup | after the full run: 0 objects in the bucket, 0 under `_healthcheck/` |

Test payloads are synthetic: valid magic bytes plus padding. Supabase Storage does not decode images.

## Limitations

- **Commit window.** If the caller's final `COMMIT` fails after `store_image()` returns, the object exists without a row. The caller must call `discard_objects()`; a periodic orphan sweep (objects without a matching `image_assets` row) is recommended before production.
- **Images are not decoded.** Magic bytes are checked, but the image is not parsed or re-encoded, so EXIF/GPS metadata is kept. Decide whether to strip EXIF; GPS may be research-relevant but sensitive.
- **The bucket limit must match the setting.** `STORAGE_MAX_UPLOAD_BYTES` and the bucket `file_size_limit` are two settings that must stay equal.
- **Width/height** are supplied by the caller and not measured.
