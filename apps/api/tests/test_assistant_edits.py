"""Teacher assistant: commands that used to collide, and ticket edits that keep the whole ticket consistent."""
import pytest
from test_flows import app, TestClient, login, post

STORY='В подъезде жилого дома густой дым. Дом газифицирован.'

def ask(c,text,dialog=None,page='/tickets'):
    r=post(c,'/assistant/interpret',{'text':text,'context':{'page':page},**({'dialog':dialog} if dialog else {})})
    assert r.status_code==200,r.text
    return r.json()

def follow(c,r,text='',page='/tickets',**slots):
    missing=r['missing'][0]['slot'] if r['missing'] else None
    answer=next(iter(slots)) if slots else missing if text else None
    return ask(c,text,{'intent':r['intent'],'slots':{**r['slots'],**slots,**({'answer_slot':answer} if answer else {})}},page)

def run(c,r):
    response=post(c,'/assistant/execute',{'intent':r['intent'],'slots':r['slots'],'confirm_token':r['confirm_token']})
    assert response.status_code==200,response.text
    return response.json()

def saved(c,done):
    vid=int(done['action']['to'].split('/')[2].split('?')[0])
    return next(v for v in c.get('/api/tickets').json() if v['id']==vid)

@pytest.fixture
def teacher(monkeypatch):
    from apps.api.app import scenario_wizard, assistant_tickets, assistant
    monkeypatch.setattr(scenario_wizard,'complete',lambda *a,**kw:({'description':STORY},{'model':'test'}))
    def no_model(*a,**kw):raise RuntimeError('Локальная модель не установлена')
    monkeypatch.setattr(assistant_tickets,'complete',no_model)
    monkeypatch.setattr(assistant,'station_rows',lambda u,db:[])
    with TestClient(app) as c:
        login(c,'teacher')
        yield c

def dds_ticket(c,victims='Пострадавших людей нет.'):
    """A DDS draft of our own whose card speaks about casualties in its texts."""
    source=next(v for v in c.get('/api/tickets').json() if v['published'] and not v['archived'] and v['data']['tasks'][0]['mode']=='dds')
    data=source['data'];task=data['tasks'][0];card=task['initial_card']
    card.update(victims='no',victims_count='',description='В подвале течёт вода из трубы. '+victims,name='Елена Андреевна Соколова')
    task['intro']=f'Получена карточка. В подвале течёт вода из трубы. {victims}'
    for contact in task.get('contacts',[]):
        if contact.get('kind')=='caller':contact['name']='Елена Андреевна Соколова';contact['response']=f'Меня зовут Елена Андреевна Соколова. {victims}'
    data['title']=card.get('incident_type','')+': тестовый билет'
    r=post(c,'/tickets',data);assert r.status_code==200,r.text
    return next(v for v in c.get('/api/tickets').json() if v['id']==r.json()['id'])

@pytest.mark.parametrize('text,intent',[
    ('разлогинь всех учеников','exit_all'),('выйди','exit_pc'),('какие есть команды','help'),
    ('подключись к Морозову','connect_student'),('покажи экран Морозова','connect_student'),('посмотри что делает Морозов','connect_student'),
    ('покажи мой экран ученикам','demo_mode'),('включи трансляцию экрана','demo_mode'),
])
def test_commands_that_used_to_collide(teacher,text,intent):
    r=ask(teacher,text)
    assert r['intent']==intent or (intent=='connect_student' and r['intent']=='connect_student'),r
    if intent=='exit_all':assert r['action']!={'kind':'logout'},'the teacher stays signed in'

def test_cancel_inside_the_questions_keeps_the_window(teacher):
    r=ask(teacher,'создай билет')
    assert r['missing']
    cancelled=follow(teacher,r,'отмена')
    assert cancelled['intent']=='cancel' and cancelled['action'] is None and not cancelled['missing']
    assert ask(teacher,'отмена')['action']=={'kind':'close'},'without a dialog «отмена» still closes the window'

