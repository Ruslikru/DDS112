import re
from types import SimpleNamespace
from test_flows import app, TestClient, login, post
from apps.api.app.scenario_facts import semantic_services
from apps.api.app.ticket_difficulty import assess_wizard, legacy_level

def test_difficulty_is_based_on_facts_not_model_label():
    simple=SimpleNamespace(incident_type='лифт',victims_state='no',victims_count=0,animals=False)
    assert assess_wizard(simple,{'description':'Лифт остановился. Доступ свободен.','traits':[]},['ДДС района'])[0]==1
    complex_case=SimpleNamespace(incident_type='сход трамвая с рельс',victims_state='yes',victims_count=3,animals=False)
    stars,reason=assess_wizard(complex_case,{'description':'Повреждены провода контактной сети.','traits':[]},['Служба 102','Служба 103','Служба 101'])
    assert stars==5 and 'несколько пострадавших' in reason and legacy_level(stars)=='Сложный'

def test_service_facts_and_negations():
    services=[SimpleNamespace(name=name,config={}) for name in ['Служба 101','Служба 103','Газовая']]
    assert semantic_services(services,{'victims':'yes'})==['Служба 103']
    assert semantic_services(services,{'traits':['Есть пострадавшие','Газифицированный дом']})==['Служба 103','Газовая']
    assert semantic_services(services,{'incident_type':'пожар','description':'Дом не газифицирован. Пострадавших нет.'})==['Служба 101']
    assert 'Газовая' in semantic_services(services,{'description':'Дом газифицирован.'})
    assert semantic_services(services[:2],{'description':'Дом газифицирован.'})==[]
    ambulance=SimpleNamespace(name='Служба 103',config={'tags':['пострадавшие']})
    assert semantic_services([ambulance],{'victims':'no','traits':['Есть пострадавшие животные']})==[]
    district=SimpleNamespace(name='ДДС района',config={'tags':['вода']})
    assert semantic_services([district],{'description':'Повреждены провода контактной сети.'})==[]

def test_correct_russian_is_not_flagged():
    from apps.api.app.domain import text_checks
    assert text_checks('Район обслуживания. Примите решение и организуйте реагирование. Ход работ уточняйте у старшего бригады.')==[]
    assert text_checks('В доме доме задымленее!!!')
    assert any('расстояния' in item['message'] for item in text_checks('Очевидец стоит на безопасном растояния.'))

def test_import_unrelated_json_as_ticket(monkeypatch):
    from apps.api.app import ai_routes
    def inference(system,prompt,*args,**kwargs):
        assert 'драка' in prompt and 'место' in prompt
        return {'incident_type':'112','description':'Во дворе жилого дома двое мужчин дерутся возле автомобиля. Очевидец просит направить полицию.',
                'mode':'dds','victims_state':'unknown','difficulty':'Средний','street':'','house':'','caller_name':''},{'model':'test'}
    monkeypatch.setattr(ai_routes,'complete',inference)
    with TestClient(app) as c:
        login(c,'admin')
        response=post(c,'/ai/tickets/from-json',{'content':{'событие':'драка возле автомобиля','место':'улица Декабристов, дом 28','свидетель':'Елена Соколова','подробности':'Двое мужчин дерутся возле машины.'}})
        assert response.status_code==200,response.text
        ticket=response.json()['data'];task=ticket['tasks'][0]
        assert ticket['description']=='Двое мужчин дерутся возле машины.' and ticket['difficulty']=='Средний'
        assert task['mode']=='112' and task['expected_card']['street']=='улица Декабристов' and task['expected_card']['house']=='28'
        assert task['expected_card']['incident_type']=='правонарушение' and task['expected_card']['name']=='Елена Соколова'
        assert task['questions'] and task['criteria'] and task['services']
        saved=post(c,'/tickets',ticket)
        assert saved.status_code==200,saved.text
        assert post(c,f'/tickets/{saved.json()["id"]}/publish').status_code==200

def test_wizard_rich_card_publish_both_modes(monkeypatch):
    from apps.api.app import scenario_wizard
    monkeypatch.setattr(scenario_wizard,'complete',lambda *a,**kw:({'description':'В подъезде жилого дома густой дым. Дом газифицирован. Доступ свободен.','difficulty':'Средний'},{'model':'test'}))
    with TestClient(app) as c:
        login(c,'admin')
        assert post(c,'/learning/services',{'name':'Газовая','tags':['газ'],'active':True}).status_code==200
        payload={'incident_type':'задымление','own_service':'Служба 101','services':['Служба 101'],'victims_state':'yes','victims_count':2}
        suggestions=post(c,'/learning/services/suggest',{'incident_type':'задымление','victims':'yes'}).json()['services']
        assert {'Служба 101','Служба 103'}<=set(suggestions)
        for mode in ['dds','112']:
            response=post(c,'/ai/wizard',{**payload,'mode':mode})
            assert response.status_code==200,response.text
            draft=response.json()['data'];task=draft['tasks'][0]
            card=task['initial_card'] if mode=='dds' else task['expected_card']
            assert {'Служба 101','Служба 103','Газовая'}<=set(task['services'])
            assert card['area']!='Учебный район' and card['street']!='Учебная'
            assert len([v for v in card.values() if v])>=20
            assert re.fullmatch(r'\+7 \(9\d{2}\) \d{3}-\d{2}-\d{2}',task['phone'])
            assert card['phone']==task['phone']
            assert card['street'] in draft['title'] and 'ДДС ·' not in draft['title']
            assert draft['difficulty_stars']==5 and draft['difficulty_reason']
            if mode=='dds':
                assert card['blocked']=='unknown'
                assert any(question['id']=='access' for question in task['contacts'][1]['questions'])
            assert 'Дым' in task['traits'] and 'Газифицированный дом' in card['traits']
            saved=post(c,'/tickets',draft)
            assert saved.status_code==200,saved.text
            published=post(c,f'/tickets/{saved.json()["id"]}/publish')
            assert published.status_code==200,published.text


