"""add mpesa and sms config tables

Revision ID: 8a1c2e6f4b3d
Revises: 4d4474cbb4c5
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a1c2e6f4b3d'
down_revision: Union[str, None] = '4d4474cbb4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('mpesa_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('environment', sa.String(), nullable=True),
        sa.Column('paybill_number', sa.String(), nullable=True),
        sa.Column('passkey', sa.String(), nullable=True),
        sa.Column('consumer_key', sa.String(), nullable=True),
        sa.Column('consumer_secret', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mpesa_configs_id'), 'mpesa_configs', ['id'], unique=False)

    op.create_table('sms_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gateway', sa.String(), nullable=True),
        sa.Column('api_username', sa.String(), nullable=True),
        sa.Column('api_key', sa.String(), nullable=True),
        sa.Column('sender_id', sa.String(), nullable=True),
        sa.Column('twilio_sid', sa.String(), nullable=True),
        sa.Column('twilio_token', sa.String(), nullable=True),
        sa.Column('twilio_from', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sms_configs_id'), 'sms_configs', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sms_configs_id'), table_name='sms_configs')
    op.drop_table('sms_configs')

    op.drop_index(op.f('ix_mpesa_configs_id'), table_name='mpesa_configs')
    op.drop_table('mpesa_configs')
