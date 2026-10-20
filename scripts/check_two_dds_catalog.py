import os
from pathlib import Path
import sys
import tempfile
import uuid
import wave
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
folder = Path(tempfile.mkdtemp(prefix='two-dds-check-'))
os.environ.update(DATA_DIR=str(folder), DATABASE_URL='sqlite:///' + (folder / 'check.db').as_posix(),
                  TRAINING_CATALOG='two-dds', DEMO_CLASSROOM='1', DEMO_PASSWORD='Training112!',
                  VOICE_AUTO_GENERATE='false', AI_AUTO_REVIEW='false', ENFORCE_SERVER_NAME='0')

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from apps.api.app.main import app
from apps.api.app.db import Assignment, Lesson, SessionLocal, Ticket, TicketVersion, User
from apps.api.app.seed import sample_tasks
from apps.api.app.test_catalog import TITLES
from apps.api.app import voice

HEADERS = {'X-Requested-With': 'Training112'}


def sound(*args):
    file = folder / ('speech-' + uuid.uuid4().hex + '.wav')
    with wave.open(str(file), 'wb') as output:
        output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\0\0' * 240)
    return file, {'duration': .01, 'voice': 'fixture', 'seconds': 0}


def post(client, path, body):
    response = client.post(path, json=body, headers=HEADERS)
    assert response.status_code == 200, (path, response.status_code, response.text)
    return response.json()


with patch.object(voice.runtime, 'synthesize', sound), TestClient(app) as client:
    for index in range(1000):
        with SessionLocal() as db:
            if not db.scalar(select(voice.VoiceJob).where(voice.VoiceJob.status == 'pending')):
                break
        voice.generate_one()
    post(client, '/api/login', {'login': 'admin', 'password': 'Training112!'})
    tickets = client.get('/api/tickets').json()
    assert len(tickets) == 2
    assert {ticket['data']['title'] for ticket in tickets} == set(TITLES)
    assert all(task['mode'] == 'dds' for ticket in tickets for task in ticket['data']['tasks'])
    assert client.get('/api/tutorials').json() == []
    for ticket in tickets:
        preview = post(client, f"/api/tickets/{ticket['id']}/try", {})
        assert preview['task']['mode'] == 'dds'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Ticket)) == 2
        admin = db.scalar(select(User).where(User.login == 'admin'))
        student = db.scalar(select(User).where(User.login == 'student'))
        student_id = student.id
        for learner in db.scalars(select(User).where(User.role == 'student')):
            versions = db.scalars(select(TicketVersion).join(Assignment, Assignment.version_id == TicketVersion.id).where(Assignment.student_id == learner.id)).all()
            assert {version.data['title'] for version in versions} == set(TITLES)
        legacy = Ticket(title='Старый билет 112', created_by=admin.id)
        db.add(legacy)
        db.flush()
        version = TicketVersion(ticket_id=legacy.id, number=1, published=True, data={'title': legacy.title, 'tasks': [sample_tasks()[0]]})
        db.add(version)
        db.flush()
        assignment = Assignment(version_id=version.id, student_id=student.id, teacher_id=admin.id, title=legacy.title)
        db.add(assignment)
        legacy_lesson = Lesson(teacher_id=admin.id, title='Старое занятие 112', config={'students': [student.id], 'versions': [version.id]})
        db.add(legacy_lesson)
        db.flush()
        db.add(Assignment(version_id=version.id, lesson_id=legacy_lesson.id, student_id=student.id, teacher_id=admin.id, title=legacy.title))
        db.commit()
        legacy_version_id, legacy_assignment_id, legacy_lesson_id = version.id, assignment.id, legacy_lesson.id
    assert len(client.get('/api/tickets').json()) == 2
    assert client.post(f'/api/tickets/{legacy_version_id}/try', json={}, headers=HEADERS).status_code == 400
    assert client.post(f'/api/lessons/{legacy_lesson_id}/start', json={}, headers=HEADERS).status_code == 400
    lesson = post(client, '/api/lessons', {'title': 'Подбор двух ДДС', 'students': [student_id], 'delivery_mode': 'adaptive'})
    with SessionLocal() as db:
        selected = db.get(Lesson, lesson['id']).config['versions']
        assert len(selected) == 2 and legacy_version_id not in selected
    post(client, '/api/login', {'login': 'student', 'password': 'Training112!'})
    assignments = client.get('/api/assignments').json()
    assert all(task['mode'] == 'dds' for assignment in assignments for task in assignment['tasks'])
    assert legacy_assignment_id not in [assignment['id'] for assignment in assignments]
    assert client.post(f'/api/assignments/{legacy_assignment_id}/start', json={}, headers=HEADERS).status_code == 400
    with SessionLocal() as db:
        assert db.get(TicketVersion, legacy_version_id) is not None
        assert db.get(Assignment, legacy_assignment_id) is not None
    post(client, '/api/login', {'login': 'admin', 'password': 'Training112!'})
    os.environ['TRAINING_CATALOG'] = 'full'
    assert len(client.get('/api/tickets').json()) == 2
    post(client, '/api/management/training-modes', {'operator112': True})
    assert len(client.get('/api/tickets').json()) == 3
print('PASS: fresh database has 2 DDS tickets; both preview; demo assignments; old data preserved and hidden; adaptive selection; full-mode switch')
