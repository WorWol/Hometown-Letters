"""add_mails_table

Revision ID: 3a1b2c3d4e5f
Revises: 9b1d5f7c2a11
Create Date: 2026-07-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = '9b1d5f7c2a11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mails',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('recipient_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(256), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('attached_postcard_id', sa.Integer(), nullable=True),
        sa.Column('attached_letter_id', sa.Integer(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('sender_deleted', sa.Boolean(), nullable=False),
        sa.Column('recipient_deleted', sa.Boolean(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['attached_letter_id'], ['letters.id']),
        sa.ForeignKeyConstraint(['attached_postcard_id'], ['postcards.id']),
        sa.ForeignKeyConstraint(['recipient_id'], ['users.id']),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_mails_recipient_time', 'mails', ['recipient_id', 'sent_at'], unique=False)
    op.create_index('ix_mails_sender_time', 'mails', ['sender_id', 'sent_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_mails_sender_time', table_name='mails')
    op.drop_index('ix_mails_recipient_time', table_name='mails')
    op.drop_table('mails')
