"""Teacher assistant, stage 1: rule-based parsing, student resolution, rights and audit."""
import uuid
import pytest
from sqlalchemy import select
from test_flows import app, TestClient, login, post, HEAD, SessionLocal
from apps.api.app.db import User, TicketVersion, Assignment, Attempt, Audit
from apps.api.app.assistant import resolve_students, levenshtein

PASSWORD='Training112!'

def ask(c,text,dialog=None,page='/journal'):
    r=post(c,'/assistant/interpret',{'text':text,'context':{'page':page},**({'dialog':dialog} if dialog else {})})
    assert r.status_code==200,r.text
    return r.json()

@pytest.fixture(scope='module')
def classroom():
    """A separate teacher with an own group, so other tests' students never leak into name resolution."""
    tag=uuid.uuid4().hex[:8]
    with TestClient(app) as c:
        login(c,'admin')
        teacher=post(c,'/users',{'login':'assist_t_'+tag,'name':'Ирина Ассистентова','password':PASSWORD,'role':'teacher'}).json()
        gid=post(c,'/groups',{'name':'Группа ассистента '+tag,'teacher_id':teacher['id']}).json()['id']
        ids={}
        for login_name,name in [('kuz','Артём Кузнецов'),('iv1','Мария Иванова'),('iv2','Ольга Иванова'),('elk','Алёна Ёлкина')]:
            ids[login_name]=post(c,'/users',{'login':f'assist_{login_name}_{tag}','name':name,'password':PASSWORD,'role':'student','group_id':gid}).json()['id']
        ids['outside']=post(c,'/users',{'login':f'assist_out_{tag}','name':'Невидимый Петров','password':PASSWORD,'role':'student'}).json()['id']
        post(c,'/logout')
    return {'teacher':teacher['login'],'group':gid,'tag':tag,**ids}

@pytest.fixture
def teacher(classroom):
    with TestClient(app) as c:
        login(c,classroom['teacher'])
        yield c

@pytest.mark.parametrize('text,intent,to',[
    ('открой журнал','open_page','/journal'),
    ('Покажи журнал','open_page','/journal'),
    ('журнал','open_page','/journal'),
    ('открой проверку работ','open_page','/reviews'),
    ('рабочие места','open_page','/'),
    ('покажи класс','open_page','/'),
    ('открой режимы','open_page','/classroom/modes'),
    ('покажи студентов','open_page','/users'),
    ('перейди к аналитике','open_page','/analytics'),
    ('открой билеты','open_page','/tickets'),
    ('минивопросы','open_page','/learning'),
    ('открой мини вопросы','open_page','/learning'),
    ('занятия','open_page','/lessons'),
    ('покажи, какие работы нужно проверить','show_reviews','/reviews?state=review'),
    ('что нужно проверить?','show_reviews','/reviews?state=review'),
    ('Проверить работы','show_reviews','/reviews?state=review'),
    ('непроверенные работы','show_reviews','/reviews?state=review'),
])
def test_navigation_phrases(teacher,text,intent,to):
    r=ask(teacher,text)
    assert r['intent']==intent,r
    assert r['action']=={'kind':'navigate','to':to} and not r['confirm_required'],r

def test_open_group_by_voice_or_from_list(teacher,classroom):
    first=ask(teacher,'открой мне группу')
    assert first['intent']=='open_group' and first['missing'][0]['slot']=='group_id'
    assert {c['id'] for c in first['candidates']}=={classroom['group']}
    assert first['action'] is None
    chosen=ask(teacher,'Группа ассистента '+classroom['tag'],dialog={'intent':'open_group','slots':{'answer_slot':'group_id'}})
    assert chosen['action']=={'kind':'navigate','to':f'/users?group={classroom["group"]}'}
    assert 'Артём Кузнецов' in chosen['preview'] and 'Невидимый Петров' not in chosen['preview']
    clicked=ask(teacher,'Группа ассистента '+classroom['tag'],dialog={'intent':'open_group','slots':{'group_id':classroom['group'],'answer_slot':'group_id'}})
    assert clicked['action']==chosen['action']
    direct=ask(teacher,'покажи группу «Группа ассистента '+classroom['tag']+'»')
    assert direct['action']==chosen['action']

