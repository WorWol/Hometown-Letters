"""add_letter_summary_and_memory

Revision ID: 9b1d5f7c2a11
Revises: 6e27f118ea48
Create Date: 2026-07-13 00:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9b1d5f7c2a11'
down_revision: Union[str, Sequence[str], None] = '6e27f118ea48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'letter_summaries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('batch_no', sa.Integer(), nullable=False),
        sa.Column('start_letter_id', sa.Integer(), nullable=False),
        sa.Column('end_letter_id', sa.Integer(), nullable=False),
        sa.Column('letter_count', sa.Integer(), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=True),
        sa.Column('source_letter_ids', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['end_letter_id'], ['letters.id']),
        sa.ForeignKeyConstraint(['start_letter_id'], ['letters.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'batch_no'),
    )
    op.create_index('ix_letter_summaries_user_batch', 'letter_summaries', ['user_id', 'batch_no'], unique=False)

    op.create_table(
        'letter_memories',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('summary_id', sa.Integer(), nullable=False),
        sa.Column('memory_overview', sa.Text(), nullable=True),
        sa.Column('emotion_signals', sa.JSON(), nullable=True),
        sa.Column('place_signals', sa.JSON(), nullable=True),
        sa.Column('theme_signals', sa.JSON(), nullable=True),
        sa.Column('people_signals', sa.JSON(), nullable=True),
        sa.Column('sensory_signals', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['summary_id'], ['letter_summaries.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('summary_id'),
    )
    op.create_index('ix_letter_memories_user_summary', 'letter_memories', ['user_id', 'summary_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_letter_memories_user_summary', table_name='letter_memories')
    op.drop_table('letter_memories')
    op.drop_index('ix_letter_summaries_user_batch', table_name='letter_summaries')
    op.drop_table('letter_summaries')
