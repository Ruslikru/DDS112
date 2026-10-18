"""Teacher assistant, tickets stage: slot forms, confirmation tokens, creation through the wizard and edits as new versions."""
import time
import uuid
import pytest
from sqlalchemy import select
from test_flows import app, TestClient, login, post, HEAD, SessionLocal
from apps.api.app.db import Audit, User

PASSWORD='Training112!'
STORY='В подъезде жилого дома густой дым. Дом газифицирован. Доступ свободен.'

def ask(c,text,dialog=None):
    r=post(c,'/assistant/interpret',{'text':text,'context':{'page':'/tickets'},**({'dialog':dialog} if dialog else {})})
    assert r.status_code==200,r.text
    return r.json()

def follow(c,r,text='',**slots):
    """Continues the slot form the way the client does: same intent, accumulated slots, optional answer."""
    missing=r['missing'][0]['slot'] if r['missing'] else None
    answer=next(iter(slots)) if slots else missing if text else None
    return ask(c,text,{'intent':r['intent'],'slots':{**r['slots'],**slots,**({'answer_slot':answer} if answer else {})}})

def run(c,r):
    return post(c,'/assistant/execute',{'intent':r['intent'],'slots':r['slots'],'confirm_token':r['confirm_token']})

@pytest.fixture
def teacher(monkeypatch):
    from apps.api.app import scenario_wizard, assistant_tickets
    monkeypatch.setattr(scenario_wizard,'complete',lambda *a,**kw:({'description':STORY},{'model':'test'}))
    monkeypatch.setattr(assistant_tickets,'complete',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('model must not be asked when rules found the incident')))
    with TestClient(app) as c:
        login(c,'teacher')
        yield c

def test_full_phrase_fills_every_slot_and_creates_a_ticket(teacher):
    r=ask(teacher,'создай билет про пожар на 3 звезды для ДДС с двумя пострадавшими')
    assert r['intent']=='create_ticket' and r['confirm_required'] and r['confirm_token'] and not r['missing'],r
    assert r['slots']['incident_type']=='пожар' and r['slots']['own_service']=='Служба 101' and r['slots']['mode']=='dds'
    assert r['slots']['difficulty']==3 and r['slots']['victims']=='yes' and r['slots']['victims_count']==2
    assert 'Служба 101' in r['preview'] and '★★★' in r['preview'] and r['action'] is None
    done=run(teacher,r);assert done.status_code==200,done.text
    body=done.json();assert body['ok'] and body['action']['kind']=='navigate' and body['action']['to'].startswith('/tickets/')
    version_id=int(body['action']['to'].rsplit('/',1)[1])
    saved=next(v for v in teacher.get('/api/tickets').json() if v['id']==version_id)
    assert saved['data']['difficulty_stars']==3 and saved['data']['tasks'][0]['mode']=='dds' and not saved['published']
    assert saved['data']['tasks'][0]['initial_card']['victims_count']=='2' and 'Служба 101' in saved['data']['tasks'][0]['services']
    with SessionLocal() as db:
        rows=list(db.scalars(select(Audit).where(Audit.action=='assistant_executed').order_by(Audit.id.desc())))
        assert rows and rows[0].detail['version_id']==version_id and rows[0].detail['incident_type']=='пожар'