def test_video_creation_commands(teacher,classroom):
    from apps.api.app.assistant_tickets import incident_phrase, parse_create
    assert incident_phrase('Давай ДТП.')=='дтп'
    assert parse_create('Один пострадавший',[])['victims_count']==1
    question=ask(teacher,'Создай мини задание: Какие клавиши обновляют журнал? варианты Ctrl+F5; Ctrl+F2; Ctrl+F7; верный ответ Ctrl+F5')
    assert question['intent']=='create_question' and question['confirm_required'],question
    assert question['slots']['options']==['Ctrl+F5','Ctrl+F2','Ctrl+F7']
    assert question['slots']['answer']=='Ctrl+F5'
    student=ask(teacher,'Создай нового ученика')
    assert student['missing'][0]['slot']=='name'
    student=ask(teacher,'Тюрин Василий Денисович',dialog={'intent':'create_student','slots':{**student['slots'],'answer_slot':'name'}})
    assert student['confirm_required'] and student['slots']['group_id']==classroom['group']
    created=post(teacher,'/assistant/execute',{'intent':'create_student','slots':student['slots'],'confirm_token':student['confirm_token']})
    assert created.status_code==200,created.text
    assert 'Одноразовый код' in created.json()['preview'] and 'tyurin.vd' in created.json()['preview']
    assert ask(teacher,'Закрой рабочий стол')['action']=={'kind':'navigate','to':'/?close_remote=1'}
    assert ask(teacher,'Всё выходи из всех ПК')['action']=={'kind':'navigate','to':'/?close_remote=1'}
    assert ask(teacher,'Спасибо за работу, до завтра')['action']=={'kind':'logout'}

def test_assign_ticket_to_named_student(teacher,classroom,monkeypatch):
    from apps.api.app import voice
    monkeypatch.setattr(voice,'ensure_ready',lambda *args:None)
    command=ask(teacher,'Отправь билет студенту Кузнецову')
    assert command['intent']=='assign_ticket' and command['confirm_required'],command
    assert command['slots']['student_id']==classroom['kuz']
    assigned=post(teacher,'/assistant/execute',{'intent':'assign_ticket','slots':command['slots'],'confirm_token':command['confirm_token']})
    assert assigned.status_code==200,assigned.text
    assert 'Кузнецов' in assigned.json()['preview']

@pytest.mark.parametrize('text,intent',[
    ('где сидит Кузнецов','where_student'),
    ('Где Кузнецова?','where_student'),
    ('где сидит кузнецов','where_student'),
    ('где сидит Кузницов','where_student'),
    ('где сейчас Артём','where_student'),
    ('где сейчас Артем','where_student'),
    ('за каким ПК Кузнецов','where_student'),
    ('на каком рабочем месте студент Кузнецов?','where_student'),
    ('найди последнюю работу у Кузнецова','find_last_attempt'),
    ('последняя работа Кузнецова','find_last_attempt'),
    ('крайняя попытка Кузнецова','find_last_attempt'),
    ('по студенту Кузнецову есть рекомендации?','student_profile'),
    ('какие ошибки у Кузнецова','student_profile'),
    ('профиль Кузнецова','student_profile'),
    ('результаты ученика Кузнецова','student_profile'),
])
def test_student_phrases_resolve_cases_and_typos(teacher,classroom,text,intent):
    r=ask(teacher,text)
    assert r['intent']==intent,r
    assert r['slots'].get('student_id')==classroom['kuz'],r
    assert not r['candidates'] and not r['missing']

@pytest.mark.parametrize('text',['где Ёлкина','где Елкина','рекомендации Ёлкиной','последняя работа Елкиной'])
def test_yo_and_ye_are_the_same_letter(teacher,classroom,text):
    r=ask(teacher,text)
    assert r['slots'].get('student_id')==classroom['elk'],r

def test_offline_student_and_profile_text(teacher,classroom):
    r=ask(teacher,'где сидит Кузнецов')
    assert 'не в сети' in r['preview'] and r['action'] is None
    r=ask(teacher,'найди последнюю работу у Кузнецова')
    assert 'нет работ' in r['preview'] and r['action'] is None
    r=ask(teacher,'по студенту Кузнецову есть рекомендации?')
    assert 'Рекомендации' in r['preview'] and 'Артём Кузнецов' in r['preview'] and r['action']['to']==f'/users?student={classroom["kuz"]}'
    assert {'label':'Студенты','to':'/users'} in r['links'] and any(l['to']==f'/reviews?student={classroom["kuz"]}&state=completed' for l in r['links']),'reading answers keep links to open later'

