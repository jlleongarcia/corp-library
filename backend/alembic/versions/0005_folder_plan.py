"""phase 2: folder plan and its daily compliance snapshots

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('plan_folders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('share_id', sa.Integer(), nullable=False),
    sa.Column('path', sa.Text(), nullable=False),
    sa.Column('path_key', sa.Text(), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('belongs', sa.Text(), nullable=False),
    sa.Column('not_belongs', sa.Text(), nullable=False),
    sa.Column('owner', sa.String(length=200), nullable=False),
    sa.Column('naming', sa.Text(), nullable=False),
    sa.Column('naming_pattern', sa.String(length=300), nullable=True),
    sa.Column('examples', sa.JSON(), nullable=False),
    sa.Column('extensions', sa.JSON(), nullable=False),
    sa.Column('keywords', sa.JSON(), nullable=False),
    sa.Column('allow_files', sa.Boolean(), nullable=False),
    sa.Column('allow_subfolders', sa.Boolean(), nullable=False),
    sa.Column('max_files', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['share_id'], ['shares.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('share_id', 'path_key', name='uq_plan_folders_share_path')
    )
    op.create_index(op.f('ix_plan_folders_share_id'), 'plan_folders', ['share_id'], unique=False)

    op.create_table('plan_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('share_id', sa.Integer(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('taken_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('files_total', sa.Integer(), nullable=False),
    sa.Column('files_in_plan', sa.Integer(), nullable=False),
    sa.Column('files_checked', sa.Integer(), nullable=False),
    sa.Column('files_misnamed', sa.Integer(), nullable=False),
    sa.Column('files_wrong_type', sa.Integer(), nullable=False),
    sa.Column('folders_planned', sa.Integer(), nullable=False),
    sa.Column('folders_missing', sa.Integer(), nullable=False),
    sa.Column('folders_empty', sa.Integer(), nullable=False),
    sa.Column('folders_overgrown', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['share_id'], ['shares.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('share_id', 'day', name='uq_plan_snapshots_share_day')
    )
    op.create_index(op.f('ix_plan_snapshots_share_id'), 'plan_snapshots', ['share_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_plan_snapshots_share_id'), table_name='plan_snapshots')
    op.drop_table('plan_snapshots')
    op.drop_index(op.f('ix_plan_folders_share_id'), table_name='plan_folders')
    op.drop_table('plan_folders')
