"""Ticket from a free-text description: stated facts are kept, the gaps are filled."""
import pytest
from sqlalchemy import select
from test_flows import app, TestClient, login, post, SessionLocal
from apps.api.app.db import Audit

REPORTS={'approach':'Выезжаем к школе, на подъезде плотное движение, будем через несколько минут.',
         'on_scene':'Прибыли, из окон второго этажа идёт дым, проводим разведку и эвакуацию.',
         'outcome':'Возгорание в кабинете ликвидировано, здание проветриваем, передаём результат.'}

def empty(**values):
    base={'incident':'','own_service':'','mode':'','victims':'','victims_count':0,'animals':'','difficulty':0,
          'street':'','house':'','caller_name':'','object':'','description':''}
    return {**base,**values}

@pytest.fixture
def author(monkeypatch):
    from apps.api.app import scenario_wizard
    def wizard_model(system,prompt,schema,**kwargs):
        if 'description' in schema['properties']:return {'description':prompt},{'model':'test'}  # rewrite of the scene template
        return REPORTS,{'model':'test'}
    monkeypatch.setattr(scenario_wizard,'complete',wizard_model)
    with TestClient(app) as c:
        login(c,'admin')
        before=c.get('/api/management/training-modes').json()['operator112']
        assert post(c,'/management/training-modes',{'operator112':True}).status_code==200  # 112 drafts need the mode switched on
        login(c,'teacher')
        yield c
        login(c,'admin');post(c,'/management/training-modes',{'operator112':before})

def model(monkeypatch,value):
    from apps.api.app import prompt_ticket
    calls=[]
    def inference(system,prompt,schema,**kwargs):
        calls.append(prompt)
        assert 'untrusted data' in system and set(schema['required'])==set(value)
        return value,{'model':'test','mode':'cpu','seconds':1}
    monkeypatch.setattr(prompt_ticket,'complete',inference)
    return calls

def generate(c,prompt,**extra):
    r=post(c,'/ai/prompt',{'prompt':prompt,**extra})
    assert r.status_code==200,r.text
    return r.json()

def test_stated_facts_are_kept_and_the_draft_publishes(author,monkeypatch):
    calls=model(monkeypatch,empty(incident='пожар',object='школа',caller_name='Ольга Иванова',street='улица Хачатуряна',house='7',
                                  description='В здании школы горит кабинет на втором этаже. Из окон идёт густой дым.'))
    body=generate(author,'Пожар в школе на улице Хачатуряна, дом 7. Двое пострадавших, сложность 4, для оператора 112. Звонит Ольга Иванова.')
    ticket,meta=body['data'],body['meta'];task=ticket['tasks'][0];card=task['expected_card']
    assert len(calls)==1
    assert task['mode']=='112' and ticket['difficulty_stars']==4
    assert card['street']=='улица Хачатуряна' and card['house']=='7' and card['name']=='Ольга Иванова'
    assert card['incident_type']=='пожар' and card['object']=='Школа' and card['victims_count']=='2'
    assert 'школы' in task['intro'] and 'Служба 101' in task['services'] and 'Служба 103' in task['services']
    assert meta['sources']['incident_type']=='prompt' and meta['sources']['difficulty']=='prompt' and meta['sources']['mode']=='prompt'
    assert meta['sources']['address']=='prompt' and meta['sources']['caller_name']=='prompt' and meta['sources']['description']=='prompt'
    assert meta['sources']['own_service']=='computed' and not meta['warnings']
    assert meta['slots']['incident_type']=='пожар' and meta['slots']['own_service']=='Служба 101' and meta['slots']['victims_count']==2
    saved=post(author,'/tickets',ticket);assert saved.status_code==200,saved.text
    published=post(author,f'/tickets/{saved.json()["id"]}/publish');assert published.status_code==200,published.text
    with SessionLocal() as db:
        row=db.scalars(select(Audit).where(Audit.action=='prompt_draft_generated').order_by(Audit.id.desc())).first()
        assert row and row.detail['incident']=='пожар' and 'школе' in row.detail['prompt']

def test_dds_draft_uses_model_reports(author,monkeypatch):
    model(monkeypatch,empty(incident='задымление',description='В подъезде жилого дома густой дым. На лестнице пахнет гарью.'))
    body=generate(author,'Задымление в подъезде, пострадавших нет, для службы 101')
    ticket,meta=body['data'],body['meta'];task=ticket['tasks'][0]
    assert task['mode']=='dds' and task['own_service']=='Служба 101' and meta['sources']['mode']=='default'
    assert task['initial_card']['victims']=='no' and 'дым' in task['initial_card']['description']
    assert meta['brigade_reports']=='model' and any('разведку' in e['text'] for e in task['service_events'])
    assert 1<=ticket['difficulty_stars']<=5 and meta['sources']['difficulty']=='computed'
    assert post(author,'/tickets',ticket).status_code==200

