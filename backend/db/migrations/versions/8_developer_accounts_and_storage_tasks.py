"""add developer roles and storage deletion retry tasks"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8_developer_accounts_and_storage_tasks"
down_revision: Union[str, Sequence[str], None] = "7_persistent_limits_and_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("is_developer", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "storage_deletion_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("object_keys", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_storage_tasks_status_updated", "storage_deletion_tasks", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_storage_tasks_status_updated", table_name="storage_deletion_tasks")
    op.drop_table("storage_deletion_tasks")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_developer")
