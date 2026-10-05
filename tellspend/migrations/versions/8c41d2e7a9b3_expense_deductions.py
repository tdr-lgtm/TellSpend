"""expense deductions and refunds

Deductions (discounts, rounding down) become lines of their own kind,
like charges; discount_amount stays as their total. Every expense that
already has a discount gets one "discount" line for it, since that's all
that was recorded.

Refunds are their own event: money given back after paying, to one
person (you or a contact), with a date. Shares add up to the amount less
the refunds.

Revision ID: 8c41d2e7a9b3
Revises: 5d87ffdbfe13
Create Date: 2026-09-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c41d2e7a9b3'
down_revision: Union[str, Sequence[str], None] = '5d87ffdbfe13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('expense_deductions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('expense_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('label', sa.String(length=100), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.CheckConstraint("kind IN ('discount', 'rounding', 'other')", name='ck_expense_deductions_kind_valid'),
    sa.CheckConstraint('amount > 0', name='ck_expense_deductions_amount_positive'),
    sa.ForeignKeyConstraint(['expense_id'], ['expenses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_expense_deductions_expense_id'), 'expense_deductions', ['expense_id'], unique=False)

    op.create_table('expense_refunds',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('expense_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('counterparty_id', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('label', sa.String(length=100), nullable=True),
    sa.Column('date', sa.Date(), nullable=False),
    sa.CheckConstraint('(user_id IS NULL) <> (counterparty_id IS NULL)', name='ck_expense_refunds_one_recipient'),
    sa.CheckConstraint('amount > 0', name='ck_expense_refunds_amount_positive'),
    sa.ForeignKeyConstraint(['counterparty_id'], ['counterparties.id']),
    sa.ForeignKeyConstraint(['expense_id'], ['expenses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_expense_refunds_expense_id'), 'expense_refunds', ['expense_id'], unique=False)
    op.create_index(op.f('ix_expense_refunds_counterparty_id'), 'expense_refunds', ['counterparty_id'], unique=False)

    op.execute(
        """
        INSERT INTO expense_deductions (expense_id, kind, label, amount)
        SELECT id, 'discount', 'Discount', discount_amount
        FROM expenses
        WHERE discount_amount > 0
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_expense_refunds_counterparty_id'), table_name='expense_refunds')
    op.drop_index(op.f('ix_expense_refunds_expense_id'), table_name='expense_refunds')
    op.drop_table('expense_refunds')
    op.drop_index(op.f('ix_expense_deductions_expense_id'), table_name='expense_deductions')
    op.drop_table('expense_deductions')