def test_gaps_are_filled_randomly(author,monkeypatch):
    model(monkeypatch,empty())
    body=generate(author,'Нужен какой-нибудь учебный билет')
    ticket,meta=body['data'],body['meta'];task=ticket['tasks'][0]
    assert meta['sources']['incident_type']=='random' and meta['warnings']
    assert meta['sources']['address']=='random' and meta['sources']['caller_name']=='random' and meta['sources']['victims']=='default'
    assert task['initial_card']['street'] and task['initial_card']['house'] and task['initial_card']['name']
    assert task['initial_card']['victims']=='unknown'
    assert post(author,'/tickets',ticket).status_code==200

def test_model_may_not_invent_names_streets_or_incidents(author,monkeypatch):
    model(monkeypatch,empty(incident='наводнение',caller_name='Пётр Сидоров',street='Тверская улица',house='13',object='вокзал',
                            description='На вокзале прорвало трубу, вода заливает зал.'))
    body=generate(author,'Человек упал во дворе и повредил ногу, есть пострадавшие')
    meta=body['meta'];card=body['data']['tasks'][0]['initial_card']
    assert card['name']!='Пётр Сидоров' and 'Тверская' not in card['street'] and card['object']!='Вокзал'
    assert meta['sources']['caller_name']=='random' and meta['sources']['address']=='random'
    assert meta['slots']['incident_type']!='наводнение' and meta['sources']['incident_type']!='prompt'
    assert card['victims']=='yes' and 1<=int(card['victims_count'])<=3 and meta['sources']['victims_count']=='random'

def test_nearest_type_and_choice_among_candidates(author,monkeypatch):
    model(monkeypatch,empty(incident='пожар машины'))
    body=generate(author,'Пожар машины во дворе')
    meta=body['meta']
    assert meta['sources']['incident_type']=='nearest' and meta['slots']['incident_type']=='пожар: машина'
    assert len(meta['candidates'])>1 and meta['candidates'][0]=='пожар: машина' and 'Служба 101' in body['data']['tasks'][0]['services']
    chosen=next(title for title in meta['candidates'][1:] if title!='пожар: машина')
    again=generate(author,'Пожар машины во дворе',incident_type=chosen)
    assert again['meta']['slots']['incident_type']==chosen and again['meta']['sources']['incident_type']=='chosen'
    assert post(author,'/ai/prompt',{'prompt':'Пожар машины во дворе','incident_type':'несуществующий тип'}).status_code==400

def test_nearest_type_prefers_titles_without_extra_words(author,monkeypatch):
    model(monkeypatch,empty())
    meta=generate(author,'Застрял лифт в жилом доме, внутри двое взрослых')['meta']
    assert meta['slots']['incident_type']=='Застревание в лифте',meta['candidates']
    meta=generate(author,'Прорыв трубы в подвале, вода')['meta']
    assert 'прорыв' in meta['slots']['incident_type'].casefold(),meta['candidates']

def test_without_model_rules_and_template_still_give_a_draft(author,monkeypatch):
    from apps.api.app import prompt_ticket
    def unavailable(*a,**kw):raise RuntimeError('Локальная модель не установлена. Нужна папка local_ai с моделью и runtime.')
    monkeypatch.setattr(prompt_ticket.runtime,'complete_pre',unavailable)
    from apps.api.app import scenario_wizard
    monkeypatch.setattr(scenario_wizard,'complete',lambda *a,**kw:scenario_wizard.m.fail('Локальная модель не установлена',503))
    body=generate(author,'создай билет про лифт, застряли двое, на 2 звезды')
    meta=body['meta'];task=body['data']['tasks'][0]
    assert meta['model']=='rules' and meta['warnings'] and meta['sources']['description']=='prompt'
    assert meta['slots']['incident_type']=='лифт' and meta['sources']['incident_type']=='prompt'
    assert body['data']['difficulty_stars']==2 and meta['brigade_reports']=='fallback'
    assert 'лифт, застряли двое' in task['initial_card']['description'].casefold() and 'звезд' not in task['initial_card']['description']
    template=generate(author,'Нужен билет, 3 звезды')['meta']
    assert template['sources']['description']=='template' and template['sources']['incident_type']=='random'

def test_busy_model_is_reported(author,monkeypatch):
    from apps.api.app import prompt_ticket
    def busy(*a,**kw):raise RuntimeError('Нейросеть занята другим запросом. Повторите через несколько секунд.')
    monkeypatch.setattr(prompt_ticket.runtime,'complete_pre',busy)
    r=post(author,'/ai/prompt',{'prompt':'Пожар в подъезде жилого дома'})
    assert r.status_code==503 and 'занята' in r.text

def test_students_cannot_generate():
    with TestClient(app) as c:
        login(c,'student')
        assert post(c,'/ai/prompt',{'prompt':'Пожар в подъезде жилого дома'}).status_code==403

