"""verification codes

Email verification uses a 6-digit code instead of a link: auth tokens get
a per-code salt and a count of wrong tries.

Revision ID: c4f19d2e8a71
Revises: b7e3a91c4d20
Create Date: 2026-09-30 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f19d2e8a71'
down_revision: Union[str, Sequence[str], None] = 'b7e3a91c4d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('auth_tokens', sa.Column('salt', sa.String(length=32), nullable=True))
    op.add_column('auth_tokens', sa.Column('attempts', sa.Integer(), server_default='0', nullable=False))
    # Links sent for verification before this no longer apply.
    op.execute("UPDATE auth_tokens SET used_at = now() WHERE purpose = 'verify_email' AND used_at IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('auth_tokens', 'attempts')
    op.drop_column('auth_tokens', 'salt')
