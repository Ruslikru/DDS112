"""Speech jobs a teacher is waiting for go first."""
from alembic import op
import sqlalchemy as sa
revision='0009'
down_revision='0008'
branch_labels=None
depends_on=None
def upgrade():
    bind=op.get_bind()
    if 'priority' not in {c['name'] for c in sa.inspect(bind).get_columns('voice_jobs')}:
        op.add_column('voice_jobs',sa.Column('priority',sa.Float,nullable=False,server_default='0'))
        op.create_index('ix_voice_jobs_priority','voice_jobs',['priority'])
def downgrade():
    op.drop_index('ix_voice_jobs_priority','voice_jobs')
    op.drop_column('voice_jobs','priority')