def test_slot_form_asks_one_question_at_a_time(teacher):
    r=ask(teacher,'давай новый билет сделаем')
    assert r['intent']=='create_ticket' and r['missing'][0]['slot']=='own_service' and not r['confirm_required']
    assert {'value':'ДДС района','label':'ДДС района'} in r['missing'][0]['options']
    r=follow(teacher,r,'ДДС района',own_service='ДДС района')
    assert r['missing'][0]['slot']=='incident_type' and {'value':'лифт','label':'лифт'} in r['missing'][0]['options']
    r=follow(teacher,r,'лифт')
    assert r['slots']['incident_type']=='лифт' and r['missing'][0]['slot']=='mode'
    r=follow(teacher,r,'оператора 112')
    assert r['slots']['mode']=='112' and r['missing'][0]['slot']=='difficulty'
    r=follow(teacher,r,'четыре')
    assert r['slots']['difficulty']==4 and r['missing'][0]['slot']=='victims'
    r=follow(teacher,r,'есть')
    assert r['slots']['victims']=='yes' and r['missing'][0]['slot']=='victims_count'
    r=follow(teacher,r,'много')
    assert r['missing'][0]['slot']=='victims_count','an unreadable answer repeats the same question'
    r=follow(teacher,r,'трое')
    assert r['confirm_required'] and r['slots']['victims_count']==3 and 'оператор 112' in r['preview']
    done=run(teacher,r);assert done.status_code==200,done.text
    version_id=int(done.json()['action']['to'].rsplit('/',1)[1])
    saved=next(v for v in teacher.get('/api/tickets').json() if v['id']==version_id)
    assert saved['data']['tasks'][0]['mode']=='112' and saved['data']['difficulty_stars']==4

def test_option_click_and_correction_before_confirmation(teacher):
    r=ask(teacher,'создай билет про лифт для ДДС района, сложность 2, без пострадавших')
    assert r['confirm_required'] and r['slots']['difficulty']==2 and r['slots']['victims']=='no' and r['slots']['mode']=='dds'
    r=follow(teacher,r,'сложность 5')
    assert r['confirm_required'] and r['slots']['difficulty']==5 and r['slots']['incident_type']=='лифт','a correction keeps the other slots'
    r=follow(teacher,r,'Оператор 112',mode='112')
    assert r['confirm_required'] and r['slots']['mode']=='112'

def test_generic_topic_is_refused_before_the_wizard(teacher):
    r=ask(teacher,'создай билет про пострадавшие')
    assert r['intent']=='create_ticket' and 'конкретное происшествие' in r['preview'] and r['missing'][0]['slot']=='incident_type' and not r['confirm_required']
    r=ask(teacher,'',{'intent':'create_ticket','slots':{'incident_type':'полиция','own_service':'Служба 102','mode':'dds','difficulty':1,'victims':'no'}})
    assert 'конкретное происшествие' in r['preview'] and not r['confirm_required']

def test_classifier_candidates_are_offered_for_ambiguous_incident(teacher):
    r=ask(teacher,'сделай билет про трамвай')
    assert r['intent']=='create_ticket' and r['candidates'] and all(c['kind']=='incident' and c['slot']=='incident_type' for c in r['candidates'])
    assert any('трамва' in c['label'].lower() for c in r['candidates']) and not r['confirm_required']
    pick=next(c for c in r['candidates'] if c['label']=='Трамвай сход с рельс')
    r=follow(teacher,r,pick['label'],incident_type=pick['id'])
    assert r['slots']['incident_type']=='Трамвай сход с рельс' and r['missing'][0]['slot']=='own_service'

def test_unknown_incident_asks_again(teacher):
    r=ask(teacher,'создай билет про единорога для ДДС района')
    assert r['intent']=='create_ticket' and 'Не нашёл происшествие' in r['preview'] and r['missing'][0]['slot']=='incident_type'
    assert r['slots'].get('own_service')=='ДДС района' and {'value':'лифт','label':'лифт'} in r['missing'][0]['options']

def test_model_extracts_incident_when_rules_cannot(monkeypatch):
    from apps.api.app import scenario_wizard, assistant_tickets
    monkeypatch.setattr(scenario_wizard,'complete',lambda *a,**kw:({'description':STORY},{'model':'test'}))
    calls=[]
    def model(system,prompt,schema,**kwargs):
        calls.append(prompt);assert kwargs['tokens']==160 and 'enum' in str(schema)
        return {'incident':'лифт','victims':'no','victims_count':0,'difficulty':2,'mode':'dds'},{'model':'test'}
    monkeypatch.setattr(assistant_tickets,'complete',model)
    with TestClient(app) as c:
        login(c,'teacher')
        r=ask(c,'создай билет: у нас кабина застряла между этажами, никого не зажало')
        assert calls==['создай билет: у нас кабина застряла между этажами, никого не зажало']
        assert r['slots']['incident_type']=='лифт' and r['slots']['difficulty']==2 and r['slots']['victims']=='no' and r['slots']['mode']=='dds'
        assert r['missing'][0]['slot']=='own_service' and {'value':'ДДС района','label':'ДДС района'} in r['missing'][0]['options'],'two services share the tag «лифт», so the teacher picks one'
        r=follow(c,r,'ДДС района',own_service='ДДС района')
        assert r['confirm_required'] and r['slots']['own_service']=='ДДС района' and r['slots']['services']==['ДДС района']
        monkeypatch.setattr(assistant_tickets,'complete',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('нейросеть занята')))
        r=ask(c,'создай билет, что-то случилось во дворе')
        assert r['intent']=='create_ticket' and r['missing'][0]['slot']=='own_service' and not r['confirm_required'],'a busy model degrades to the ordinary questions'

