"""Add editions/provenance on new_books and source controls on publishers

Revision ID: add_nb_editions_src
Revises: add_csrf_tokens_table
Create Date: 2026-08-12 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = 'add_nb_editions_src'
down_revision = 'add_csrf_tokens_table'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('new_books', schema=None) as batch_op:
        batch_op.add_column(sa.Column('canonical_source_url', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('editions_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('field_provenance_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('last_import_batch_id', sa.String(length=128), nullable=True))

    with op.batch_alter_table('publishers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('site_crawl_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('site_import_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('site_display_primary', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(
            sa.Column('fallback_google_enabled', sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(sa.Column('source_status', sa.String(length=32), nullable=False, server_default='healthy'))
        batch_op.add_column(sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('consecutive_successes', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('last_success_batch_id', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('last_attempt_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('publishers', schema=None) as batch_op:
        batch_op.drop_column('last_attempt_at')
        batch_op.drop_column('last_success_batch_id')
        batch_op.drop_column('consecutive_successes')
        batch_op.drop_column('consecutive_failures')
        batch_op.drop_column('source_status')
        batch_op.drop_column('fallback_google_enabled')
        batch_op.drop_column('site_display_primary')
        batch_op.drop_column('site_import_enabled')
        batch_op.drop_column('site_crawl_enabled')

    with op.batch_alter_table('new_books', schema=None) as batch_op:
        batch_op.drop_column('last_import_batch_id')
        batch_op.drop_column('field_provenance_json')
        batch_op.drop_column('editions_json')
        batch_op.drop_column('canonical_source_url')
