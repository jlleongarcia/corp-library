"""record unlisted folders and skipped reparse-point folders

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('folders', sa.Column('list_error', sa.String(length=500), nullable=True))
    op.add_column('scan_runs', sa.Column('folders_skipped', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('scan_runs') as batch:
        batch.drop_column('folders_skipped')
    with op.batch_alter_table('folders') as batch:
        batch.drop_column('list_error')
