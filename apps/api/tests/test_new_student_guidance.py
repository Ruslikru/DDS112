import uuid
import pytest
from test_flows import app,TestClient,login,post,command,SessionLocal
from apps.api.app.db import User,Assignment,TicketVersion
from apps.api.app.classroom_models import TrainingProfile
from sqlalchemy import select

@pytest.fixture
def classroom(monkeypatch):
    from local_ai.voice import VoiceRuntime
    from local_ai.engine import LocalEngine
    monkeypatch.setattr(VoiceRuntime,'warm',lambda self:{})
    monkeypatch.setattr(VoiceRuntime,'warm_pre',lambda self:None)
    monkeypatch.setattr(LocalEngine,'start',lambda self:None)
    with TestClient(app) as client:yield client

def learner(level):
    from argon2 import PasswordHasher
    with SessionLocal() as db:
        name='guidance-'+uuid.uuid4().hex[:10]
        user=User(login=name,name=name,role='student',active=True,password_hash=PasswordHasher().hash('Training112!'))
        db.add(user);db.flush()
        db.add(TrainingProfile(user_id=user.id,data={'demo_level':level,'intro_complete':False}))
        db.commit();return name,user.id

def test_experienced_student_has_no_automatic_introduction(classroom):
    name,sid=learner(3);login(classroom,name)
    profile=classroom.get('/api/learning/profile').json()
    assert not profile['needs_intro'] and not profile['needs_onboarding'] and profile['intro_complete']
    assert len(classroom.get('/api/tutorials').json())==2  # Available in the repeat-introduction tab.
    with SessionLocal() as db:
        version=next(v for v in db.scalars(select(TicketVersion)) if v.data['tasks'][0].get('onboarding'))
        owner=db.scalar(select(User).where(User.login=='teacher'))
        assignment=Assignment(version_id=version.id,student_id=sid,teacher_id=owner.id,title='Ordinary task',training=True)
        db.add(assignment);db.commit();aid=assignment.id
    result=post(classroom,f'/assignments/{aid}/start',{'task_index':0})
    assert result.status_code==200,result.text
    assert not result.json()['state'].get('guided')

def test_new_student_has_ready_greeting_and_can_contact_brigade(classroom,monkeypatch):
    from apps.api.app import voice
    name,sid=learner(0);login(classroom,name)
    assert classroom.get('/api/learning/profile').json()['needs_intro']
    catalog=classroom.get('/api/tutorials').json();assert len(catalog)==2
    assert all(t['voice']['ready'] for t in catalog)
    monkeypatch.setattr(voice.runtime,'synthesize',lambda *a,**kw:pytest.fail('Built-in tickets must not generate speech at runtime'))
    result=post(classroom,f"/tutorials/{catalog[0]['version_id']}/start")
    assert result.status_code==200,result.text
    attempt=result.json();assert attempt['state']['guided']
    assert post(classroom,f"/learning/drill/{attempt['id']}").json() is None
    greeting=attempt['task']['contacts'][0]['greeting_audio'];assert greeting
    assert classroom.get('/api/media/'+greeting).content.startswith(b'RIFF')
    attempt=command(classroom,attempt,'status',{'status':'Принята','comment':'Принято'})
    attempt=command(classroom,attempt,'contact',{'id':'brigade','text':'Передаю заявку по указанному адресу'})
    assert attempt['state']['contact_counts']['brigade']==1
    assert any(m.get('audio') for m in attempt['state']['messages'])

def test_invalid_recording_has_human_readable_error(classroom,monkeypatch):
    from apps.api.app import voice
    login(classroom,'student')
    def fail(*a,**kw):raise RuntimeError("[Errno 541478725] End of file: C:/private/file.webm")
    monkeypatch.setattr(voice.runtime,'transcribe',fail)
    result=post(classroom,'/voice/transcribe',{'audio':'AAAA'})
    assert result.status_code==400
    assert 'Удерживайте' in result.json()['detail'] and 'private' not in result.text


def test_first_two_demo_accounts_start_as_novices(classroom):
    from apps.api.app.demo_learning import seed_demo_learning
    from apps.api.app.learning import onboarding_needed
    with SessionLocal() as db:
        for n in range(1,4):
            user=db.scalar(select(User).where(User.login==f'student{n}'))
            if not user:
                user=User(login=f'student{n}',name=f'Student {n}',role='student',password_hash='unused')
                db.add(user);db.flush()
            profile=db.get(TrainingProfile,user.id)
            if not profile:profile=TrainingProfile(user_id=user.id,data={});db.add(profile)
            profile.data={'demo_learning_v1':True,'demo_level':n-1,'intro_complete':n>1}
        db.commit()
        seed_demo_learning(db)
        for n in range(1,4):
            user=db.scalar(select(User).where(User.login==f'student{n}'))
            assert onboarding_needed(db,user.id)==(n<=2)


def test_practice_workplace_is_visible_to_student(classroom):
    from apps.api.app import practice_library
    from apps.api.app.main import attempt_view
    from apps.api.app.dds_flow import create_attempt
    name,sid=learner(3)
    with SessionLocal() as db:
        practice_library.seed(db)
        version=next(v for v in db.scalars(select(TicketVersion)) if v.data['tasks'][0].get('id')=='practice-referral-v1')
        owner=db.scalar(select(User).where(User.login=='admin'))
        assignment=Assignment(version_id=version.id,student_id=sid,teacher_id=owner.id,title='Practice',training=True)
        db.add(assignment);db.flush()
        attempt=create_attempt(db,assignment,version.data['tasks'][0],0);db.commit()
        view=attempt_view(attempt,db.get(User,sid))
        workplace=view['task']['workplace']
        assert 'Район-Сервис' in workplace['organization']
        assert 'Хорошёво-Мнёвники' in workplace['district']
        assert 'д. 41' in workplace['coverage']
        assert 'д. 43' in workplace['directory'] and 'Северный квартал' in workplace['directory']
        assert 'criteria' not in view['task']
