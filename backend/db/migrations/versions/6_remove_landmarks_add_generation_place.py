"""remove unused landmark system and record postcard generation place"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6_remove_landmarks_add_generation_place"
down_revision: Union[str, Sequence[str], None] = "5_add_letter_likes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    postcard_columns = {column["name"] for column in inspector.get_columns("postcards")}
    with op.batch_alter_table("postcards") as batch:
        if "generation_place" not in postcard_columns:
            batch.add_column(
                sa.Column("generation_place", sa.String(length=128), nullable=False, server_default="")
            )
        if "landmark_id" in postcard_columns:
            batch.drop_column("landmark_id")
        if "landmark_description" in postcard_columns:
            batch.drop_column("landmark_description")

    # 历史数据没有独立的生成地点，先沿用原来的核心地点展示。
    op.execute(
        sa.text(
            "UPDATE postcards SET generation_place = COALESCE(place, '') "
            "WHERE generation_place IS NULL OR generation_place = ''"
        )
    )

    if inspector.has_table("landmarks"):
        op.drop_table("landmarks")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("landmarks"):
        op.create_table(
            "landmarks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("scene_type", sa.String(length=32), nullable=True),
            sa.Column("tier", sa.String(length=8), nullable=True),
            sa.Column("used_count", sa.Integer(), nullable=True),
            sa.Column("last_used_day", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(length=32), nullable=True),
            sa.Column("is_used", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_landmarks_user_name", "landmarks", ["user_id", "name"])
        op.create_index("ix_landmarks_user_tier", "landmarks", ["user_id", "tier"])
        op.create_index("ix_landmarks_user_used", "landmarks", ["user_id", "is_used"])

    postcard_columns = {column["name"] for column in sa.inspect(bind).get_columns("postcards")}
    with op.batch_alter_table("postcards") as batch:
        if "landmark_id" not in postcard_columns:
            batch.add_column(sa.Column("landmark_id", sa.Integer(), nullable=True))
        if "landmark_description" not in postcard_columns:
            batch.add_column(sa.Column("landmark_description", sa.Text(), nullable=True))
        if "generation_place" in postcard_columns:
            batch.drop_column("generation_place")
