import hashlib,uuid
from sqlalchemy import select
from test_new_student_guidance import classroom,learner
from test_flows import login,post,command,SessionLocal
from apps.api.app.db import User,Assignment,TicketVersion,Attempt,Group
from apps.api.app.classroom_models import Workstation


def test_binary_audio_requires_and_accepts_workstation_identity(classroom,monkeypatch):
    from apps.api.app import call_audio
    login(classroom,'student')
    token=uuid.uuid4().hex
    with SessionLocal() as db:
        db.add(Workstation(id=token,number='audio-'+token[:8],secret_hash=hashlib.sha256(token.encode()).hexdigest(),approved=True))
        db.commit()
    monkeypatch.setenv('ENFORCE_WORKSTATIONS','1')
    row=call_audio.asset('ringback')
    assert classroom.get(row['url']).status_code==403
    response=classroom.get(row['url'],headers={'X-Workstation':token})
    assert response.status_code==200
    assert hashlib.sha256(response.content).hexdigest()==row['sha256']
    assert classroom.get(row['url'],headers={'X-Workstation':'invalid'}).status_code==403


def test_two_practice_cases_are_separate_and_can_be_assigned_to_a_beginner(classroom):
    name,sid=learner(0)
    with SessionLocal() as db:
        teacher=db.scalar(select(User).where(User.login=='teacher'))
        db.get(User,sid).group_id=db.scalar(select(Group.id).where(Group.teacher_id==teacher.id))
        db.commit()
    login(classroom,'teacher')
    library=classroom.get('/api/tickets').json()
    assert all(not any(t.get('onboarding') for t in v['data']['tasks']) for v in library)
    from apps.api.app.test_catalog import TITLES
    practice=[v for v in library if v['published'] and v['data']['title'] in TITLES and v['data']['tasks'][0]['id'].startswith('practice-')]
    assert len(practice)==2
    assert all(v['voice']['ready'] for v in practice)
    assert all(len(v['data']['tasks'][0]['criteria'])>=4 for v in practice)
    version=practice[0]['id']
    response=post(classroom,'/assignments',{'version_id':version,'students':[sid],'training':True})
    assert response.status_code==200,response.text
    login(classroom,name)
    assert classroom.get('/api/learning/profile').json()['needs_onboarding']
    rows=classroom.get('/api/assignments').json()
    assignment=next(a for a in rows if not a['tasks'][0]['onboarding'])
    attempt=post(classroom,f"/assignments/{assignment['id']}/start",{'task_index':0}).json()
    assert not attempt['state'].get('guided')
    assert classroom.get('/api/learning/profile').json()['needs_onboarding']
    greeting=attempt['task']['contacts'][0]['greeting_audio']
    token=uuid.uuid4().hex
    with SessionLocal() as db:
        db.add(Workstation(id=token,number='speech-'+token[:8],secret_hash=hashlib.sha256(token.encode()).hexdigest(),approved=True))
        db.commit()
    assert classroom.get('/api/media/'+greeting,headers={'X-Workstation':token}).status_code==200
    assert attempt['task']['id']=='practice-referral-v1'
    attempt=command(classroom,attempt,'contact',{'id':'receiving-dispatcher','text':'Передаю отключение электроснабжения: Маршала Тухачевского, 43, корпус 2, первый подъезд. Дыма и пострадавших нет.'})
    assert attempt['state']['messages'][-1]['audio']
    attempt=command(classroom,attempt,'status',{'status':'Не принята','comment':'Дом вне зоны обслуживания. Заявку принял диспетчер УК «Северный квартал», номер 214. Электрик направлен.'})
    attempt=command(classroom,attempt,'finish')
    assert attempt['status']=='completed'
    assert all(c['passed'] for c in attempt['assessment']['criteria'] if c['kind'] in ('contact','status'))


def test_completing_both_introductions_removes_main_intro_block(classroom):
    name,sid=learner(0);login(classroom,name)
    catalog=classroom.get('/api/tutorials').json()
    for index,tutorial in enumerate(catalog):
        attempt=post(classroom,f"/tutorials/{tutorial['version_id']}/start").json()
        attempt=command(classroom,attempt,'status',{'status':'Принята','comment':'Карточка принята.'})
        attempt=command(classroom,attempt,'contact',{'id':'brigade','text':'Передаю адрес и описание происшествия.'})
        for status in ['Начало реагирования','Прибытие','Проведение работ','Работы завершены']:
            attempt=command(classroom,attempt,'status',{'status':status,'comment':{'Начало реагирования':'Бригада выехала.','Прибытие':'Бригада прибыла на место.','Проведение работ':'Бригада выполняет работы.','Работы завершены':'Утечка устранена. Работы завершены.'}[status]})
        attempt=command(classroom,attempt,'finish')
        assert attempt['status']=='completed'
        assert classroom.get('/api/learning/profile').json()['needs_onboarding']==(index==0)
    assert len(classroom.get('/api/tutorials').json())==2  # Repeat tab stays available.
