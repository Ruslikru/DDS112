"""Group-scoped teaching reference materials."""
from alembic import op
import sqlalchemy as sa
revision='0003'
down_revision='0002'
branch_labels=depends_on=None

def upgrade():
    op.create_table('materials',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('title',sa.String(200),nullable=False),sa.Column('body',sa.Text(),nullable=False),
        sa.Column('group_id',sa.Integer(),sa.ForeignKey('groups.id'),nullable=False),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.String(40),nullable=False))

def downgrade():
    op.drop_table('materials')
