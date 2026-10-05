"""settlement kind

What money between the user and a contact was: paying back what was owed
(repayment), lending (loan), paying back an expense (reimbursement), or a
gift. Loans and repayments move a balance; a gift doesn't. Existing rows
were all recorded as repayments.

Revision ID: f2b8d4e6a913
Revises: e7a3c5d9f201
Create Date: 2026-10-01 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b8d4e6a913'
down_revision: Union[str, Sequence[str], None] = 'e7a3c5d9f201'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'settlements',
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='repayment'),
    )
    op.create_check_constraint(
        'ck_settlements_kind', 'settlements', "kind IN ('repayment', 'loan', 'reimbursement', 'gift')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_settlements_kind', 'settlements', type_='check')
    op.drop_column('settlements', 'kind')
