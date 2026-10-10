"""create uploaded_files and features

Revision ID: 97b9fb4e0e44
Revises:
Create Date: 2026-10-10 17:34:11.742327

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "97b9fb4e0e44"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("crs", sa.String(), nullable=True),
        sa.Column("feature_count", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("feature_index", sa.Integer(), nullable=False),
        sa.Column("geometry_type", sa.String(), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("measurement_crs", sa.String(), nullable=True),
        sa.Column("area_m2", sa.Double(), nullable=True),
        sa.Column("length_m", sa.Double(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["uploaded_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_features_file_id", "features", ["file_id"])


def downgrade() -> None:
    op.drop_table("features")
    op.drop_table("uploaded_files")
