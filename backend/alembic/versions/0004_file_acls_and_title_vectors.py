"""files with their own permissions (BUG-023); name/path vectors for ranking (BUG-027)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('files') as batch:
        batch.add_column(sa.Column('acl_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_files_acl_id_acls', 'acls', ['acl_id'], ['id'])
    op.create_index('ix_files_acl_id', 'files', ['acl_id'], unique=False,
                    postgresql_where=sa.text('acl_id IS NOT NULL'),
                    sqlite_where=sa.text('acl_id IS NOT NULL'))

    op.add_column('documents', sa.Column(
        'title_vector', postgresql.TSVECTOR().with_variant(sa.Text(), 'sqlite'), nullable=True))
    op.create_index('ix_documents_title_vector', 'documents', ['title_vector'], unique=False,
                    postgresql_using='gin')

    # Documents indexed before this revision have no name/path vector, and their text
    # was stored without reading the file's own permissions: index everything again
    # (the next `index` job). There is no production data yet; on a dev database this
    # only re-reads the test shares.
    op.execute("DELETE FROM documents")


def downgrade() -> None:
    op.drop_index('ix_documents_title_vector', table_name='documents')
    with op.batch_alter_table('documents') as batch:
        batch.drop_column('title_vector')
    op.drop_index('ix_files_acl_id', table_name='files')
    with op.batch_alter_table('files') as batch:
        batch.drop_constraint('fk_files_acl_id_acls', type_='foreignkey')
        batch.drop_column('acl_id')
