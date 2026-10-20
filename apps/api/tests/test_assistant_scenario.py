"""The demonstration script of 20 October run through the assistant: create a ticket, send it at once,
a dictated mini question, the review queue in conversational words, «делай как я» for a named student."""
import pytest
from test_flows import app, TestClient, login, post

STORY='В подъезде жилого дома густой дым. Дом газифицирован.'

def ask(c,text,dialog=None,**context):
    r=post(c,'/assistant/interpret',{'text':text,'context':{'page':'/',**context},**({'dialog':dialog} if dialog else {})})
    assert r.status_code==200,r.text
    return r.json()

def run(c,r):
    response=post(c,'/assistant/execute',{'intent':r['intent'],'slots':r['slots'],'confirm_token':r['confirm_token']})
    assert response.status_code==200,response.text
    return response.json()

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

def student_id(c,name):
    return next(s['id'] for s in c.get('/api/teacher/students').json() if name in s['name'])

def test_dictated_mini_question_with_quotes_and_brackets(teacher):
    r=ask(teacher,'создай мини задание: "какие горячие клавиши нужно нажимать для обновления списка журнала и варианты (Ctrl + f5; Ctrl + f2; Ctrl + f7) верный ответ Ctrl + f5"')
    assert r['intent']=='create_question' and r['confirm_required'],r
    assert r['slots']['prompt']=='какие горячие клавиши нужно нажимать для обновления списка журнала'
    assert r['slots']['options']==['Ctrl + f5','Ctrl + f2','Ctrl + f7'] and r['slots']['answer']=='Ctrl + f5'
    assert run(teacher,r)['slots']['question_id']

def test_review_queue_in_conversational_words(teacher):
    r=ask(teacher,'давай проверим работы, что у нас там в очереди')
    assert r['intent']=='show_reviews' and 'Не нашёл' not in r['preview'] and r['action']['to'].startswith('/reviews')

def test_created_draft_is_published_and_sent_in_one_confirmation(teacher):
    source=next(v for v in teacher.get('/api/tickets').json() if v['published'] and not v['archived'] and all(t.get('id')=='practice-water-v1' for t in v['data']['tasks']))
    draft=post(teacher,'/tickets',{**source['data'],'title':'Черновик для отправки'});assert draft.status_code==200,draft.text
    version=draft.json()['id']
    r=ask(teacher,'Отправь билет Морозову',version_id=version)
    assert r['intent']=='assign_ticket' and r['slots']['version_id']==version and r['slots']['publish_first'],r
    assert 'Черновик для отправки' in r['preview'] and 'черновик' in r['preview']
    done=run(teacher,r)
    assert 'отправлен' in done['preview']
    saved=next(v for v in teacher.get('/api/tickets').json() if v['id']==version)
    assert saved['published']
    r=ask(teacher,f'Отправь билет {source["ticket_id"]} Морозову',version_id=version)
    assert r['slots']['ticket_id']==source['ticket_id'],'a named ticket wins over the context'

def test_demo_mode_for_a_named_student(teacher):
    sid=student_id(teacher,'Морозов')
    r=ask(teacher,'запусти режим «делай как я» для ученика Морозов')
    assert r['intent']=='demo_mode' and r['action']['to']==f'/classroom/modes?mode=demo&students={sid}'
    assert 'не в сети' in r['preview']
    assert ask(teacher,'делай как я')['action']['to']=='/classroom/modes?mode=demo'

def test_incident_answer_gives_scene_and_service(teacher):
    r=ask(teacher,'создай мне новый билет')
    r=ask(teacher,'Пожар в подъезде жилого дома. Двое пострадавших',{'intent':r['intent'],'slots':{**r['slots'],'answer_slot':'incident_type'}})
    titles=[x['id'] for x in r['candidates']]
    assert titles and titles[0]=='пожар: подъезд',titles
    assert r['slots']['story']['seed'].startswith('Пожар в подъезде жилого дома')
    r=ask(teacher,'пожар: подъезд',{'intent':r['intent'],'slots':{**r['slots'],'incident_type':'пожар: подъезд','answer_slot':'incident_type'}})
    assert r['slots']['own_service']=='Служба 101' and r['missing'][0]['slot']=='difficulty',r

def test_ticket_still_being_voiced_is_sent_with_a_warning(teacher,monkeypatch):
    from apps.api.app import main
    tickets=main.tickets
    def unready(u,db):
        rows=tickets(u,db)
        for row in rows:
            if not row['published']:row['voice']={'ready':False,'generated':1,'total':18,'failed':0}
        return rows
    monkeypatch.setattr(main,'tickets',unready)
    source=next(v for v in teacher.get('/api/tickets').json() if v['published'] and not v['archived'] and all(t['mode']=='dds' for t in v['data']['tasks']))
    version=post(teacher,'/tickets',{**source['data'],'title':'Ещё озвучивается'}).json()['id']
    r=ask(teacher,'Отправь билет Морозову',version_id=version)
    assert r['confirm_required'] and 'Озвучка 1 из 18' in r['preview'] and 'без озвучки, текстом' in r['preview'] and 'черновик' in r['preview'],r['preview']