def test_ambiguous_surname_offers_candidates_then_resolves(teacher,classroom):
    r=ask(teacher,'где сидит Иванова')
    assert r['intent']=='where_student' and r['action'] is None
    assert {c['id'] for c in r['candidates']}=={classroom['iv1'],classroom['iv2']}
    assert all(c['kind']=='student' and c['label'] for c in r['candidates'])
    r=ask(teacher,'где сидит Иванова',dialog={'intent':'where_student','slots':{'student_id':classroom['iv2']}})
    assert r['slots']['student_id']==classroom['iv2'] and not r['candidates'] and 'Ольга Иванова' in r['preview']
    r=ask(teacher,'где сидит Мария Иванова')
    assert r['slots']['student_id']==classroom['iv1'] and not r['candidates']

def test_unknown_or_invisible_student_is_reported(teacher,classroom):
    r=ask(teacher,'где сидит Сидоров')
    assert r['intent']=='where_student' and 'Не нашёл' in r['preview'] and not r['candidates'] and r['action'] is None
    r=ask(teacher,'где сидит Петров')
    assert 'Не нашёл' in r['preview'],'a student outside the teacher group must stay invisible'
    r=ask(teacher,'где сидит Иванова',dialog={'intent':'where_student','slots':{'student_id':classroom['outside']}})
    assert 'недоступен' in r['preview'] and not r['slots'].get('student_id')

def test_missing_student_asks_and_takes_next_message(teacher,classroom):
    r=ask(teacher,'где сидит')
    assert r['intent']=='where_student' and r['missing'] and r['missing'][0]['slot']=='student' and r['action'] is None
    r=ask(teacher,'Кузнецов',dialog={'intent':'where_student','slots':{'student_query':'Кузнецов'}})
    assert r['intent']=='where_student' and r['slots']['student_id']==classroom['kuz']

@pytest.mark.parametrize('text,intent',[
    ('что умеешь?','help'),('помощь','help'),('','help'),
    ('закрой','close'),('закрыть окно','close'),
    ('сделай кофе','unknown'),('не открывай журнал','unknown'),('можно ли открыть журнал?','unknown'),
    ('кто сейчас в классе?','who_online'),('кто в сети','who_online'),('кто подключён','who_online'),('кто не в сети','who_online'),
])
def test_service_intents(teacher,text,intent):
    r=ask(teacher,text)
    assert r['intent']==intent,r
    if intent=='close':assert r['action']=={'kind':'close'}
    else:assert r['action'] is None
    if intent=='help':assert 'журнал' in r['preview']
    if text=='не открывай журнал':assert 'ничего не делаю' in r['preview']

def test_reviews_list_last_attempt_and_audit(teacher,classroom):
    with SessionLocal() as db:
        t=db.scalar(select(User).where(User.login==classroom['teacher']))
        version=next(v for v in db.scalars(select(TicketVersion).where(TicketVersion.published==True)) if all(task.get('mode')=='dds' for task in v.data.get('tasks',[])))
        assignment=Assignment(version_id=version.id,student_id=classroom['kuz'],teacher_id=t.id,title='Работа для ассистента')
        db.add(assignment);db.flush()
        attempt=Attempt(assignment_id=assignment.id,student_id=classroom['kuz'],task_index=0,status='completed',snapshot={**version.data['tasks'][0],'title':'Карточка ассистента'},card={},state={},assessment={'score':64,'pending':False,'criteria':[],'reviews':[]})
        db.add(attempt);db.commit();attempt_id=attempt.id
    r=ask(teacher,'покажи, какие работы нужно проверить')
    assert r['slots']['count']>=1 and 'Артём Кузнецов' in r['preview'] and r['action']['to']=='/reviews?state=review'
    r=ask(teacher,'какие работы Кузнецова нужно проверить')
    assert r['slots']['student_id']==classroom['kuz'] and r['action']['to']==f'/reviews?state=review&student={classroom["kuz"]}'
    r=ask(teacher,'найди последнюю работу у Кузнецова')
    assert r['action']=={'kind':'navigate','to':f'/attempts/{attempt_id}'} and 'Карточка ассистента' in r['preview'] and 'нужна проверка' in r['preview']
    assert r['slots']['attempt_id']==attempt_id
    with SessionLocal() as db:
        rows=list(db.scalars(select(Audit).where(Audit.action=='assistant_command',Audit.actor_id==t.id).order_by(Audit.id.desc())))
        assert rows and rows[0].detail['intent']=='find_last_attempt' and rows[0].detail['student_id']==classroom['kuz'] and rows[0].detail['attempt_id']==attempt_id
        assert rows[0].detail['text']=='найди последнюю работу у Кузнецова' and rows[0].detail['page']=='/journal'

