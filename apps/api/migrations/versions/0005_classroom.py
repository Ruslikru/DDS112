"""Classroom, approved examples and training profiles."""
from alembic import op
from apps.api.app.classroom_models import (Workstation, ApprovedAnswer, TrainingProfile,
                                           MiniQuestion, ServiceDefinition, ClassroomLink)
revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None
TABLES=(Workstation, ApprovedAnswer, TrainingProfile, MiniQuestion, ServiceDefinition, ClassroomLink)

def upgrade():
    for model in TABLES: model.__table__.create(op.get_bind(),checkfirst=True)

def downgrade():
    for model in reversed(TABLES): model.__table__.drop(op.get_bind(),checkfirst=True)
