import time
import uuid
from test_flows import app, TestClient, login, post, SessionLocal
from apps.api.app.db import Attempt
from apps.api.app.classroom_models import TrainingProfile


def test_mini_questions_rotate_before_work_and_during_analysis():
    with TestClient(app) as client:
        login(client, 'student')
        ticket = next(t for t in client.get('/api/tutorials').json() if t['mode'] == 'dds')
        attempt = post(client, f"/tutorials/{ticket['version_id']}/start").json()
        attempt_id = attempt['id']
        with SessionLocal() as db:
            row = db.get(Attempt, attempt_id)
            row.snapshot = {**row.snapshot, 'onboarding': None}
            profile = db.get(TrainingProfile, row.student_id)
            if profile:
                profile.data = {**profile.data, 'pending_drill': None, 'drill_offered': [], 'drills': []}
            db.commit()

        first = post(client, f'/learning/drill/{attempt_id}').json()
        assert first and 'answer' not in first
        assert post(client, f'/learning/drill/{attempt_id}').json() == first
        with SessionLocal() as db:
            row = db.get(Attempt, attempt_id)
            row.state = {**row.state, 'mini_started': time.time() - 10}
            db.commit()
        latest = client.get(f'/api/attempts/{attempt_id}').json()
        blocked = post(client, f'/attempts/{attempt_id}/command', {
            'command_id': uuid.uuid4().hex, 'revision': latest['revision'],
            'type': 'status', 'payload': {'status': 'Принята'},
        })
        assert blocked.status_code == 400
        assert post(client, '/learning/drill-answer', {'id': first['id'], 'answer': 'проверка'}).status_code == 200
        resumed = client.get(f'/api/attempts/{attempt_id}').json()
        assert resumed['state']['paused_seconds'] >= 10
        assert 'mini_started' not in resumed['state']
        assert post(client, f'/learning/drill/{attempt_id}').json() is None

        with SessionLocal() as db:
            row = db.get(Attempt, attempt_id)
            row.status = 'completed'
            row.assessment = {'pending': True}
            db.commit()
        during_analysis = post(client, f'/learning/drill/{attempt_id}').json()
        assert during_analysis and during_analysis['id'] != first['id']
        post(client, '/learning/drill-answer', {'id': during_analysis['id'], 'answer': 'проверка'})
        next_question = post(client, f'/learning/drill/{attempt_id}').json()
        assert next_question and next_question['id'] != during_analysis['id']
        post(client, '/learning/drill-answer', {'id': next_question['id'], 'answer': 'проверка'})

        with SessionLocal() as db:
            row = db.get(Attempt, attempt_id)
            row.assessment = {'pending': False, 'score': 100}
            db.commit()
        assert post(client, f'/learning/drill/{attempt_id}').json() is None


def test_student_microphone_uses_gigaam(monkeypatch):
    from apps.api.app import voice
    calls = []
    def recognize(audio, **kwargs):
        calls.append(kwargs)
        return {'text': 'Диспетчер на связи'}
    monkeypatch.setattr(voice.runtime, 'transcribe', recognize)
    with TestClient(app) as client:
        login(client, 'student')
        response = post(client, '/voice/transcribe', {'audio': 'dGVzdA=='})
        assert response.status_code == 200, response.text
        assert response.json()['text'] == 'Диспетчер на связи'
        assert calls[0]['model'] == 'gigaam'
