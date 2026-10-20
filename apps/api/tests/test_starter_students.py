from argon2 import PasswordHasher
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from apps.api.app.db import Base, User, Group
from apps.api.app.initial_library import seed


def database():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine, tables=[Group.__table__, User.__table__])
    return Session(engine)


def test_new_classroom_has_five_working_student_logins(monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD', '12345678')
    with database() as db:
        seed(db)
        students = list(db.scalars(select(User).where(User.role == 'student')))
        assert {u.login for u in students} == {'student', 'student2', 'student3', 'student4', 'student5'}
        assert len({u.group_id for u in students}) == 1
        assert all(PasswordHasher().verify(u.password_hash, '12345678') for u in students)
        seed(db)
        assert len(list(db.scalars(select(User)))) == 7


def test_old_classroom_gets_missing_students_without_overwriting_users(monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD', '12345678')
    with database() as db:
        group = Group(name='Моя учебная группа')
        db.add(group)
        db.flush()
        first = User(login='student', name='Моё имя', role='student', password_hash='old-custom-hash', group_id=group.id)
        second = User(login='student2', name='Второй', role='student', password_hash='another-hash', group_id=group.id)
        archived = User(login='student3', name='Сохранённый пользователь', role='student', password_hash='archived-hash', group_id=group.id, active=False, deleted_at='2026-10-01')
        db.add_all([first, second, archived])
        db.commit()
        seed(db)
        assert first.name == 'Моё имя' and first.password_hash == 'old-custom-hash'
        assert not archived.active and archived.deleted_at == '2026-10-01' and archived.password_hash == 'archived-hash'
        for login in ('student4', 'student5'):
            user = db.scalar(select(User).where(User.login == login))
            assert user.group_id == group.id and PasswordHasher().verify(user.password_hash, '12345678')
        seed(db)
        assert len(list(db.scalars(select(User)))) == 5


def test_custom_classroom_does_not_get_demo_accounts():
    with database() as db:
        db.add(User(login='custom-admin', name='Администратор', role='admin', password_hash='existing'))
        db.commit()
        seed(db)
        assert [u.login for u in db.scalars(select(User))] == ['custom-admin']
