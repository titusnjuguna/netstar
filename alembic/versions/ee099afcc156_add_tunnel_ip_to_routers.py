"""add_tunnel_ip_to_routers

Revision ID: ee099afcc156
Revises: 75fe396f5081
Create Date: 2026-06-28 12:15:39.321900

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee099afcc156'
down_revision: Union[str, None] = '75fe396f5081'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('routers', sa.Column('tunnel_ip', sa.String(), nullable=True))
    op.create_unique_constraint('uq_routers_tunnel_ip', 'routers', ['tunnel_ip'])


def downgrade() -> None:
    op.drop_constraint('uq_routers_tunnel_ip', 'routers', type_='unique')
    op.drop_column('routers', 'tunnel_ip')
