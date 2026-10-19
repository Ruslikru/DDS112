"""Teacher assistant, requests of 20 October: «закрой …», opening and editing a ticket, the address,
several facts in one answer and a ticket from a whole description with questions only about what is missing."""
import pytest
from test_flows import app, TestClient, login, post

STORY='В подъезде жилого дома густой дым. Дом газифицирован.'
FIRE=('создай билет: Пожар в квартире 21 этажного здания. Пожар на 14 этаже. Есть пострадавшие 2 человека: мужчина Иван Петров '
      'Ильдарович 2006 года рождения и Анна Глубко Юрьевна 1965 года рождения. Тяжелые ожоги. Адрес: Барселона, улица Лионелли Месси 21 А, '
      'квартира 10. По телефону обращается очевидец: Игорь Иванов Владимирович, мужчина.')

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

@pytest.fixture
def teacher(monkeypatch):
    from apps.api.app import scenario_wizard, assistant_tickets
    monkeypatch.setattr(scenario_wizard,'complete',lambda *a,**kw:({'description':STORY},{'model':'test'}))
    def no_model(*a,**kw):raise RuntimeError('Локальная модель не установлена')
    monkeypatch.setattr(assistant_tickets,'complete',no_model)
    with TestClient(app) as c:
        login(c,'teacher')
        yield c

def latest(c):
    rows=c.get('/api/tickets').json()
    return next(v for v in rows if v['data']['tasks'] and not v['archived'])

def test_close_closes_what_is_named(teacher):
    for phrase in ('Закрой','закрой ассистента','закрой, пожалуйста'):
        assert ask(teacher,phrase)['action']=={'kind':'close'},phrase
    assert ask(teacher,'закрой билет')['action']=={'kind':'navigate','to':'/tickets'}
    assert ask(teacher,'закрой работу')['action']=={'kind':'navigate','to':'/reviews'}
    assert ask(teacher,'закрой мастер')['action']=={'kind':'event','name':'training112:close-dialogs'}
    assert ask(teacher,'закрой журнал')['action']=={'kind':'navigate','to':'/'}
    assert ask(teacher,'закрой рабочий стол')['intent']=='close_desktop'

def test_open_ticket_by_number_words_and_page(teacher):
    v=latest(teacher)
    r=ask(teacher,f'зайди в билет {v["ticket_id"]}')
    assert r['intent']=='open_ticket' and r['action']=={'kind':'navigate','to':f'/tickets/{v["id"]}'}
    r=ask(teacher,'редактировать билет')
    assert r['intent']=='open_ticket' and r['missing'][0]['slot']=='ticket'
    r=follow(teacher,r,str(v['ticket_id']))
    assert r['action']['to']==f'/tickets/{v["id"]}'
    r=ask(teacher,'редактировать билет',page=f'/tickets/{v["id"]}')
    assert r['intent']=='open_ticket' and 'уже открыт' in r['preview'] and not r['action']
    assert ask(teacher,'открой билеты')['action']=={'kind':'navigate','to':'/tickets'}
    missing=ask(teacher,'зайди в билет 999999')
    assert 'Билет № 999999 не найден' in missing['preview']

def test_edit_on_the_open_ticket_page_and_service_add(teacher):
    v=latest(teacher)
    r=ask(teacher,'поменяй сложность на 4',page=f'/tickets/{v["id"]}')
    assert r['intent']=='edit_ticket' and r['confirm_required'] and r['slots']['ticket_id']==v['ticket_id'] and r['slots']['value']==4
    r=ask(teacher,f'в билете {v["ticket_id"]} добавь службу 103')
    assert r['intent']=='edit_ticket' and r['slots']['field']=='services' and r['slots']['value']=='add:Служба 103'
    r=ask(teacher,f'билету {v["ticket_id"]} добавь службу 103')
    assert r['intent']=='edit_ticket' and r['slots']['value']=='add:Служба 103'
    r=ask(teacher,f'убери из билета {v["ticket_id"]} полицию')
    assert r['slots'].get('field')=='services' and r['slots'].get('value')=='remove:Служба 102'

