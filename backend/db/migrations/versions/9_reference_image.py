"""persist the selected image-search reference used for generation"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9_reference_image"
down_revision: Union[str, Sequence[str], None] = "8_developer_accounts_and_storage_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("postcards") as batch:
        batch.add_column(sa.Column("reference_image_key", sa.String(length=512), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("postcards") as batch:
        batch.drop_column("reference_image_key")
