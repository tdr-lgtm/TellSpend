"""item unit price

The price of one unit of a bill line, kept next to its quantity and line
total when it's known ("4 bottles of juice at 85 each"). Lines saved
before this have no unit price recorded.

Revision ID: e7a3c5d9f201
Revises: d2a8b6f0c913
Create Date: 2026-10-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7a3c5d9f201'
down_revision: Union[str, Sequence[str], None] = 'd2a8b6f0c913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('expense_items', sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=True))
    op.create_check_constraint(
        'ck_expense_items_unit_price_positive', 'expense_items', 'unit_price IS NULL OR unit_price > 0'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_expense_items_unit_price_positive', 'expense_items', type_='check')
    op.drop_column('expense_items', 'unit_price')
