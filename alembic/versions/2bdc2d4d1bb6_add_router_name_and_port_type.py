"""add router name and change port type

Revision ID: 2bdc2d4d1bb6
Revises: 48935a76d5f6
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2bdc2d4d1bb6'
down_revision: Union[str, None] = '48935a76d5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('routers') as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(), nullable=True))
        batch_op.alter_column('port', type_=sa.Integer(), existing_type=sa.String(),
                               server_default='8728', postgresql_using='port::integer')


def downgrade() -> None:
    with op.batch_alter_table('routers') as batch_op:
        batch_op.drop_column('name')
        batch_op.alter_column('port', type_=sa.String(), existing_type=sa.Integer(),
                               server_default=None)
