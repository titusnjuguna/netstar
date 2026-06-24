"""add router_id to products

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-24 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('products') as batch_op:
        batch_op.add_column(sa.Column('router_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_products_router_id', 'routers', ['router_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_constraint('fk_products_router_id', type_='foreignkey')
        batch_op.drop_column('router_id')
