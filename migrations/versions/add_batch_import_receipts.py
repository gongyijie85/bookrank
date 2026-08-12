"""Add batch_import_receipts for idempotent crawl batch imports

Revision ID: add_batch_import_rcpt
Revises: add_nb_editions_src
Create Date: 2026-08-12 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = 'add_batch_import_rcpt'
down_revision = 'add_nb_editions_src'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'batch_import_receipts',
        sa.Column('batch_id', sa.String(length=128), nullable=False),
        sa.Column('content_sha256', sa.String(length=64), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('receipt_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('batch_id'),
    )
    with op.batch_alter_table('batch_import_receipts', schema=None) as batch_op:
        batch_op.create_index('ix_batch_import_receipts_source_id', ['source_id'], unique=False)


def downgrade():
    with op.batch_alter_table('batch_import_receipts', schema=None) as batch_op:
        batch_op.drop_index('ix_batch_import_receipts_source_id')
    op.drop_table('batch_import_receipts')
