"""add_wire_address_to_routers

Revision ID: 75fe396f5081
Revises: d4e5f6a7b8c9
Create Date: 2026-06-28 12:11:30.433144

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75fe396f5081'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('routers', sa.Column('wire_address', sa.String(), nullable=True))
    op.create_unique_constraint('uq_routers_wire_address', 'routers', ['wire_address'])


def downgrade() -> None:
    op.drop_constraint('uq_routers_wire_address', 'routers', type_='unique')
    op.drop_column('routers', 'wire_address')