def test_tram_wizard_rejects_unrelated_model_story(monkeypatch):
    from apps.api.app import scenario_wizard
    monkeypatch.setattr(scenario_wizard,'complete',lambda *a,**kw:({'description':'В доме человек упал на лестнице и повредил ногу.','difficulty':'Средний'},{'model':'test'}))
    with TestClient(app) as c:
        login(c,'admin')
        payload={'incident_type':'Трамвай сход с рельс','own_service':'Служба 102','services':['Служба 102'],
                 'traits':['Повреждены провода контактной сети'],'victims_state':'yes','victims_count':3,'animals':True}
        response=post(c,'/ai/wizard',payload)
        assert response.status_code==200,response.text
        task=response.json()['data']['tasks'][0]
        assert task['type_options']==['Трамвай сход с рельс']
        assert 'трамвай' in task['initial_card']['description'].casefold()
        assert 'лестниц' not in task['initial_card']['description'].casefold()
        assert task['initial_card']['object']=='Участок улицы'
        assert {'Служба 102','Служба 103'}<=set(task['services'])
        assert 'Есть пострадавшие' in task['traits'] and 'Нет пострадавших' not in task['traits']
        assert 'Нет доступа' not in task['traits'] and 'Доступ свободен' not in task['traits']
        assert post(c,'/ai/wizard',{**payload,'incident_type':'пострадавшие'}).status_code==400


def test_wizard_uses_scenario_reports_for_brigade_calls(monkeypatch):
    from apps.api.app import scenario_wizard
    calls=[]
    def inference(system,prompt,*args,**kwargs):
        calls.append(prompt)
        if len(calls)==1:
            return {'description':'Во дворе дома человек упал на ступенях и не может встать. Он в сознании и жалуется на боль в ноге.',
                    'difficulty':'Средний'},{'model':'test'}
        return {'approach':'Мы выехали на вызов, но у дома затор. Подскажите, с какой стороны лучше подъехать к пострадавшему.',
                'on_scene':'Мы у подъезда, осматриваем пострадавшего после падения. Он в сознании, уточняем характер боли.',
                'outcome':'Помощь оказана. Госпитализируем пострадавшего для обследования ноги; передадим маршрут при выезде.'},{'model':'test'}
    monkeypatch.setattr(scenario_wizard,'complete',inference)
    with TestClient(app) as c:
        login(c,'admin')
        result=post(c,'/ai/wizard',{'incident_type':'травма','own_service':'Служба 103','services':['Служба 103'],
                                    'victims_state':'yes','victims_count':1})
        assert result.status_code==200,result.text
        task=result.json()['data']['tasks'][0]
        messages=[event['text'] for event in task['service_events']]
        assert len(calls)==2 and len(messages)==3
        assert 'затор' in messages[0] and 'осматриваем' in messages[1] and 'Госпитализируем' in messages[2]
        assert all(update in message for update,message in zip(task['contacts'][0]['updates'],messages))

def test_selected_stars_change_playable_scenario(monkeypatch):
    from apps.api.app import scenario_wizard
    monkeypatch.setattr(scenario_wizard,'complete',lambda *a,**kw:({'description':'В подъезде жилого дома густой дым.'},{'model':'test'}))
    with TestClient(app) as c:
        login(c,'admin')
        payload={'incident_type':'задымление','own_service':'Служба 101','services':['Служба 101'],'victims_state':'no'}
        for mode in ['112','dds']:
            drafts=[]
            for stars in [1,2,3,4,5]:
                r=post(c,'/ai/wizard',{**payload,'mode':mode,'difficulty_stars':stars})
                assert r.status_code==200,r.text
                draft=r.json()['data'];assert draft['difficulty_stars']==stars
                drafts.append(draft['tasks'][0])
                assert post(c,'/tickets',draft).status_code==200
            assert drafts[0]['limit_seconds']>drafts[-1]['limit_seconds']
            assert len(drafts[-1]['criteria'])>len(drafts[0]['criteria'])
            if mode=='dds':
                assert drafts[0]['initial_card']['house'] and not drafts[-1]['initial_card']['house']
                house=drafts[-1]['expected_card']['house']
                caller=next(x for x in drafts[-1]['contacts'] if x['id']=='caller')
                assert house in caller['questions'][0]['answer']
                assert 'задерживаемся' in drafts[-1]['service_events'][0]['text']
            else:
                assert 'Адрес:' in drafts[0]['intro'] and 'Адрес:' not in drafts[-1]['intro']
                assert any(c.get('expected')=='access' and c['kind']=='question' for c in drafts[-1]['criteria'])
