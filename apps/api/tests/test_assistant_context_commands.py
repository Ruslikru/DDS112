import pytest
from sqlalchemy import select
from test_new_student_guidance import classroom,learner
from test_flows import login,post,SessionLocal
from apps.api.app.db import User,Group,TicketVersion,Assignment
from apps.api.app.dds_flow import create_attempt


def ask(c,text,dialog=None):
    r=post(c,'/assistant/interpret',{'text':text,'context':{'page':'/'},**({'dialog':dialog} if dialog else {})})
    assert r.status_code==200,r.text
    return r.json()


def test_journal_in_question_is_not_navigation(classroom):
    login(classroom,'teacher')
    r=ask(classroom,'Создай минивопрос')
    r=ask(classroom,'Каким сочетанием клавиш обновляется список происшествий журнал?',{'intent':r['intent'],'slots':{**r['slots'],'answer_slot':'prompt'}})
    assert r['intent']=='create_question' and r['missing'][0]['slot']=='answer'
    assert 'журнал' in r['slots']['prompt'] and not r.get('action')


@pytest.mark.parametrize('phrase',['Английскими символами КТРЛ + F5','КСонтрол плюс F5','контрол плюс эф пять','Ctrl + F5','контроль шифт эф пять'])
def test_dictated_shortcut(phrase):
    from apps.api.app.assistant import clean_speech,normalize_shortcut
    assert normalize_shortcut(clean_speech(phrase))==('Ctrl + Shift + F5' if 'шифт' in phrase else 'Ctrl + F5')


@pytest.fixture
def kuznetsov(classroom):
    _,sid=learner(3)
    with SessionLocal() as db:
        teacher=db.scalar(select(User).where(User.login=='teacher'))
        user=db.get(User,sid);user.name='Артём Игоревич Кузнецов'
        user.group_id=db.scalar(select(Group.id).where(Group.teacher_id==teacher.id))
        version=next(v for v in db.scalars(select(TicketVersion)) if v.data['tasks'][0].get('id')=='practice-water-v1')
        assignment=Assignment(version_id=version.id,student_id=sid,teacher_id=teacher.id,title=version.data['title'],training=True)
        db.add(assignment);db.flush()
        attempt=create_attempt(db,assignment,version.data['tasks'][0],0)
        attempt.status='completed';attempt.assessment={'score':100,'criteria':[],'pending':False,'reviews':[],'report_job':{'status':'done'}}
        db.commit();aid=attempt.id
    login(classroom,'teacher')
    yield sid,aid
    with SessionLocal() as db:
        user=db.get(User,sid);user.name='Finished context test '+str(sid);db.commit()


@pytest.mark.parametrize('phrase',['Проверить работу Кузнецова','Нужна проверка Кузнецов','Открой проверку работы Кузнецова'])
def test_named_review_opens_the_result(classroom,kuznetsov,phrase):
    sid,aid=kuznetsov;r=ask(classroom,phrase)
    assert r['intent']=='student_review' and r['slots']['student_id']==sid
    assert 'attempt='+str(aid) in r['action']['to'] and 'student='+str(sid) in r['action']['to']


@pytest.mark.parametrize('phrase',['Статистика Кузнецова','Аналитика Кузнецов','Как учится Кузнецов?'])
def test_named_statistics_open_profile(classroom,kuznetsov,phrase):
    sid,_=kuznetsov;r=ask(classroom,phrase)
    assert r['intent']=='student_profile' and r['action']['to']=='/users?student='+str(sid)


def test_profile_followup_name(classroom,kuznetsov):
    sid,_=kuznetsov;r=ask(classroom,'Проблемы у студента')
    assert r['missing'][0]['slot']=='student'
    r=ask(classroom,'Кузнецов',{'intent':r['intent'],'slots':{**r['slots'],'answer_slot':'student'}})
    assert r['slots']['student_id']==sid


def test_close_workplace_synonym(classroom):
    login(classroom,'teacher');r=ask(classroom,'Закрой рабочее место')
    assert r['intent']=='close_desktop' and r['action']['to']=='/?close_remote=1'
