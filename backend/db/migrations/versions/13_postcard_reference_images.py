"""add postcards.reference_images JSON column for multi-reference support"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "13_postcard_reference_images"
down_revision: Union[str, Sequence[str], None] = "12_image_styles_zh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "postcards",
        sa.Column("reference_images", sa.JSON, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("postcards", "reference_images")