def test_address_edit_replaces_the_place_everywhere(teacher):
    v=latest(teacher);task=v['data']['tasks'][0]
    card=task['expected_card'] if task['mode']=='112' else task['initial_card']
    old=card['street']
    r=ask(teacher,f'в билете {v["ticket_id"]} поменяй адрес на улицу Ленина, дом 5')
    assert r['intent']=='edit_ticket' and r['confirm_required'] and r['slots']['value']=={'street':'улица Ленина','house':'5'}
    assert 'улица Ленина, дом 5' in r['preview']
    done=run(teacher,r)
    saved=next(x for x in teacher.get('/api/tickets').json() if x['id']==done['slots'].get('version_id',0) or x['id']==int(done['action']['to'].split('/')[2].split('?')[0]))
    new=saved['data']['tasks'][0]
    new_card=new['expected_card'] if new['mode']=='112' else new['initial_card']
    assert new_card['street']=='улица Ленина' and new_card['house']=='5'
    if old and old!='улица Ленина':
        assert old not in str(new) and old not in saved['data']['title'],'the old street is gone from the intro, contacts and events'
    r=ask(teacher,'поменяй адрес',page=f'/tickets/{saved["id"]}')
    assert r['missing'][0]['slot']=='value'
    r=follow(teacher,r,'проспект Мира 10',page=f'/tickets/{saved["id"]}')
    assert r['slots']['value']=={'street':'проспект Мира','house':'10'}

def test_one_answer_fills_several_slots(teacher):
    r=ask(teacher,'создай билет')
    assert r['missing'][0]['slot']=='incident_type'
    r=follow(teacher,r,'Пожар. Двое пострадавших')
    assert r['slots']['incident_type']=='пожар' and r['slots']['victims']=='yes' and r['slots']['victims_count']==2
    assert r['missing'][0]['slot']=='difficulty'
    r=ask(teacher,'создай билет. Пожар. Двое пострадавших')
    assert r['slots']['incident_type']=='пожар' and r['slots']['victims_count']==2 and 'difficulty' not in r['slots']

def test_whole_description_asks_only_what_is_missing(teacher):
    r=ask(teacher,FIRE)
    story=r['slots']['story']
    assert story['place']['street']=='улица Лионелли Месси' and story['place']['house']=='21А' and story['place']['apartment']=='10'
    assert story['place']['floor']=='14' and story['caller_name']=='Игорь Иванов Владимирович' and 'Иван Петров Ильдарович' in story['victims_note']
    assert 'Барселона' not in story['seed'] and 'Игорь' not in story['seed']
    if r['candidates']:
        assert 'пожар: квартира' in [x['id'] for x in r['candidates']],r['candidates']
        r=follow(teacher,r,'пожар: квартира',incident_type='пожар: квартира')
    assert r['slots']['incident_type'] in ('пожар','пожар: квартира') and r['slots']['victims_count']==2
    asked=[]
    while not r['confirm_required']:
        slot=r['missing'][0]['slot'];asked.append(slot)
        assert slot not in ('incident_type','victims','victims_count'),'the description already named them'
        value={'own_service':'Служба 101','difficulty':3,'mode':'dds'}[slot]  # four stars and more hide the house for clarification
        r=follow(teacher,r,str(value),**{slot:value})
    assert 'difficulty' in asked
    assert 'Барселона' in r['preview'] and 'Игорь Иванов Владимирович' in r['preview']
    draft=run(teacher,r)
    assert draft['intent']=='save_ticket'
    from apps.api.app.assistant_tickets import DRAFTS
    ticket=DRAFTS[draft['slots']['draft_id']]['draft'];card=ticket['tasks'][0]['initial_card']
    assert card['city']=='Барселона' and card['street']=='улица Лионелли Месси' and card['house']=='21А'
    assert card['apartment']=='10' and card['floor']=='14' and card['name']=='Игорь Иванов Владимирович'
    assert 'Иван Петров Ильдарович' in card['description']

def test_new_command_is_not_taken_for_an_answer(teacher):
    r=ask(teacher,'создай билет про пожар')
    assert r['missing'][0]['slot']=='difficulty'
    v=latest(teacher)
    r=follow(teacher,r,f'зайди в билет {v["ticket_id"]}')
    assert r['intent']=='open_ticket' and r['action']['to']==f'/tickets/{v["id"]}'

def test_change_said_instead_of_the_ticket_is_kept(teacher):
    v=latest(teacher)
    r=ask(teacher,'редактировать билет')
    assert r['missing'][0]['slot']=='ticket'
    r=follow(teacher,r,'поменяй адрес на улицу Ленина, дом 5')
    assert r['intent']=='edit_ticket' and r['missing'][0]['slot']=='ticket' and r['slots']['field']=='address'
    r=follow(teacher,r,str(v['ticket_id']))
    assert r['confirm_required'] and r['slots']['value']=={'street':'улица Ленина','house':'5'}
