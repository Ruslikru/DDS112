"""Immutable speech generation jobs."""
from alembic import op
import sqlalchemy as sa
revision='0008'
down_revision='0007'
branch_labels=None
depends_on=None
def upgrade():
    bind=op.get_bind()
    if 'voice_jobs' not in sa.inspect(bind).get_table_names():
        op.create_table('voice_jobs',sa.Column('id',sa.String(64),primary_key=True),sa.Column('status',sa.String(20),nullable=False),sa.Column('data',sa.JSON,nullable=False),sa.Column('audio_id',sa.String(64),nullable=True),sa.Column('error',sa.Text,nullable=False))
        op.create_index('ix_voice_jobs_status','voice_jobs',['status'])
def downgrade():
    op.drop_table('voice_jobs')
