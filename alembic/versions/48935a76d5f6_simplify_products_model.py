"""simplify products model

Revision ID: 48935a76d5f6
Revises: caf6ae8ae94b
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48935a76d5f6'
down_revision: Union[str, None] = 'caf6ae8ae94b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('products') as batch_op:
        batch_op.alter_column('product_name', new_column_name='name')
        batch_op.add_column(sa.Column('speed_limit', sa.String(), nullable=True))
        batch_op.drop_column('product_category')
        batch_op.drop_column('download')
        batch_op.drop_column('upload')
        batch_op.drop_column('billing_period')
        batch_op.drop_column('product_status')
        batch_op.drop_column('router_id')


def downgrade() -> None:
    with op.batch_alter_table('products') as batch_op:
        batch_op.alter_column('name', new_column_name='product_name')
        batch_op.drop_column('speed_limit')
        batch_op.add_column(sa.Column('product_category', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('download', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('upload', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('billing_period', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('product_status', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('router_id', sa.Integer(), sa.ForeignKey('routers.id'), nullable=True))