def test_confirm_token_binds_user_slots_and_time(teacher,monkeypatch):
    r=ask(teacher,'создай билет про лифт для ДДС района на 1 звезду без пострадавших')
    assert r['confirm_required']
    tampered=post(teacher,'/assistant/execute',{'intent':r['intent'],'slots':{**r['slots'],'difficulty':5},'confirm_token':r['confirm_token']})
    assert tampered.status_code==403
    assert post(teacher,'/assistant/execute',{'intent':'create_ticket','slots':r['slots'],'confirm_token':'1.deadbeef'}).status_code==403
    assert post(teacher,'/assistant/execute',{'intent':'open_page','slots':{},'confirm_token':r['confirm_token']}).status_code==400
    from apps.api.app import assistant
    monkeypatch.setattr(assistant,'TOKEN_TTL',-1)
    assert run(teacher,r).status_code==409
    monkeypatch.setattr(assistant,'TOKEN_TTL',600)
    with TestClient(app) as other:
        login(other,'admin')
        assert post(other,'/assistant/execute',{'intent':r['intent'],'slots':r['slots'],'confirm_token':r['confirm_token']}).status_code==403

def test_wizard_errors_reach_the_teacher_in_words(teacher):
    r=ask(teacher,'создай билет про лифт для ДДС района на 1 звезду без пострадавших')
    from apps.api.app import assistant
    with SessionLocal() as db:
        u=db.scalar(select(User).where(User.login=='teacher'))
        slots={**r['slots'],'incident_type':'пострадавшие'}
        token=assistant.confirm_token(u,'create_ticket',slots)
    failed=post(teacher,'/assistant/execute',{'intent':'create_ticket','slots':slots,'confirm_token':token})
    assert failed.status_code==400 and 'конкретное происшествие' in failed.json()['detail']

@pytest.fixture
def ticket(teacher):
    tag=uuid.uuid4().hex[:6]
    source=teacher.get('/api/tickets').json()[0]['data']
    data={**source,'title':f'Застрявший лифт {tag}','description':'Учебный билет ассистента','difficulty_stars':2,'difficulty':'Базовый'}
    saved=post(teacher,'/tickets',data);assert saved.status_code==200,saved.text
    version=next(v for v in teacher.get('/api/tickets').json() if v['id']==saved.json()['id'])
    return {'tag':tag,'ticket_id':version['ticket_id'],'version_id':version['id'],'data':version['data']}

def test_edit_difficulty_by_number_keeps_other_fields(teacher,ticket):
    r=ask(teacher,f'в билете {ticket["ticket_id"]} поменяй сложность на 4')
    assert r['intent']=='edit_ticket' and r['confirm_required'] and r['slots']['ticket_id']==ticket['ticket_id'] and r['slots']['field']=='difficulty_stars' and r['slots']['value']==4
    assert '★★ → ★★★★' in r['preview']
    done=run(teacher,r);assert done.status_code==200,done.text
    body=done.json();assert body['action']['to'].endswith('?section=story')
    new_id=int(body['action']['to'].split('/')[2].split('?')[0])
    versions=[v for v in teacher.get('/api/tickets').json() if v['ticket_id']==ticket['ticket_id']]
    latest=next(v for v in versions if v['id']==new_id)
    assert latest['number']==2 and latest['data']['difficulty_stars']==4 and latest['data']['difficulty']=='Сложный'
    assert latest['data']['title']==ticket['data']['title'] and len(latest['data']['tasks'])==len(ticket['data']['tasks'])
    assert latest['data']['tasks'][0]['criteria']==ticket['data']['tasks'][0]['criteria']

