"""add stripe_analyses table

Prepares durable job queue, provenance and artifact storage metadata for Member 1
(stripe_morphology) and Member 2 (spatial_frequency) scientific analyses.

Security posture mirrors 4fa9f00adf31: RLS enabled (no public policies) and table
grants revoked from Supabase anon/authenticated roles.

IMPORTANT: Do not run `alembic upgrade head` against live Supabase until approved.

Revision ID: a8d3f2c91b40
Revises: 4fa9f00adf31
Create Date: 2026-11-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "a8d3f2c91b40"
down_revision: Union[str, None] = "4fa9f00adf31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_API_ROLES = ("anon", "authenticated")


def _roles_present(conn) -> list[str]:
    if context.is_offline_mode():
        return list(_API_ROLES)
    rows = conn.execute(sa.text("select rolname from pg_roles where rolname = any(:r)"), {"r": list(_API_ROLES)})
    return [r[0] for r in rows]


def upgrade() -> None:
    op.create_table(
        "stripe_analyses",
        sa.Column("image_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("roi", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("roi_mode", sa.String(length=20), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("provider", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifacts", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # Defaults match UUIDPrimaryKeyMixin / TimestampMixin and the earlier tables.
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('stripe_morphology', 'spatial_frequency')",
            name=op.f("ck_stripe_analyses_analysis_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name=op.f("ck_stripe_analyses_analysis_status"),
        ),
        sa.CheckConstraint(
            "roi_mode IN ('mask', 'auto', 'box')",
            name=op.f("ck_stripe_analyses_roi_mode"),
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR error_message IS NOT NULL",
            name=op.f("ck_stripe_analyses_failed_has_error"),
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL",
            name=op.f("ck_stripe_analyses_completed_has_time"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_stripe_analyses_time_order"),
        ),
        sa.ForeignKeyConstraint(
            ["image_asset_id"],
            ["image_assets.id"],
            name=op.f("fk_stripe_analyses_image_asset_id_image_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stripe_analyses")),
    )
    op.create_index("ix_stripe_analyses_image_created", "stripe_analyses", ["image_asset_id", "created_at"], unique=False)
    op.create_index("ix_stripe_analyses_status_created", "stripe_analyses", ["status", "created_at"], unique=False)

    op.execute('ALTER TABLE public."stripe_analyses" ENABLE ROW LEVEL SECURITY')
    conn = op.get_bind()
    roles = _roles_present(conn)
    if roles:
        op.execute(f'REVOKE ALL ON TABLE public."stripe_analyses" FROM {", ".join(roles)}')


def downgrade() -> None:
    op.drop_index("ix_stripe_analyses_status_created", table_name="stripe_analyses")
    op.drop_index("ix_stripe_analyses_image_created", table_name="stripe_analyses")
    op.drop_table("stripe_analyses")
