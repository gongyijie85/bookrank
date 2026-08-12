"""Add last_error_code/summary on publishers for source health

Revision ID: add_pub_last_error
Revises: add_batch_import_rcpt
Create Date: 2026-08-12 13:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = 'add_pub_last_error'
down_revision = 'add_batch_import_rcpt'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('publishers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_error_code', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('last_error_summary', sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('publishers', schema=None) as batch_op:
        batch_op.drop_column('last_error_summary')
        batch_op.drop_column('last_error_code')
