"""add registration fields to routers

Revision ID: a1b2c3d4e5f6
Revises: 8a1c2e6f4b3d
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '8a1c2e6f4b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('routers') as batch_op:
        batch_op.add_column(sa.Column('reg_token', sa.String(), nullable=True, unique=True))
        batch_op.add_column(sa.Column('public_ip', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('last_seen', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('routers') as batch_op:
        batch_op.drop_column('last_seen')
        batch_op.drop_column('public_ip')
        batch_op.drop_column('reg_token')
