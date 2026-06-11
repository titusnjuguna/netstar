"""add hotspot_name to routers

Revision ID: 4d4474cbb4c5
Revises: 2bdc2d4d1bb6
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d4474cbb4c5'
down_revision: Union[str, None] = '2bdc2d4d1bb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('routers') as batch_op:
        batch_op.add_column(sa.Column('hotspot_name', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('routers') as batch_op:
        batch_op.drop_column('hotspot_name')
