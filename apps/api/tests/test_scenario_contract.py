from copy import deepcopy
from types import SimpleNamespace
import pytest
from apps.api.app.dds_scenarios import generated_dds
from apps.api.app.scenario_contract import validate_scenario
from apps.api.app.ticket_difficulty import apply_difficulty
from apps.api.app.schemas import TicketData


def draft(source='auto', stars=3, services=None, own='Служба 101', incident='Пожар'):
    config=SimpleNamespace(own_service=own, incident_type=incident, access_source=source,
        services=services or [own,'Служба 103'],district='Район',mode='dds')
    facts={'title':'Пожар во дворе','city':'Москва','street':'улица Ленина','house':'13',
        'caller_name':'Иван Иванов','phone':'+7 (900) 000-00-01','description':'Во дворе горит контейнер.',
        'victims':'Пострадавших нет.','victims_state':'no','address_note':'Въезд через двор справа, у дома 13.',
        'difficulty_stars':stars,'difficulty_reason':'Учебный случай','traits':[]}
    ticket=generated_dds(config,facts,{'model':'test'}).model_dump()
    apply_difficulty(ticket,facts,stars)
    return TicketData.model_validate(ticket).model_dump()


@pytest.mark.parametrize('source',['card','service_history','caller','unknown'])
@pytest.mark.parametrize('stars',range(1,6))
def test_every_source_and_difficulty_is_playable(source,stars):
    ticket=draft(source,stars)
    task=ticket['tasks'][0]
    assert validate_scenario(task)==[]
    assert task['initial_card']['house']=='13'
    assert not any(c['kind']=='field' for c in task['criteria'])
    stages=task['scenario']['stages']
    assert stages[1]['id']=='approach' and stages[1]['status']==''
    assert stages[2]['id']=='arrived' and stages[2]['status']=='Прибытие'
    assert all(c['phone'] for c in task['contacts'])
    assert len([c for c in task['criteria'] if c['required_record']])==6


def test_other_service_source_is_an_actual_visible_record():
    task=draft('service_history')['tasks'][0]
    access=task['scenario']['access']
    event=next(e for e in task['service_events'] if e['id']==access['report_id'])
    assert event['service']=='Служба 103' and event['after']==0
    assert event['comment']==access['answer']
    assert 'отключено электроснабжение' not in str(task)
    assert all('service' not in e for e in task['service_events'] if e['kind']=='incoming_call')


def test_missing_source_is_explicit_and_not_a_hidden_route():
    task=draft('unknown')['tasks'][0]
    assert task['initial_card']['address_note']=='Сведений о подъезде нет.'
    assert task['scenario']['access']['answer']=='Сведений о подъезде нет.'
    caller=next(c for c in task['contacts'] if c['id']=='caller')
    assert caller['questions'][0]['answer']=='Мне неизвестен удобный подъезд.'
    assert 'Въезд через двор справа' not in str(task)


def test_access_source_needs_another_service():
    with pytest.raises(ValueError,match='вторую службу'):
        draft('service_history',services=['Служба 101'])


def test_auto_stars_choose_a_reachable_source():
    assert draft(stars=3)['tasks'][0]['scenario']['access']['source']=='card'
    assert draft(stars=4)['tasks'][0]['scenario']['access']['source']=='caller'
    assert draft(stars=5)['tasks'][0]['scenario']['access']['source']=='service_history'
    assert draft(stars=5,services=['Служба 101'])['tasks'][0]['scenario']['access']['source']=='caller'


@pytest.mark.parametrize('mutation',[
    lambda t:t['service_events'].pop(0),
    lambda t:t['service_events'][0].update(after=60),
    lambda t:t['service_events'][1].update(status='Прибытие'),
    lambda t:t['scenario']['stages'][1].update(status='Прибытие'),
    lambda t:t['initial_card'].update(house=''),
    lambda t:t['criteria'][3].update(report_id='missing'),
    lambda t:t['criteria'].append({'kind':'field','field':'house'}),
    lambda t:t['contacts'][0].update(phone=''),
    lambda t:t['service_events'][2].update(after=0),
    lambda t:t['service_events'][2].update(text='Несвязанный факт'),
    lambda t:t['scenario']['access'].update(answer='Выдуманный маршрут'),
])
def test_inconsistent_drafts_cannot_publish(mutation):
    task=deepcopy(draft('service_history')['tasks'][0]);mutation(task)
    assert validate_scenario(task)


