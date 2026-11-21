"""harden integrity and revoke public api grants

Phase 2.5 hardening. Additive/tightening only; no data is dropped.

- identification_candidates: similarity_score must be finite (was: only not-NaN).
- verifications: confirmed zebra_id must equal the candidate's zebra_id
  (composite FK to identification_candidates(id, zebra_id)).
- image_assets: content_type required and limited to JPEG/PNG/WebP;
  storage_path may not contain '..' segments, backslashes or control chars.
- Revoke Supabase default table grants from anon/authenticated. Access is
  backend-only; RLS (no policies) already hides rows, but RLS does not cover
  TRUNCATE or REFERENCES, so the grants are removed as defense in depth.
  service_role and the owner (postgres) keep access.

Revision ID: 4fa9f00adf31
Revises: 7f6be5c92a8f
Create Date: 2026-11-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "4fa9f00adf31"
down_revision: Union[str, None] = "7f6be5c92a8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "zebras",
    "image_assets",
    "gallery_entries",
    "identification_runs",
    "identification_candidates",
    "sightings",
    "verifications",
    "alembic_version",
)
_API_ROLES = ("anon", "authenticated")
_ALLOWED_MIME = "content_type IN ('image/jpeg', 'image/png', 'image/webp')"
_PATH_SAFE = r"storage_path !~ '(^|/)\.\.(/|$)' AND storage_path !~ '[\\[:cntrl:]]'"
_SCORE_FINITE = "similarity_score > '-Infinity'::float8 AND similarity_score < 'Infinity'::float8"


def _roles_present(conn) -> list[str]:
    if context.is_offline_mode():
        return list(_API_ROLES)
    rows = conn.execute(sa.text("select rolname from pg_roles where rolname = any(:r)"), {"r": list(_API_ROLES)})
    return [r[0] for r in rows]


def upgrade() -> None:
    conn = op.get_bind()

    # Fail with a clear message instead of a constraint error if legacy rows would violate new rules.
    bad = 0 if context.is_offline_mode() else conn.execute(
        sa.text(f"select count(*) from image_assets where content_type is null or not ({_ALLOWED_MIME}) or not ({_PATH_SAFE})")
    ).scalar_one()
    if bad:
        raise RuntimeError(f"{bad} image_assets rows violate new content_type/path rules; fix data first")

    op.drop_constraint(op.f("ck_identification_candidates_score_not_nan"), "identification_candidates", type_="check")
    op.create_check_constraint(op.f("ck_identification_candidates_score_finite"), "identification_candidates", _SCORE_FINITE)

    op.create_unique_constraint(op.f("uq_identification_candidates_id_zebra"), "identification_candidates", ["id", "zebra_id"])
    op.create_foreign_key(
        op.f("fk_verifications_candidate_zebra"),
        "verifications",
        "identification_candidates",
        ["candidate_id", "zebra_id"],
        ["id", "zebra_id"],
        ondelete="RESTRICT",
    )

    op.alter_column("image_assets", "content_type", existing_type=sa.VARCHAR(length=100), nullable=False)
    op.create_check_constraint(op.f("ck_image_assets_content_type_allowed"), "image_assets", _ALLOWED_MIME)
    op.create_check_constraint(op.f("ck_image_assets_path_safe"), "image_assets", _PATH_SAFE)

    roles = _roles_present(conn)  # roles only exist on Supabase
    if roles:
        for table in _TABLES:
            op.execute(f'REVOKE ALL ON TABLE public."{table}" FROM {", ".join(roles)}')


def downgrade() -> None:
    conn = op.get_bind()
    roles = _roles_present(conn)
    if roles:
        for table in _TABLES:
            op.execute(f'GRANT ALL ON TABLE public."{table}" TO {", ".join(roles)}')

    op.drop_constraint(op.f("ck_image_assets_path_safe"), "image_assets", type_="check")
    op.drop_constraint(op.f("ck_image_assets_content_type_allowed"), "image_assets", type_="check")
    op.alter_column("image_assets", "content_type", existing_type=sa.VARCHAR(length=100), nullable=True)

    op.drop_constraint(op.f("fk_verifications_candidate_zebra"), "verifications", type_="foreignkey")
    op.drop_constraint(op.f("uq_identification_candidates_id_zebra"), "identification_candidates", type_="unique")

    op.drop_constraint(op.f("ck_identification_candidates_score_finite"), "identification_candidates", type_="check")
    op.create_check_constraint(
        op.f("ck_identification_candidates_score_not_nan"), "identification_candidates", "similarity_score = similarity_score"
    )