def test_model_enums_count_only_when_the_request_mentions_them(author,monkeypatch):
    model(monkeypatch,empty(incident='запах газа',own_service='ДДС района',mode='dds',victims='unknown',difficulty=5,animals='yes',
                            description='В подъезде сильно пахнет газом. Жильцы жалуются на головную боль.'))
    body=generate(author,'Запах газа в подъезде, жильцы жалуются на головную боль.')
    meta=body['meta'];task=body['data']['tasks'][0]
    assert meta['sources']['own_service']=='computed' and task['own_service']=='Служба 104'
    assert meta['sources']['mode']=='default' and meta['sources']['victims']=='default' and meta['sources']['difficulty']=='computed'
    assert not meta['slots']['animals'] and meta['sources']['object']=='computed'

FIRE='''Пожар в квартире 21 этажного здания. Пожар на 14 этаже. Переходит на этажи выше. Есть пострадавшие 2 человека: мужчина Иван Петров Ильдарович 2006 года рождения и Анна Глубко Юрьевна 1965 года рождения. Тяжелые ожоги. В доме есть газ. Подозреваемый в поджоге найден. Адрес: Барселона, улица Лионелли Месси 21 А, квартира 10. По телефону обращается очевидец: Игорь Иванов Владимирович, мужчина.'''

def test_long_description_without_model_keeps_place_people_and_scene(author,monkeypatch):
    from apps.api.app import prompt_ticket
    def unavailable(*a,**kw):raise RuntimeError('Локальная модель не установлена. Нужна папка local_ai с моделью и runtime.')
    monkeypatch.setattr(prompt_ticket.runtime,'complete_pre',unavailable)
    body=generate(author,FIRE)
    ticket,meta=body['data'],body['meta'];task=ticket['tasks'][0];card=task['initial_card']
    assert meta['slots']['incident_type']=='пожар: квартира',meta['candidates']
    assert 'не установлена' in meta['warnings'][0] and any('Барселона' in w for w in meta['warnings'])
    assert card['city']=='Барселона' and card['street']=='улица Лионелли Месси' and card['house']=='21А'
    assert card['apartment']=='10' and card['floor']=='14' and not card['area']
    assert card['name']=='Игорь Иванов Владимирович' and meta['sources']['caller_name']=='prompt' and meta['sources']['address']=='prompt'
    story=card['description']
    assert story.startswith('Пожар в квартире 21 этажного здания. Пожар на 14 этаже') and 'Тяжелые ожоги' in story
    assert not any(word in story for word in ('Барселона','Месси','Игорь','мужчина.','квартира 10','Адрес'))
    assert 'Пострадавших людей: 2.' in story and 'Иван Петров Ильдарович 2006 года рождения' in story
    assert {'Служба 101','Служба 102','Служба 103','Служба 104'}<=set(task['services'])
    assert ticket['title']=='пожар: квартира: улица Лионелли Месси, дом 21А'
    assert 'Москва' not in task['intro']
    assert post(author,'/tickets',ticket).status_code==200

def test_place_parsing():
    from apps.api.app.prompt_ticket import parse_place, scene_from_request
    assert parse_place('Адрес: г. Москва, проспект Мира, д. 10, подъезд 2. Дым на 5 этаже.')=={'city':'Москва','street':'проспект Мира','house':'10','entrance':'2','floor':'5'}
    assert parse_place('Пожар','улица Ленина 5, кв. 3')=={'street':'улица Ленина','house':'5','apartment':'3'}
    assert parse_place('Пожар','улица Садовой, дом 3')=={'street':'улица Садовой','house':'3'}
    assert scene_from_request('Пожар в школе на улице Хачатуряна, дом 7. Из окон идёт дым, двое пострадавших. Для оператора 112, сложность 4.')=='Пожар в школе. Из окон идёт дым.'
    assert scene_from_request('Горит бар на первом этаже, очевидец: Пётр Сидоров, мужчина.')=='Горит бар на первом этаже.'

def test_model_story_loses_invented_districts_and_casualty_sentences(author,monkeypatch):
    from apps.api.app.scenario_facts import clean_story
    assert clean_story('Пожар в квартире на 14 этаже 21-этажного здания в районе Северный, округе Боровицкий. Огонь перешёл выше. В результате пострадали двое.')=='Пожар в квартире на 14 этаже 21-этажного здания. Огонь перешёл выше.'
    model(monkeypatch,empty(incident='пожар',description='Горит квартира в районе Северный, округе Боровицкий. Из окон идёт дым. Есть пострадавшие.'))
    card=generate(author,'Пожар в квартире, из окон идёт дым, двое пострадавших')['data']['tasks'][0]['initial_card']
    assert card['description'].startswith('Горит квартира. Из окон идёт дым. Пострадавших людей: 2.'),card['description']
