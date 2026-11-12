"""rate events

Rate limits (assistant reads, wrong passwords, sign-ups, reset requests)
are counted in the database instead of the server's memory, so a restart
doesn't reset them.

Revision ID: d7a1c3e5f902
Revises: b9d1f3a5c702
Create Date: 2026-11-06 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a1c3e5f902'
down_revision: Union[str, Sequence[str], None] = 'b9d1f3a5c702'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'rate_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bucket', sa.String(length=32), nullable=False),
        sa.Column('key', sa.String(length=400), nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rate_events_bucket_key_at', 'rate_events', ['bucket', 'key', 'at'])
    op.create_index('ix_rate_events_at', 'rate_events', ['at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_rate_events_at', table_name='rate_events')
    op.drop_index('ix_rate_events_bucket_key_at', table_name='rate_events')
    op.drop_table('rate_events')
