"""item owners

Whose each item on a bill is, and how much of its price: saved from the
assistant's drafts so questions like "who had the burger?" can be answered
from stored data. Items saved before this have no owners recorded.

Revision ID: d2a8b6f0c913
Revises: c4f19d2e8a71
Create Date: 2026-09-30 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2a8b6f0c913'
down_revision: Union[str, Sequence[str], None] = 'c4f19d2e8a71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('expense_item_owners',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('counterparty_id', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.CheckConstraint('(user_id IS NULL) <> (counterparty_id IS NULL)', name='ck_expense_item_owners_one_owner'),
    sa.CheckConstraint('amount > 0', name='ck_expense_item_owners_amount_positive'),
    sa.ForeignKeyConstraint(['counterparty_id'], ['counterparties.id']),
    sa.ForeignKeyConstraint(['item_id'], ['expense_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_expense_item_owners_item_id'), 'expense_item_owners', ['item_id'], unique=False)
    op.create_index(op.f('ix_expense_item_owners_counterparty_id'), 'expense_item_owners', ['counterparty_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_expense_item_owners_counterparty_id'), table_name='expense_item_owners')
    op.drop_index(op.f('ix_expense_item_owners_item_id'), table_name='expense_item_owners')
    op.drop_table('expense_item_owners')
