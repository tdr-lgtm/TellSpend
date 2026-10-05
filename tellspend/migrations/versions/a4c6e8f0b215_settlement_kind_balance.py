"""settlement kind: balance

A debt that already existed when it was recorded ("Parth owed me 600"):
no money moved, but it counts towards what's owed like a loan.

Revision ID: a4c6e8f0b215
Revises: f2b8d4e6a913
Create Date: 2026-10-01 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a4c6e8f0b215'
down_revision: Union[str, Sequence[str], None] = 'f2b8d4e6a913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_settlements_kind', 'settlements', type_='check')
    op.create_check_constraint(
        'ck_settlements_kind', 'settlements',
        "kind IN ('repayment', 'loan', 'reimbursement', 'gift', 'balance')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_settlements_kind', 'settlements', type_='check')
    op.create_check_constraint(
        'ck_settlements_kind', 'settlements', "kind IN ('repayment', 'loan', 'reimbursement', 'gift')"
    )
