from sqlalchemy import String, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class ManagementSetting(Base):
    __tablename__='management_settings'
    key: Mapped[str]=mapped_column(String(100),primary_key=True)
    value: Mapped[dict]=mapped_column(JSON,default=dict)


class DeviceCommand(Base):
    __tablename__='device_commands'
    id: Mapped[str]=mapped_column(String(64),primary_key=True)
    station_id: Mapped[str]=mapped_column(String(64),index=True)
    kind: Mapped[str]=mapped_column(String(30))
    payload: Mapped[dict]=mapped_column(JSON,default=dict)
    status: Mapped[str]=mapped_column(String(30),default='queued')
    result: Mapped[str]=mapped_column(String(1000),default='')
    created: Mapped[float]=mapped_column(Float)


class UpdatePackage(Base):
    __tablename__='update_packages'
    id: Mapped[str]=mapped_column(String(64),primary_key=True)
    version: Mapped[str]=mapped_column(String(80))
    sha256: Mapped[str]=mapped_column(String(64))
    size: Mapped[float]=mapped_column(Float)
    created: Mapped[float]=mapped_column(Float)
