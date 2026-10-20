from test_new_student_guidance import classroom, learner
from test_flows import login, post, SessionLocal
from apps.api.app.db import Attempt


def test_drill_during_report_generation_without_pending_grade(classroom):
    name, sid = learner(0)
    login(classroom, name)
    catalog = classroom.get('/api/tutorials').json()
    attempt = post(classroom, f"/tutorials/{catalog[0]['version_id']}/start").json()
    with SessionLocal() as db:
        row = db.get(Attempt, attempt['id'])
        row.status = 'completed'
        row.assessment = {'score': 75, 'pending': False, 'report_job': {'status': 'queued'}}
        db.commit()
    question = post(classroom, f"/learning/drill/{attempt['id']}").json()
    assert question and question['prompt']
    answer = post(classroom, '/learning/drill-answer', {'id': question['id'], 'answer': 'test'})
    assert answer.status_code == 200
    with SessionLocal() as db:
        row = db.get(Attempt, attempt['id'])
        assert row.assessment['score'] == 75
        assert not row.state.get('mini_started')
        row.assessment = {**row.assessment, 'report_job': {'status': 'done'}}
        db.commit()
    assert post(classroom, f"/learning/drill/{attempt['id']}").json() is None
