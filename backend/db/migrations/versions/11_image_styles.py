"""create image_styles table and seed built-in styles"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "11_image_styles"
down_revision: Union[str, Sequence[str], None] = "10_prompt_overrides"
branch_labels = None
depends_on = None


# 内置风格种子数据。必须与 style_service.STYLES 保持一致，
# 保证已设置风格的老用户在迁移后仍能找到对应风格。
_SEED_STYLES = [
    {
        "style_id": "pixel_16bit",
        "label": "16位像素风",
        "style_prompt": (
            "复古16位像素风，怀旧游戏截图质感，暖色怀旧调色板，"
            "可见像素网格与锐利方块边缘，平涂2D着色低色彩数，"
            "SNES/GBA时代精灵画质量，无平滑渐变、无写实细节、无3D渲染"
        ),
        "analysis_hint": "复古16位像素风",
        "sort_order": 0,
    },
    {
        "style_id": "watercolor",
        "label": "水彩风",
        "style_prompt": (
            "柔和水彩画，细腻晕染与洇边，暖色怀旧调色板，"
            "可见纸张纹理，柔和渐变，手绘插画风，"
            "无锐利像素边缘、无3D渲染"
        ),
        "analysis_hint": "柔和水彩画",
        "sort_order": 1,
    },
    {
        "style_id": "ghibli",
        "label": "吉卜力风",
        "style_prompt": (
            "吉卜力风格动漫插画，温暖手绘背景，柔和自然光，"
            "繁茂细致景色，怀旧温柔氛围，赛璐璐角色，绘画质感，"
            "无写实、无3D渲染"
        ),
        "analysis_hint": "吉卜力风格动漫插画",
        "sort_order": 2,
    },
    {
        "style_id": "ink_wash",
        "label": "水墨风",
        "style_prompt": (
            "传统中国水墨画，写意水墨风，单色墨韵渐变带细微暖色点缀，"
            "写意笔触，宣纸纹理，大量留白，无写实、无3D渲染"
        ),
        "analysis_hint": "传统中国水墨画",
        "sort_order": 3,
    },
    {
        "style_id": "retro_photo",
        "label": "复古胶片",
        "style_prompt": (
            "复古胶片照片，暖色褪色，细微颗粒与漏光，柔焦，"
            "怀旧90年代快照质感，自然光，无像素画、无插画、无3D渲染"
        ),
        "analysis_hint": "复古胶片照片",
        "sort_order": 4,
    },
]


def upgrade() -> None:
    op.create_table(
        "image_styles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("style_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("style_prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("analysis_hint", sa.Text, nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.UniqueConstraint("style_id", name="uq_image_styles_style_id"),
    )
    op.create_index("ix_image_styles_active_sort", "image_styles", ["is_active", "sort_order"])

    image_styles_table = sa.table(
        "image_styles",
        sa.Column("style_id", sa.String),
        sa.Column("label", sa.String),
        sa.Column("style_prompt", sa.Text),
        sa.Column("analysis_hint", sa.Text),
        sa.Column("sort_order", sa.Integer),
        sa.Column("is_active", sa.Boolean),
        sa.Column("is_system", sa.Boolean),
    )
    op.bulk_insert(
        image_styles_table,
        [{**style, "is_active": True, "is_system": True} for style in _SEED_STYLES],
    )


def downgrade() -> None:
    op.drop_index("ix_image_styles_active_sort", table_name="image_styles")
    op.drop_table("image_styles")
