"""add duration and data_limit to products

Revision ID: caf6ae8ae94b
Revises: 57761276767e
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'caf6ae8ae94b'
down_revision: Union[str, None] = '57761276767e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('duration', sa.Integer(), nullable=True))
    op.add_column('products', sa.Column('data_limit', sa.String(), server_default='Unlimited', nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'data_limit')
    op.drop_column('products', 'duration')
