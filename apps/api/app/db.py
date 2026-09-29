import os
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import create_engine, event, String, Integer, Boolean, Text, JSON, ForeignKey, Float, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(os.getenv('APP_RESOURCE_ROOT', str(Path(__file__).resolve().parents[3])))
DATA = Path(os.getenv('DATA_DIR', str(ROOT / 'var')))
DATA.mkdir(parents=True, exist_ok=True)
(DATA / 'media').mkdir(exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{(DATA / "dispetcher.db").as_posix()}')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False, 'timeout': 30} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def configure_sqlite(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA journal_mode=WAL')
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def now():
    return datetime.now(timezone.utc).isoformat()

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(30))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    audit_access: Mapped[bool] = mapped_column(Boolean, default=False)
    group_id: Mapped[int | None] = mapped_column(ForeignKey('groups.id'), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class Group(Base):
    __tablename__ = 'groups'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    teacher_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

class LoginSession(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expires: Mapped[float] = mapped_column(Float)

class Ticket(Base):
    __tablename__ = 'tickets'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class TicketVersion(Base):
    __tablename__ = 'ticket_versions'
    __table_args__ = (UniqueConstraint('ticket_id', 'number'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('tickets.id'))
    number: Mapped[int] = mapped_column(Integer)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Assignment(Base):
    __tablename__ = 'assignments'
    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey('lessons.id'), nullable=True, index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey('ticket_versions.id'))
    student_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    teacher_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(200))
    start_mode: Mapped[str] = mapped_column(String(20), default='self')
    released: Mapped[bool] = mapped_column(Boolean, default=True)
    training: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Attempt(Base):
    __tablename__ = 'attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey('assignments.id'))
    student_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    task_index: Mapped[int] = mapped_column(Integer)
    delivery_key: Mapped[str | None] = mapped_column(String(100),nullable=True,unique=True)
    status: Mapped[str] = mapped_column(String(30), default='ringing')
    revision: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[dict] = mapped_column(JSON)
    card: Mapped[dict] = mapped_column(JSON)
    state: Mapped[dict] = mapped_column(JSON)
    assessment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[str] = mapped_column(String(40), default=now)
    submitted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class AttemptEvent(Base):
    __tablename__ = 'attempt_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey('attempts.id'), index=True)
    command_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    kind: Mapped[str] = mapped_column(String(80))
    data: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    at: Mapped[str] = mapped_column(String(40), default=now)

class Audit(Base):
    __tablename__ = 'audit_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(160), default='Система')
    action: Mapped[str] = mapped_column(String(100), index=True)
    target: Mapped[str] = mapped_column(String(100), default='')
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[str] = mapped_column(String(40), default=now, index=True)

class Media(Base):
    __tablename__ = 'media_assets'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))

class ScheduledEvent(Base):
    __tablename__ = 'scheduled_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey('attempts.id'), index=True)
    due: Mapped[float] = mapped_column(Float, index=True)
    data: Mapped[dict] = mapped_column(JSON)
    done: Mapped[bool] = mapped_column(Boolean, default=False)

class Classifier(Base):
    __tablename__ = 'classifier_types'
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    traits: Mapped[list] = mapped_column(JSON)
    source: Mapped[dict] = mapped_column(JSON)

class Lesson(Base):
    __tablename__ = 'lessons'
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default='prepared')
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
class Material(Base):
    __tablename__ = 'materials'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    group_id: Mapped[int] = mapped_column(ForeignKey('groups.id'))
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
