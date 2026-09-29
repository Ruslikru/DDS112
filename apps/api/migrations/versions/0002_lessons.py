"""Persistent teacher-controlled lessons; existing assignments remain independent."""
from alembic import op
import sqlalchemy as sa
revision = '0002'
down_revision = '0001'
branch_labels = depends_on = None

def upgrade():
    op.create_table('lessons', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('teacher_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(200), nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False), sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('started_at', sa.String(40)), sa.Column('ended_at', sa.String(40)))
    with op.batch_alter_table('assignments') as batch:
        batch.add_column(sa.Column('lesson_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_assignment_lesson', 'lessons', ['lesson_id'], ['id'])
        batch.create_index('ix_assignments_lesson_id', ['lesson_id'])

def downgrade():
    with op.batch_alter_table('assignments') as batch:
        batch.drop_index('ix_assignments_lesson_id')
        batch.drop_constraint('fk_assignment_lesson', type_='foreignkey')
        batch.drop_column('lesson_id')
    op.drop_table('lessons')
