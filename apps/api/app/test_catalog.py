import os

from sqlalchemy import select


TITLES = ('ДДС · взаимодействие с бригадой', 'ДДС: карточка вне зоны обслуживания')


def enabled():
    return os.getenv('TRAINING_CATALOG', 'two-dds') != 'full'


def available(data):
    if not enabled():
        return True
    tasks = data.get('tasks', [])
    return bool(tasks) and all(task.get('mode') == 'dds' and task.get('title') in TITLES for task in tasks)


def versions(values):
    seen = set()
    for version in values:
        if not available(version.data):
            continue
        if enabled():
            if version.data.get('description') == 'Снимок занятия':
                continue
            title = version.data.get('title')
            if title not in TITLES or title in seen:
                continue
            seen.add(title)
        yield version


def ensure_demo_assignments(db):
    from .db import Assignment, Group, TicketVersion, User
    selected = list(versions(db.scalars(select(TicketVersion).where(TicketVersion.published == True).order_by(TicketVersion.id.desc()))))
    owner = db.scalar(select(User).where(User.login == 'admin'))
    if not owner:
        return
    for student in db.scalars(select(User).where(User.role == 'student', User.active == True, User.deleted_at == None)):
        group = db.get(Group, student.group_id) if student.group_id else None
        teacher_id = group.teacher_id if group and group.teacher_id else owner.id
        for version in selected:
            exists = db.scalar(select(Assignment.id).where(Assignment.student_id == student.id, Assignment.version_id == version.id, Assignment.lesson_id == None))
            if not exists:
                db.add(Assignment(version_id=version.id, student_id=student.id, teacher_id=teacher_id,
                                  title=version.data['title'], training=True))
    db.commit()
