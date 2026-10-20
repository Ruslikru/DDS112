"""A classroom meeting owns temporary teams and durable attendance snapshots."""
from sqlalchemy import String, Integer, Float, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, now


class TrainingSession(Base):
    __tablename__ = 'training_sessions'
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default='prepared')
    group_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SessionMember(Base):
    __tablename__ = 'training_session_members'
    __table_args__ = (UniqueConstraint('session_id', 'student_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('training_sessions.id'), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    name: Mapped[str] = mapped_column(String(160))
    group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    group_name: Mapped[str] = mapped_column(String(160), default='')
    first_seen: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen: Mapped[float | None] = mapped_column(Float, nullable=True)
    intervals: Mapped[list] = mapped_column(JSON, default=list)


class SessionMiniGroup(Base):
    __tablename__ = 'training_session_mini_groups'
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey('training_sessions.id'), index=True)
    name: Mapped[str] = mapped_column(String(160))
    students: Mapped[list] = mapped_column(JSON, default=list)


class StudentPresence(Base):
    """Only authenticated browser heartbeats update this clock, never desktop agent polls."""
    __tablename__ = 'student_presence'
    student_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    last_seen: Mapped[float] = mapped_column(Float)
