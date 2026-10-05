"""notes, expense links and expected money

An expense keeps a note (what was worked out: an estimate, a repeating
cost). A settlement can say which expense it pays back, so deleting or
changing that expense can say so. Money expected but not yet moved
("he'll pay me back next week") is kept apart, changing no balance.

Revision ID: b9d1f3a5c702
Revises: a4c6e8f0b215
Create Date: 2026-10-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9d1f3a5c702'
down_revision: Union[str, Sequence[str], None] = 'a4c6e8f0b215'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('expenses', sa.Column('note', sa.String(length=500), nullable=True))

    op.add_column('settlements', sa.Column('expense_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_settlements_expense_id_expenses', 'settlements', 'expenses',
        ['expense_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_settlements_expense_id', 'settlements', ['expense_id'])

    op.create_table(
        'expected_money',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('counterparty_id', sa.Integer(), sa.ForeignKey('counterparties.id'), nullable=False),
        sa.Column('direction', sa.String(length=20), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='repayment'),
        sa.Column('amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('amount IS NULL OR amount > 0', name='ck_expected_money_amount_positive'),
        sa.CheckConstraint("direction IN ('they_pay_me', 'i_pay_them')", name='ck_expected_money_direction_valid'),
    )
    op.create_index('ix_expected_money_user_id', 'expected_money', ['user_id'])
    op.create_index('ix_expected_money_counterparty_id', 'expected_money', ['counterparty_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_expected_money_counterparty_id', table_name='expected_money')
    op.drop_index('ix_expected_money_user_id', table_name='expected_money')
    op.drop_table('expected_money')
    op.drop_index('ix_settlements_expense_id', table_name='settlements')
    op.drop_constraint('fk_settlements_expense_id_expenses', 'settlements', type_='foreignkey')
    op.drop_column('settlements', 'expense_id')
    op.drop_column('expenses', 'note')
