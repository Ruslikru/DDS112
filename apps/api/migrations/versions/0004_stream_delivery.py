"""Unique delivery identity for concurrent DDS arrivals; normal retries remain possible."""
from alembic import op
import sqlalchemy as sa

revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('attempts',sa.Column('delivery_key',sa.String(100),nullable=True))
    op.create_index('uq_attempts_delivery_key','attempts',['delivery_key'],unique=True)


def downgrade():
    op.drop_index('uq_attempts_delivery_key',table_name='attempts')
    op.drop_column('attempts','delivery_key')
