"""description

Revision ID: 0465b07f454c
Revises: ee099afcc156
Create Date: 2026-06-28 12:16:38.301758

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0465b07f454c'
down_revision: Union[str, None] = 'ee099afcc156'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
