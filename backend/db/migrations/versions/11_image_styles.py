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
            "retro 16-bit pixel art, nostalgic game screenshot aesthetic, "
            "warm nostalgic color palette, visible pixel grid and crisp blocky edges, "
            "flat 2D shading with limited color count, SNES/GBA-era sprite art quality, "
            "no smooth gradients, no photorealistic detail, no 3D rendering"
        ),
        "analysis_hint": "RETRO 16-BIT PIXEL ART",
        "sort_order": 0,
    },
    {
        "style_id": "watercolor",
        "label": "水彩风",
        "style_prompt": (
            "soft watercolor painting, delicate washes and bleeding edges, "
            "warm nostalgic color palette, visible paper texture, gentle gradients, "
            "hand-painted illustration aesthetic, no sharp pixel edges, no 3D rendering"
        ),
        "analysis_hint": "SOFT WATERCOLOR PAINTING",
        "sort_order": 1,
    },
    {
        "style_id": "ghibli",
        "label": "吉卜力风",
        "style_prompt": (
            "Studio Ghibli style anime illustration, warm hand-painted backgrounds, "
            "soft natural lighting, lush detailed scenery, nostalgic and gentle atmosphere, "
            "cel-shaded characters, painterly texture, no photorealism, no 3D rendering"
        ),
        "analysis_hint": "STUDIO GHIBLI STYLE ANIME ILLUSTRATION",
        "sort_order": 2,
    },
    {
        "style_id": "ink_wash",
        "label": "水墨风",
        "style_prompt": (
            "traditional Chinese ink wash painting, sumi-e aesthetic, "
            "monochrome ink gradients with subtle warm accents, expressive brush strokes, "
            "rice paper texture, generous negative space, no photorealism, no 3D rendering"
        ),
        "analysis_hint": "TRADITIONAL CHINESE INK WASH PAINTING",
        "sort_order": 3,
    },
    {
        "style_id": "retro_photo",
        "label": "复古胶片",
        "style_prompt": (
            "vintage film photograph, warm faded colors, subtle grain and light leaks, "
            "soft focus, nostalgic 1990s snapshot aesthetic, natural lighting, "
            "no pixel art, no illustration, no 3D rendering"
        ),
        "analysis_hint": "VINTAGE FILM PHOTOGRAPH",
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