def test_where_student_reports_station_number(classroom):
    with TestClient(app) as teacher,TestClient(app) as student:
        login(teacher,'admin')
        station=post(student,'/classroom/register',{'number':'A'+uuid.uuid4().hex[:6]}).json()
        student.headers['X-Workstation']=station['token']
        assert teacher.patch('/api/classroom/stations/'+station['id'],json={'approved':True},headers=HEAD).status_code==200
        post(teacher,'/logout');login(teacher,classroom['teacher'])
        login(student,f'assist_kuz_{classroom["tag"]}')
        assert post(student,'/classroom/presence',{'sharing':False,'page':'/registry'}).status_code==200
        r=ask(teacher,'где сидит Кузнецов')
        assert r['slots']['station']==station['number'] and f'ПК №{station["number"]}' in r['preview'] and '/registry' in r['preview']
        remote=ask(teacher,'подключись к рабочему месту Артёма Кузнецова')
        assert remote['action']=={'kind':'navigate','to':'/?remote='+station['id']}
        r=ask(teacher,'кто сейчас в классе?')
        assert r['slots']['count']>=1 and 'Артём Кузнецов' in r['preview'] and station['number'] in r['preview']
        r=ask(teacher,'кто не в сети?')
        assert 'Артём Кузнецов' not in r['preview'] and 'Ольга Иванова' in r['preview']

def test_student_gets_403():
    with TestClient(app) as c:
        login(c,'student')
        assert post(c,'/assistant/interpret',{'text':'открой журнал','context':{'page':'/'}}).status_code==403


def test_navigation_interrupts_ticket_dialog(teacher):
    result=post(teacher,'/assistant/interpret',{'text':'Покажи билеты','context':{'page':'/tickets'},'dialog':{'intent':'create_ticket','slots':{'answer_slot':'incident_type','own_service':'Служба 102'}}})
    assert result.status_code==200,result.text
    assert result.json()['action']=={'kind':'navigate','to':'/tickets'}


def test_open_named_student(teacher,classroom):
    result=ask(teacher,'Открой мне студента Кузнецова')
    assert result['intent']=='student_profile'
    assert result['slots']['student_id']==classroom['kuz']

def test_resolver_stages():
    assert levenshtein('кузницов','кузнецов')==1 and levenshtein('анна','инна')==1
    with TestClient(app) as c:
        login(c,'admin')
        with SessionLocal() as db:
            admin=db.scalar(select(User).where(User.login=='admin'))
            morozov=db.scalar(select(User).where(User.login=='student'))
            assert [s.id for s in resolve_students(db,admin,'Морозов')]==[morozov.id]
            assert [s.id for s in resolve_students(db,admin,'морозова')]==[morozov.id]
            assert [s.id for s in resolve_students(db,admin,'Марозов')]==[morozov.id]
            assert [s.id for s in resolve_students(db,admin,'Алексей Морозов')]==[morozov.id]
            assert resolve_students(db,admin,'Ктототам')==[] and resolve_students(db,admin,'')==[]

def test_connect_commands_choose_a_specific_student_or_station(teacher,classroom):
    r=ask(teacher,'подключись на рабочий стол к артему кузнецован')
    assert r['intent']=='connect_student' and r['slots']['student_id']==classroom['kuz']
    assert r['action'] is None or r['action']['to'].startswith('/?remote=')
    r=ask(teacher,'подключись на первом рабочем месте')
    assert r['intent']=='connect_station' and '№1' in r['preview']
    assert ask(teacher,'покажи рабочие места')['action']=={'kind':'navigate','to':'/'}
    assert ask(teacher,'выйди с этого ПК')['action']=={'kind':'logout'}

