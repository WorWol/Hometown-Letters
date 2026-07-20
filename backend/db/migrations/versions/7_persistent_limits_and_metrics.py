"""persist authentication limits and API metrics"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7_persistent_limits_and_metrics"
down_revision: Union[str, Sequence[str], None] = "6_remove_landmarks_add_generation_place"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_limit_events_key_time", "rate_limit_events", ["key", "created_at"])
    op.create_table(
        "api_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("method", sa.String(length=12), nullable=False),
        sa.Column("path", sa.String(length=256), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("success", sa.Integer(), nullable=False),
        sa.Column("client_errors", sa.Integer(), nullable=False),
        sa.Column("server_errors", sa.Integer(), nullable=False),
        sa.Column("total_ms", sa.Integer(), nullable=False),
        sa.Column("max_ms", sa.Integer(), nullable=False),
        sa.Column("last_status", sa.Integer(), nullable=False),
        sa.Column("last_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("method", "path"),
    )


def downgrade() -> None:
    op.drop_table("api_metrics")
    op.drop_index("ix_rate_limit_events_key_time", table_name="rate_limit_events")
    op.drop_table("rate_limit_events")