def test_written_and_spoken_evidence_are_separate():
    task=draft()['tasks'][0]
    records=[c for c in task['criteria'] if c['required_record']]
    assert all(c['evidence_source']=='written' for c in records)
    assert all(c['report_id'] and c['stage_id'] for c in records if c['id']!='accept-record')
    speech=next(c for c in task['criteria'] if c['id']=='access-speech')
    assert speech['evidence_source']=='speech' and not speech['required_record']


def test_medical_service_never_gets_electricity_or_fire_outcome():
    task=draft(own='Служба 103',incident='Пожар')['tasks'][0]
    reports=' '.join(s['report'] for s in task['scenario']['stages'])
    assert 'Очаг ликвидирован' not in reports and 'электроснабжение' not in reports
    assert 'медицинская помощь' in reports


def test_legacy_tasks_remain_compatible():
    assert validate_scenario({'mode':'dds','criteria':[]})==[]


def test_changed_card_invalidates_the_derived_scenario():
    task=draft()['tasks'][0]
    task['initial_card']['description']='На месте другое происшествие.'
    assert any('пересоздайте' in e for e in validate_scenario(task))


def test_elevator_fault_does_not_invent_trapped_people():
    from apps.api.app.dds_scenarios import work_reports
    config=SimpleNamespace(own_service='ДДС района',incident_type='Поломка лифта')
    reports=work_reports(config,{'description':'В доме не работает лифт. Пустая кабина стоит на первом этаже.'})
    assert 'Люди освобождены' not in str(reports)


def test_smoke_without_flames_does_not_turn_into_fire():
    from apps.api.app.dds_scenarios import work_reports
    config=SimpleNamespace(own_service='Служба 101',incident_type='Задымление')
    reports=work_reports(config,{'description':'Из мусоропровода идёт дым. Открытого пламени не видно.'})
    assert 'очаг' not in str(reports) and 'источник дыма' in str(reports)


def test_unknown_victims_does_not_invent_confirmed_casualties():
    from apps.api.app.dds_scenarios import work_reports
    config=SimpleNamespace(own_service='Служба 103',incident_type='Пожар')
    reports=work_reports(config,{'victims_state':'unknown'})
    assert 'Осматриваем пострадавших' not in str(reports)


@pytest.mark.parametrize('source',['card','service_history','caller','unknown'])
def test_author_can_rebuild_after_editing_card_without_losing_facts(source):
    from apps.api.app.scenario_contract import rebuild_scenario
    old=draft(source)['tasks'][0]
    old['initial_card'].update(house='21А',description='В подвале дома сильный дым.',name='Анна Иванова',
                              incident_type='Задымление',victims='unknown',custom_note='Авторское поле')
    old['contacts'][0].update(voice_gender='female',voice_tts='piper-irina',call_audio={'old':'stale.wav'})
    original=deepcopy(old)
    result=rebuild_scenario(old,4)
    assert old==original
    for key in ('house','description','name','incident_type','victims','custom_note'):
        assert result['initial_card'][key]==old['initial_card'][key]
    assert result['id']==old['id'] and result['title']==old['title']
    assert result['scenario']['access']['source']==source
    assert validate_scenario(result)==[]
    assert result['contacts'][0]['voice_tts']=='piper-irina'
    assert result['contacts'][0]['call_audio']=={}
    assert result['scenario']['stages'][1]['status']==''
    assert result['scenario']['stages'][2]['status']=='Прибытие'
    assert 'Очаг ликвидирован' not in str(result['scenario']['stages'])
    assert '21А' in result['scenario']['facts']['address']
    assert result['scenario']['routing']


