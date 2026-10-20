"""add_server_default_to_is_active

Revision ID: 5994cf723541
Revises: 160f64e2dc7c
Create Date: 2026-10-21 00:01:34.680406

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5994cf723541'
down_revision: Union[str, Sequence[str], None] = '160f64e2dc7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add server-level DEFAULT true to users.is_active."""
    op.alter_column(
        'users',
        'is_active',
        server_default=sa.true(),
        existing_type=sa.Boolean(),
        existing_nullable=False
    )


def downgrade() -> None:
    """Remove server-level DEFAULT from users.is_active."""
    op.alter_column(
        'users',
        'is_active',
        server_default=None,
        existing_type=sa.Boolean(),
        existing_nullable=False
    )