def test_group_and_mini_question_dialogs(teacher):
    r=ask(teacher,'создай новую группу учеников')
    assert r['intent']=='create_group' and r['missing'][0]['slot']=='name'
    r=ask(teacher,'Тренировка',dialog={'intent':'create_group','slots':{**r['slots'],'answer_slot':'name'}})
    assert r['missing'][0]['slot']=='members'
    r=ask(teacher,'всех активных',dialog={'intent':'create_group','slots':{**r['slots'],'answer_slot':'members'}})
    assert r['confirm_required'] and r['slots']['student_ids']
    grouped=post(teacher,'/assistant/execute',{'intent':r['intent'],'slots':r['slots'],'confirm_token':r['confirm_token']})
    assert grouped.status_code==200,grouped.text
    q=ask(teacher,'добавь минивопрос')
    assert q['missing'][0]['slot']=='prompt'
    q=ask(teacher,'Как называется служба?',dialog={'intent':'create_question','slots':{**q['slots'],'answer_slot':'prompt'}})
    assert q['missing'][0]['slot']=='answer'
    q=ask(teacher,'ДДС',dialog={'intent':'create_question','slots':{**q['slots'],'answer_slot':'answer'}})
    assert q['missing'][0]['slot']=='audio_text'
    q=ask(teacher,'без озвучки',dialog={'intent':'create_question','slots':{**q['slots'],'answer_slot':'audio_text'}})
    assert q['confirm_required']
    saved=post(teacher,'/assistant/execute',{'intent':q['intent'],'slots':q['slots'],'confirm_token':q['confirm_token']})
    assert saved.status_code==200,saved.text
    number=saved.json()['slots']['question_id']
    edited=ask(teacher,f'отредактируй минивопрос {number}')
    assert edited['missing'][0]['slot']=='field',edited
    edited=ask(teacher,'правильный ответ',dialog={'intent':'edit_question','slots':{**edited['slots'],'answer_slot':'field'}})
    assert edited['missing'][0]['slot']=='value'
    edited=ask(teacher,'Районная ДДС',dialog={'intent':'edit_question','slots':{**edited['slots'],'answer_slot':'value'}})
    assert edited['confirm_required']
    saved=post(teacher,'/assistant/execute',{'intent':edited['intent'],'slots':edited['slots'],'confirm_token':edited['confirm_token']})
    assert saved.status_code==200,saved.text

def test_misheard_recommendation_name(teacher,classroom):
    with TestClient(app) as admin:
        login(admin,'admin')
        student=post(admin,'/users',{'login':'assist_belova_'+classroom['tag'],'name':'Анна Павловна Белова','password':PASSWORD,'role':'student','group_id':classroom['group']}).json()
    result=ask(teacher,'по студенту Беовой есть рекомендации каки?')
    assert result['intent']=='student_profile' and result['slots']['student_id']==student['id']


def test_new_voice_commands(teacher,classroom):
    assert ask(teacher,'Создай мини-задание')['intent']=='create_question'
    assert ask(teacher,'Делай как я')['action']['to']=='/classroom/modes?mode=demo'
    assert ask(teacher,'Открой Кузнецова')['action']['to']==f'/users?student={classroom["kuz"]}'


def test_assign_multiple_students(teacher,classroom,monkeypatch):
    from apps.api.app import voice
    monkeypatch.setattr(voice,'ensure_ready',lambda *args:None)
    result=ask(teacher,'Отправь билет Кузнецову и Ёлкиной')
    assert result['confirm_required'],result
    assert set(result['slots']['student_ids'])=={classroom['kuz'],classroom['elk']}
    done=post(teacher,'/assistant/execute',{'intent':result['intent'],'slots':result['slots'],'confirm_token':result['confirm_token']})
    assert done.status_code==200,done.text
    with SessionLocal() as db:
        assigned=set(db.scalars(select(Assignment.student_id).where(Assignment.version_id==result['slots']['version_id'])))
        assert {classroom['kuz'],classroom['elk']}<=assigned


def test_publish_draft_command(teacher):
    with SessionLocal() as db:
        original=next(v for v in db.scalars(select(TicketVersion)) if v.data['tasks'][0]['mode']=='dds')
        payload=dict(original.data);payload['title']='Проверка публикации '+uuid.uuid4().hex[:8]
    draft=post(teacher,'/tickets',payload)
    assert draft.status_code==200,draft.text
    version=draft.json()
    result=ask(teacher,'Сохрани и опубликуй эту карточку',page=f'/tickets/{version["id"]}')
    assert result['intent']=='publish_ticket' and result['confirm_required'],result
    done=post(teacher,'/assistant/execute',{'intent':result['intent'],'slots':result['slots'],'confirm_token':result['confirm_token']})
    assert done.status_code==200,done.text
    with SessionLocal() as db:assert db.get(TicketVersion,version['id']).published


def test_student_first_login_uses_four_digit_code(teacher,classroom):
    import re
    from argon2 import PasswordHasher
    name='Смирнов Новый '+uuid.uuid4().hex[:8]
    result=ask(teacher,name,dialog={'intent':'create_student','slots':{'answer_slot':'name','group_id':classroom['group']}})
    assert result['confirm_required'],result
    done=post(teacher,'/assistant/execute',{'intent':result['intent'],'slots':result['slots'],'confirm_token':result['confirm_token']})
    assert done.status_code==200,done.text
    payload=done.json();code=re.search(r'первого входа: (\d{4})(?:\n|$)',payload['preview']).group(1)
    with SessionLocal() as db:
        student=db.get(User,payload['slots']['student_id'])
        assert student.must_change_password and PasswordHasher().verify(student.password_hash,code)
