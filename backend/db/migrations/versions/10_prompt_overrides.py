"""create prompt_overrides table for editable LLM prompts"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "10_prompt_overrides"
down_revision: Union[str, Sequence[str], None] = "9_reference_image"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_overrides",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(length=64), server_default=""),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.UniqueConstraint("key", name="uq_prompt_overrides_key"),
    )
    op.create_index("ix_prompt_overrides_key", "prompt_overrides", ["key"])


def downgrade() -> None:
    op.drop_index("ix_prompt_overrides_key", table_name="prompt_overrides")
    op.drop_table("prompt_overrides")
