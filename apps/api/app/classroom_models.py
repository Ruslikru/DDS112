"""Persistent classroom configuration; live media is never stored in this database."""
from sqlalchemy import String, Text, JSON, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, now


class Workstation(Base):
    __tablename__ = 'workstations'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    secret_hash: Mapped[str] = mapped_column(String(64))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    last_seen: Mapped[float] = mapped_column(Float, default=0)


class ApprovedAnswer(Base):
    __tablename__ = 'approved_answers'
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(Text)
    criterion: Mapped[str] = mapped_column(Text)
    attempt_id: Mapped[int] = mapped_column(ForeignKey('attempts.id'))
    criterion_id: Mapped[str] = mapped_column(String(80))
    teacher_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class TrainingProfile(Base):
    __tablename__ = 'training_profiles'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class MiniQuestion(Base):
    __tablename__ = 'mini_questions'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    data: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ServiceDefinition(Base):
    __tablename__ = 'service_definitions'
    name: Mapped[str] = mapped_column(String(160), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict | None] = mapped_column(JSON, default=dict, nullable=True)


class ClassroomLink(Base):
    __tablename__ = 'classroom_links'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    student_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    mode: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
