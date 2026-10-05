"""backfill payments and participants

Revision ID: 1b7285b0323f
Revises: 511cce97d84e
Create Date: 2026-09-29 16:45:11.807075

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b7285b0323f'
down_revision: Union[str, Sequence[str], None] = '511cce97d84e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Every expense must have at least one payment and one participant.
    Expenses saved before those tables existed get the default: the owner
    paid all of it, and it was all theirs. NOT EXISTS skips any expense
    that already has rows, so this is safe to run on any database.
    """
    op.execute(
        "INSERT INTO expense_payments (expense_id, user_id, amount) "
        "SELECT e.id, e.user_id, e.amount FROM expenses e "
        "WHERE NOT EXISTS "
        "(SELECT 1 FROM expense_payments p WHERE p.expense_id = e.id)"
    )
    op.execute(
        "INSERT INTO expense_participants (expense_id, user_id, share_amount) "
        "SELECT e.id, e.user_id, e.amount FROM expenses e "
        "WHERE NOT EXISTS "
        "(SELECT 1 FROM expense_participants s WHERE s.expense_id = e.id)"
    )


def downgrade() -> None:
    """Nothing to undo: the rows are ordinary data, and the previous
    migration's downgrade drops both tables anyway."""
    pass
