"""Device management and service rules."""
from alembic import op
from sqlalchemy import Column, JSON, inspect
from apps.api.app.management_models import ManagementSetting, DeviceCommand, UpdatePackage
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None

def upgrade():
    for model in (ManagementSetting,DeviceCommand,UpdatePackage):model.__table__.create(op.get_bind(),checkfirst=True)
    if 'config' not in {c['name'] for c in inspect(op.get_bind()).get_columns('service_definitions')}:
        op.add_column('service_definitions',Column('config',JSON,nullable=True))

def downgrade():
    op.drop_column('service_definitions','config')
    for model in (UpdatePackage,DeviceCommand,ManagementSetting):model.__table__.drop(op.get_bind(),checkfirst=True)
