"""Class meetings, temporary teams and authenticated attendance."""
from alembic import op
import sqlalchemy as sa

revision='0010'
down_revision='0009'
branch_labels=None
depends_on=None


def upgrade():
    from apps.api.app.training_session_models import TrainingSession, SessionMember, SessionMiniGroup, StudentPresence
    bind=op.get_bind()
    for model in (TrainingSession,SessionMember,SessionMiniGroup,StudentPresence):
        model.__table__.create(bind,checkfirst=True)
    for table in ('lessons','assignments'):
        if 'session_id' not in {column['name'] for column in sa.inspect(bind).get_columns(table)}:
            if bind.dialect.name=='sqlite':
                # Nullable REFERENCES is supported by SQLite ADD COLUMN: no table rewrite.
                op.execute(sa.text('ALTER TABLE '+table+' ADD COLUMN session_id INTEGER REFERENCES training_sessions(id)'))
            else:
                op.add_column(table,sa.Column('session_id',sa.Integer,sa.ForeignKey('training_sessions.id'),nullable=True))
            op.create_index('ix_'+table+'_session_id',table,['session_id'])


def downgrade():
    raise RuntimeError('Attendance is historical data; restore an explicit backup to downgrade.')