def test_rename_by_title_words_and_time_limit(teacher,ticket):
    r=ask(teacher,f'переименуй билет про лифт {ticket["tag"]} в «Лифт застрял {ticket["tag"]}»')
    assert r['intent']=='edit_ticket' and r['slots']['ticket_id']==ticket['ticket_id'] and r['slots']['field']=='title' and r['slots']['value']==f'Лифт застрял {ticket["tag"]}',r
    done=run(teacher,r);assert done.status_code==200,done.text
    new_id=int(done.json()['action']['to'].split('/')[2].split('?')[0])
    assert next(v for v in teacher.get('/api/tickets').json() if v['id']==new_id)['data']['title']==f'Лифт застрял {ticket["tag"]}'
    r=ask(teacher,f'у билета {ticket["ticket_id"]} поставь норматив 300 секунд')
    assert r['slots']['field']=='limit_seconds' and r['slots']['value']==300 and r['confirm_required']
    done=run(teacher,r);assert done.status_code==200,done.text
    new_id=int(done.json()['action']['to'].split('/')[2].split('?')[0])
    assert next(v for v in teacher.get('/api/tickets').json() if v['id']==new_id)['data']['tasks'][0]['limit_seconds']==300

def test_edit_asks_for_ticket_field_and_value(teacher,ticket):
    r=ask(teacher,'измени билет')
    assert r['intent']=='edit_ticket' and r['missing'][0]['slot']=='ticket'
    r=follow(teacher,r,str(ticket['ticket_id']))
    assert r['slots']['ticket_id']==ticket['ticket_id'] and r['missing'][0]['slot']=='field'
    r=follow(teacher,r,'сложность')
    assert r['slots']['field']=='difficulty_stars' and r['missing'][0]['slot']=='value' and r['missing'][0]['options']
    r=follow(teacher,r,'5')
    assert r['confirm_required'] and r['slots']['value']==5

def test_ambiguous_and_missing_tickets(teacher,ticket):
    tag=ticket['tag']
    second=post(teacher,'/tickets',{**ticket['data'],'title':f'Лифт и дым {tag}'});assert second.status_code==200
    r=ask(teacher,f'в билете про лифт {tag} поменяй сложность на 3')
    assert r['candidates'] and {c['id'] for c in r['candidates']}>={ticket['ticket_id'],next(v['ticket_id'] for v in teacher.get('/api/tickets').json() if v['id']==second.json()['id'])}
    assert all(c['kind']=='ticket' and c['slot']=='ticket_id' for c in r['candidates'])
    r=follow(teacher,r,r['candidates'][0]['label'],ticket_id=ticket['ticket_id'])
    assert r['confirm_required'] and r['slots']['ticket_id']==ticket['ticket_id']
    r=ask(teacher,'в билете 999999 поменяй сложность на 3')
    assert 'не найден' in r['preview'] and r['missing'][0]['slot']=='ticket' and not r['confirm_required']

def test_complex_edits_only_open_the_editor_tab(teacher,ticket):
    r=ask(teacher,f'в билете {ticket["ticket_id"]} измени критерии оценки')
    assert r['intent']=='edit_ticket' and not r['confirm_required'] and r['action']=={'kind':'navigate','to':f'/tickets/{ticket["version_id"]}?section=criteria'}

def test_negation_and_students_are_kept_out(teacher):
    r=ask(teacher,'билет пока не создавай')
    assert r['intent']=='unknown' and 'ничего не делаю' in r['preview']
    r=ask(teacher,'а можно вообще создавать билеты?')
    assert r['intent']=='unknown'
    with TestClient(app) as c:
        login(c,'student')
        assert post(c,'/assistant/execute',{'intent':'create_ticket','slots':{},'confirm_token':'x'}).status_code==403
