"""update image_styles style_prompt and analysis_hint to Chinese"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "12_image_styles_zh"
down_revision: Union[str, Sequence[str], None] = "11_image_styles"
branch_labels = None
depends_on = None


# 中文风格描述（与 style_service.STYLES 保持一致）
_ZH = [
    {
        "style_id": "pixel_16bit",
        "style_prompt": "16位复古像素画，SNES/GBA时代游戏截图质感，可见像素网格与锐利方块边缘，平涂2D着色，低色彩数怀旧暖色调色板，dithering抖动过渡，CPS2/Neo Geo美学",
        "analysis_hint": "复古16位像素风",
    },
    {
        "style_id": "watercolor",
        "style_prompt": "柔和水彩画，细腻晕染与洇边，可见纸张纹理，透明色层叠加，柔和渐变，手绘插画质感，暖色怀旧调",
        "analysis_hint": "柔和水彩画",
    },
    {
        "style_id": "ghibli",
        "style_prompt": "吉卜力风格动漫插画，温暖手绘背景，柔和自然光，繁茂细致景色，赛璐璐角色，怀旧温柔氛围，绘画质感",
        "analysis_hint": "吉卜力风格动漫插画",
    },
    {
        "style_id": "ink_wash",
        "style_prompt": "传统中国水墨画，写意水墨，单色墨韵渐变带细微暖色点缀，写意笔触，宣纸纹理，大量留白",
        "analysis_hint": "传统中国水墨画",
    },
    {
        "style_id": "retro_photo",
        "style_prompt": "复古胶片照片，暖色褪色，细微颗粒与漏光，柔焦，90年代快照质感，自然光",
        "analysis_hint": "复古胶片照片",
    },
]

# 英文原值（用于 downgrade 回退）
_EN = [
    {"style_id": "pixel_16bit", "style_prompt": "retro 16-bit pixel art, nostalgic game screenshot aesthetic, warm nostalgic color palette, visible pixel grid and crisp blocky edges, flat 2D shading with limited color count, SNES/GBA-era sprite art quality, no smooth gradients, no photorealistic detail, no 3D rendering", "analysis_hint": "RETRO 16-BIT PIXEL ART"},
    {"style_id": "watercolor", "style_prompt": "soft watercolor painting, delicate washes and bleeding edges, warm nostalgic color palette, visible paper texture, gentle gradients, hand-painted illustration aesthetic, no sharp pixel edges, no 3D rendering", "analysis_hint": "SOFT WATERCOLOR PAINTING"},
    {"style_id": "ghibli", "style_prompt": "Studio Ghibli style anime illustration, warm hand-painted backgrounds, soft natural lighting, lush detailed scenery, nostalgic and gentle atmosphere, cel-shaded characters, painterly texture, no photorealism, no 3D rendering", "analysis_hint": "STUDIO GHIBLI STYLE ANIME ILLUSTRATION"},
    {"style_id": "ink_wash", "style_prompt": "traditional Chinese ink wash painting, sumi-e aesthetic, monochrome ink gradients with subtle warm accents, expressive brush strokes, rice paper texture, generous negative space, no photorealism, no 3D rendering", "analysis_hint": "TRADITIONAL CHINESE INK WASH PAINTING"},
    {"style_id": "retro_photo", "style_prompt": "vintage film photograph, warm faded colors, subtle grain and light leaks, soft focus, nostalgic 1990s snapshot aesthetic, natural lighting, no pixel art, no illustration, no 3D rendering", "analysis_hint": "VINTAGE FILM PHOTOGRAPH"},
]


def _apply(bind, rows):
    for item in rows:
        bind.execute(
            sa.text(
                "UPDATE image_styles SET style_prompt = :prompt, analysis_hint = :hint "
                "WHERE style_id = :sid"
            ),
            {
                "prompt": item["style_prompt"],
                "hint": item["analysis_hint"],
                "sid": item["style_id"],
            },
        )


def upgrade() -> None:
    _apply(op.get_bind(), _ZH)


def downgrade() -> None:
    _apply(op.get_bind(), _EN)
