"""Password reset and archived user accounts."""
from alembic import op
import sqlalchemy as sa

revision='0007'
down_revision='0006'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('deleted_at', sa.String(40), nullable=True))

def downgrade():
    op.drop_column('users', 'deleted_at')
    op.drop_column('users', 'must_change_password')