def test_victims_change_rewrites_the_story_and_adds_ambulance(teacher):
    v=dds_ticket(teacher)
    r=ask(teacher,f'в билете {v["ticket_id"]} трое пострадавших')
    assert r['confirm_required'] and r['slots']['value']=='yes:3'
    new=saved(teacher,run(teacher,r))['data'];task=new['tasks'][0];card=task['initial_card']
    assert card['victims']=='yes' and card['victims_count']=='3'
    assert 'Пострадавших людей: 3.' in card['description'] and 'нет' not in card['description']
    assert 'Пострадавших людей: 3.' in task['intro'] and 'Пострадавших людей нет' not in str(task)
    assert 'Есть пострадавшие' in task['traits'] and 'Служба 103' in task['services']
    r=ask(teacher,'поменяй количество пострадавших на 4',page=f'/tickets/{new_id(teacher,v)}')
    assert r['intent']=='edit_ticket' and r['slots']['value']=='yes:4',r

def new_id(c,v):
    return max(x['id'] for x in c.get('/api/tickets').json() if x['ticket_id']==v['ticket_id'])

def test_house_caller_type_and_relative_difficulty(teacher):
    v=dds_ticket(teacher);page=f'/tickets/{v["id"]}'
    street=v['data']['tasks'][0]['initial_card']['street']
    r=ask(teacher,'поменяй дом на 7',page=page)
    assert r['intent']=='edit_ticket' and r['slots']['value']=={'house':'7'} and r['confirm_required'],r
    task=saved(teacher,run(teacher,r))['data']['tasks'][0]
    assert task['initial_card']['house']=='7' and task['initial_card']['street']==street
    page=f'/tickets/{new_id(teacher,v)}'
    r=ask(teacher,'поменяй заявителя на Ивана Петрова',page=page)
    assert r['slots']['value']=='Иван Петров' and 'Елена Андреевна Соколова → Иван Петров' in r['preview'],r
    task=saved(teacher,run(teacher,r))['data']['tasks'][0]
    assert task['initial_card']['name']=='Иван Петров' and 'Елена Андреевна' not in str(task)
    assert ask(teacher,'заявитель — Анна Белова',page=f'/tickets/{new_id(teacher,v)}')['slots']['value']=='Анна Белова'
    assert ask(teacher,'поменяй заявителя на Анну Соколову',page=f'/tickets/{new_id(teacher,v)}')['slots']['value']=='Анна Соколова'
    r=ask(teacher,'поменяй тип происшествия на пожар',page=f'/tickets/{new_id(teacher,v)}')
    assert r['slots']['value']=='пожар' and r['confirm_required'],r
    new=saved(teacher,run(teacher,r))['data'];task=new['tasks'][0]
    assert task['initial_card']['incident_type']=='пожар' and task['type_options']==['пожар'] and new['title'].startswith('пожар')
    r=ask(teacher,'тип происшествия пожар в подъезде',page=f'/tickets/{new_id(teacher,v)}')
    assert r['missing'] and r['missing'][0]['slot']=='value' and any(o['value']=='пожар: подъезд' for o in r['missing'][0]['options']),r
    stars=new.get('difficulty_stars') or 1
    r=ask(teacher,'сделай сложнее',page=f'/tickets/{new_id(teacher,v)}')
    if stars<5:assert r['confirm_required'] and r['slots']['value']==stars+1,r
    else:assert 'наибольшая' in r['preview']

def test_mode_change_rebuilds_the_ticket(teacher):
    v=dds_ticket(teacher);page=f'/tickets/{v["id"]}'
    r=ask(teacher,'поменяй режим на 112',page=page)
    assert r['intent']=='edit_ticket' and 'выключен' in r['preview'] and not r['confirm_required'],'112 is off by default'
    login(teacher,'admin');post(teacher,'/management/training-modes',{'operator112':True});login(teacher,'teacher')
    try:
        r=ask(teacher,'поменяй режим на 112',page=page)
        assert r['confirm_required'] and r['slots']['value']=='112' and 'пересобрано' in r['preview'],r
        new=saved(teacher,run(teacher,r))['data'];task=new['tasks'][0]
        card=task['expected_card']
        assert task['mode']=='112' and new['title']==v['data']['title']
        assert card['name']=='Елена Андреевна Соколова' and card['street']==v['data']['tasks'][0]['initial_card']['street']
        assert any(q['id']=='address' for q in task['questions'])
        assert 'Билет уже' in ask(teacher,'режим 112',page=f'/tickets/{new_id(teacher,v)}')['preview']
    finally:
        login(teacher,'admin');post(teacher,'/management/training-modes',{'operator112':False});login(teacher,'teacher')
