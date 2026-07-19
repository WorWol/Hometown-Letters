"""add community letter likes"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5_add_letter_likes"
down_revision: Union[str, Sequence[str], None] = "4_storage_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "letter_likes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("letter_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["letter_id"], ["letters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "letter_id"),
    )
    op.create_index("ix_letter_likes_user", "letter_likes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_letter_likes_user", table_name="letter_likes")
    op.drop_table("letter_likes")