def test_rebuild_propagates_new_route_to_both_history_and_criteria():
    from apps.api.app.scenario_contract import rebuild_scenario
    old=draft('service_history')['tasks'][0]
    old['initial_card']['address_note']='Въезд слева через арку, рядом с аптекой.'
    result=rebuild_scenario(old,5)
    answer=result['scenario']['access']['answer']
    assert answer=='Въезд слева через арку, рядом с аптекой.'
    assert result['service_events'][0]['comment']==answer
    assert next(c for c in result['criteria'] if c['id']=='access-speech')['expected']==answer
    assert result['initial_card']['address_note']=='Сведения о подъезде — в истории другой службы.'


def test_rebuild_rejects_incomplete_or_impossible_draft():
    from apps.api.app.scenario_contract import rebuild_scenario
    old=draft()['tasks'][0];old['initial_card']['house']=''
    with pytest.raises(ValueError,match='полный адрес'):rebuild_scenario(old,3)
    old=draft('service_history')['tasks'][0];old['services']=[old['own_service']]
    with pytest.raises(ValueError,match='вторую службу'):rebuild_scenario(old,3)


@pytest.mark.parametrize('updates',[
    {'victims':'yes','victims_count':'2'}, {'victims_count':'6'}, {'traits':['Газифицированный дом']},
    {'blocked':'yes'}, {'medical_refusal':'yes'}, {'victims_absent':True},
    {'region':'Московская область'}, {'object':'Строительный объект'}, {'culture_list':True},
])
def test_routing_and_casualty_edits_require_rebuild(updates):
    from apps.api.app.scenario_contract import rebuild_scenario
    old=draft()['tasks'][0]
    old['initial_card'].update(updates)
    assert any('условия назначения' in e for e in validate_scenario(old))
    rebuilt=rebuild_scenario(old,3)
    assert validate_scenario(rebuilt)==[]
    for key,value in updates.items():assert rebuilt['initial_card'][key]==value


@pytest.mark.parametrize('contact_id',['caller','service-0'])
def test_stage_report_cannot_be_misattributed_to_caller_or_other_service(contact_id):
    task=draft()['tasks'][0]
    task['service_events'][0]['contact_id']=contact_id
    assert any('контакта бригады' in e for e in validate_scenario(task))


@pytest.mark.parametrize('incident,required',[
    ('пожар: мусор','мусор'),('пожар: квартира','квартир'),('пожар: балкон','балкон'),
    ('задымление','дым'),('Застревание в лифте','лифт'),('Прорыв трубы','труб'),
    ('Отсутствие воды','прекратилась подача воды'),
])
def test_classifier_subtypes_have_concrete_matching_observations(incident,required):
    from apps.api.app.scenario_facts import scene_seed,scene_matches
    seed=scene_seed(incident)
    assert required in seed.casefold() and scene_matches(incident,[],seed)
    assert 'Очевидец сообщает о происшествии' not in seed


def test_fire_subtype_cannot_silently_change_object():
    from apps.api.app.scenario_facts import scene_seed,scene_matches
    assert not scene_matches('пожар: мусор',[],scene_seed('пожар: квартира'))
    assert not scene_matches('пожар: балкон',[],'Очевидец сообщает о происшествии: пожар: балкон.')
    assert scene_seed('Совсем неизвестное происшествие')==''


@pytest.mark.parametrize('description',[
    'В подъезде жилого дома дым.', 'На улице столкнулись два автомобиля.', 'Во дворе горит мусор.',
])
def test_generated_access_directions_are_actionable(description):
    from apps.api.app.scenario_facts import enrich_facts
    facts={'description':description}
    config=SimpleNamespace(incident_type='пожар',traits=[],animals=False)
    enrich_facts(facts,config)
    note=facts['address_note']
    assert any(word in note for word in ('справа','слева','правой'))
    assert any(word in note for word in ('ворота','воротами','переходом'))


def test_parked_cars_do_not_move_courtyard_incident_to_roadside():
    from apps.api.app.scenario_facts import enrich_facts
    facts={'description':'Во дворе горит мусор в контейнере, рядом припаркованы автомобили.'}
    enrich_facts(facts,SimpleNamespace(incident_type='пожар: мусор',traits=[],animals=False))
    assert facts['object']=='Дворовая территория'
    assert 'Въезд во двор' in facts['address_note']
    assert 'обочины' not in facts['address_note']
