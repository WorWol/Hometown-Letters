"""clean image keys, postcard quota, and local monitoring events"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4_storage_monitoring"
down_revision: Union[str, Sequence[str], None] = "3a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("postcard_limit", sa.Integer(), nullable=False, server_default="5"))
        batch.add_column(sa.Column("postcard_count", sa.Integer(), nullable=False, server_default="0"))

    with op.batch_alter_table("postcards") as batch:
        batch.add_column(sa.Column("image_thumb_key", sa.String(length=512), nullable=False, server_default=""))
        batch.add_column(sa.Column("image_card_key", sa.String(length=512), nullable=False, server_default=""))
        batch.add_column(sa.Column("image_original_key", sa.String(length=512), nullable=False, server_default=""))
        batch.drop_column("image_path")
        batch.drop_column("used_fallback")

    op.create_table(
        "system_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_events_created", "system_events", ["created_at"])
    op.create_index("ix_system_events_level_created", "system_events", ["level", "created_at"])
