"""Deterministic authoring gates for the versioned DDS scenario contract.

A published v2 task has a discoverable source for each clarification and a report
for each graded stage. Legacy tasks keep their existing publication rules.
"""
STAGES = [('dispatch','Начало реагирования'),('approach',''),('arrived','Прибытие'),
          ('working','Проведение работ'),('done','Работы завершены')]


def scenario_fact_snapshot(card):
    """Inputs whose edit invalidates future reports or the saved routing decision."""
    from copy import deepcopy
    keys=('incident_type','description','object','traits','city','region','district','area',
          'blocked','medical_refusal','culture_list','victims_absent','classifier_code')
    return {'victims_state':card.get('victims','unknown'),
            'victims_count':str(card.get('victims_count') or ''),
            'routing_inputs':{key:deepcopy(card.get(key)) for key in keys}}


def validate_scenario(task):
    if hasattr(task, 'model_dump'):
        task = task.model_dump()
    scenario = task.get('scenario') or {}
    if not scenario or task.get('mode') != 'dds':
        return []
    errors = []
    if scenario.get('version') != 2:
        return ['Неизвестная версия сценария ДДС.']
    facts=scenario.get('facts')
    card=task.get('initial_card') or {}
    if not isinstance(facts,dict):
        errors.append('Сценарию нужны исходные факты карточки.')
    else:
        address=f"{card.get('city','')}, {card.get('street','')}, дом {card.get('house','')}"
        if any([facts.get('address')!=address,facts.get('description')!=card.get('description'),
                facts.get('incident')!=card.get('incident_type'),facts.get('service')!=task.get('own_service')]):
            errors.append('После изменения фактов карточки пересоздайте связанные доклады и критерии сценария.')
        if any(facts.get(key)!=value for key,value in scenario_fact_snapshot(card).items()):
            errors.append('Изменились пострадавшие или условия назначения служб: пересоздайте события и критерии сценария.')
    stages = scenario.get('stages', [])
    if not isinstance(stages, list) or any(not isinstance(s,dict) for s in stages):
        return ['Нужен список этапов сценария ДДС.']
    if [(s.get('id'),s.get('status')) for s in stages] != STAGES:
        errors.append('Разделите выезд, уточнение подъезда, прибытие, работы и завершение в правильном порядке.')
    if any(not all(isinstance(s.get(k),str) for k in ('id','status','report','report_id')) for s in stages):
        return errors+['Поля этапа должны быть текстовыми.']
    reports = [s.get('report_id') for s in stages]
    if len(set(reports)) != len(reports) or not all(reports):
        errors.append('Каждому этапу нужен уникальный идентификатор доклада.')
    by_stage = {s.get('id'):s for s in stages}
    events = task.get('service_events', [])
    contacts = {c.get('id'):c for c in task.get('contacts', [])}
    if not task.get('initial_card', {}).get('house'):
        errors.append('Во входящей карточке ДДС должен быть указан номер дома: поле недоступно для редактирования.')
    if any(c.get('kind') == 'field' for c in task.get('criteria', [])):
        errors.append('В ДДС нельзя оценивать редактирование недоступных полей входящей карточки.')
    previous_delay = -1
    for stage in stages:
        if not stage.get('report', '').strip():
            errors.append('У каждого этапа должен быть содержательный доклад.')
        if stage.get('id') == 'dispatch':
            if stage.get('report','') not in contacts.get('brigade',{}).get('response',''):
                errors.append('Ответ бригады должен соответствовать докладу о выезде.')
            continue
        matching = [e for e in events if e.get('report_id') == stage.get('report_id')]
        if len(matching) != 1:
            errors.append('Для каждого следующего этапа нужен один доступный входящий доклад.')
            continue
        event = matching[0]
        if event.get('stage_id') != stage.get('id') or event.get('status','') != stage.get('status','') or event.get('text') != stage.get('report'):
            errors.append('Текст и статус события должны совпадать с планом этапа.')
        if event.get('kind') != 'incoming_call' or contacts.get(event.get('contact_id'),{}).get('kind') != 'brigade':
            errors.append('Доклад этапа должен поступать от доступного контакта бригады.')
        try:
            delay = float(event.get('after',0))
        except (ValueError,TypeError):
            delay = -1
        if delay <= previous_delay:
            errors.append('Доклады бригады должны поступать в последовательности этапов.')
        previous_delay = delay
    access = scenario.get('access') or {}
    if not isinstance(access,dict):
        return errors+['Нужно описание источника сведений о подъезде.']
    source = access.get('source')
    answer = access.get('answer','')
    if source not in ('card','service_history','caller','unknown') or not isinstance(answer,str) or not answer.strip():
        errors.append('Укажите источник и ожидаемый ответ об удобном подъезде.')
    elif source in ('card','unknown'):
        if answer not in task.get('initial_card',{}).get('address_note',''):
            errors.append('Сведения о подъезде или их отсутствии должны быть видны во входящей карточке.')
    elif source == 'caller':
        caller = contacts.get('caller',{})
        if not caller.get('phone') or not any(q.get('id') == 'access' and q.get('answer') == answer for q in caller.get('questions',[])):
            errors.append('Заявитель должен быть доступен по телефону и знать ожидаемый ответ о подъезде.')
    elif source == 'service_history':
        matching = [e for e in events if e.get('report_id') == access.get('report_id')]
        service = access.get('service')
        event = matching[0] if len(matching) == 1 else {}
        if not service or service == task.get('own_service') or service not in task.get('services',[]):
            errors.append('Источником подъезда должна быть другая назначенная служба.')
        if (event.get('kind') != 'service_report' or event.get('service') != service
                or event.get('comment') != answer or event.get('after') != 0):
            errors.append('Запись другой службы с ответом должна быть доступна до уточняющего звонка.')
    if access.get('available_after') != 0:
        errors.append('Источник уточнения должен быть доступен с начала задания.')
    for contact in contacts.values():
        if not contact.get('phone'):
            errors.append('Каждый контакт сценария должен иметь доступный учебный телефон.')
    for criterion in task.get('criteria',[]):
        stage_id = criterion.get('stage_id')
        if stage_id:
            stage = by_stage.get(stage_id)
            if not stage or criterion.get('report_id') != stage.get('report_id'):
                errors.append('Критерий ссылается на отсутствующий доклад этапа.')
            elif criterion.get('kind') == 'status' and criterion.get('expected') != stage.get('status'):
                errors.append('Ожидаемый статус критерия должен совпадать со статусом этапа.')
        if criterion.get('required_record') and criterion.get('evidence_source') != 'written':
            errors.append('Обязательная письменная запись должна оцениваться только по записям ученика.')
    for stage in stages:
        if not any(c.get('stage_id') == stage.get('id') and c.get('required_record') for c in task.get('criteria',[])):
            errors.append('Для каждого этапа нужен отдельный критерий оформления письменной записи.')
    return list(dict.fromkeys(errors))


def rebuild_scenario(task, stars):
    """Explicit author action: rebuild only this draft's derived events and rubric.

    Facts in the edited received card are authoritative. Existing attempts are
    never read or changed. Recordings cannot survive a changed spoken script.
    """
    from copy import deepcopy
    from types import SimpleNamespace
    from .dds_scenarios import generated_dds
    from .ticket_difficulty import apply_difficulty
    from .classifier_routing import resolve
    from .schemas import Task

    task=deepcopy(task.model_dump() if hasattr(task,'model_dump') else task)
    if task.get('mode')!='dds':
        raise ValueError('Пересборка событий доступна для карточки ДДС.')
    if stars not in range(1,6):
        raise ValueError('Укажите сложность от 1 до 5 звёзд.')
    card=task.get('initial_card') or {}
    if not all(str(card.get(key,'')).strip() for key in ('city','street','house','name','description','incident_type')):
        raise ValueError('Для пересборки нужны заявитель, описание, тип происшествия и полный адрес.')
    access=(task.get('scenario') or {}).get('access') or {}
    source=access.get('source','auto')
    if source not in ('auto','card','service_history','caller','unknown'):
        raise ValueError('Выберите доступный источник сведений о подъезде.')
    markers={'Сведения о подъезде — в истории другой службы.','Подъезд уточните у заявителя.','Сведений о подъезде нет.'}
    note=str(card.get('address_note') or '').strip()
    if not note or note in markers:
        note=access.get('answer','')
    if not note or note in markers:
        note='Подъезд к месту со стороны улицы; въезд свободен.'
    victims_state=card.get('victims','unknown')
    victims='Пострадавших нет.' if victims_state=='no' else 'Наличие пострадавших неизвестно.'
    if victims_state=='yes':
        victims=f"Пострадавших: {card.get('victims_count')}." if card.get('victims_count') else 'Есть пострадавшие.'
    facts={**card,'title':task['title'],'caller_name':card['name'],'victims_state':victims_state,
           'victims':victims,'address_note':note,'difficulty_stars':stars,'difficulty_reason':''}
    config=SimpleNamespace(mode='dds',own_service=task.get('own_service','ДДС района'),
                           services=task.get('services',[]),incident_type=card['incident_type'],
                           district=card.get('area',''),access_source=source)
    ticket=generated_dds(config,facts,{'model':'редактор'}).model_dump()
    apply_difficulty(ticket,facts,stars)
    rebuilt=ticket['tasks'][0]
    # The card's description already includes the author's casualty information;
    # generation must not append it for a second time or discard other card fields.
    rebuilt['initial_card']={**card,'address_note':rebuilt['initial_card']['address_note']}
    rebuilt['scenario']['facts']['description']=card['description']
    rebuilt['scenario']['facts'].update(scenario_fact_snapshot(rebuilt['initial_card']))
    rebuilt['scenario']['routing']=resolve(rebuilt['initial_card'])
    rebuilt['id']=task['id']
    rebuilt['intro']=f"Получена карточка: {rebuilt['scenario']['facts']['address']}. {card['description']} Примите решение и организуйте реагирование."
    for key in ('workplace','caller_gender','onboarding','origin','validation_note'):
        if key in task:rebuilt[key]=task[key]
    old_contacts=task.get('contacts',[])
    for contact in rebuilt['contacts']:
        old=next((c for c in old_contacts if c.get('kind')==contact['kind'] and
                  (c.get('service')==contact.get('service') if contact['kind']=='service' else c.get('id')==contact['id'])),None)
        if old:
            for key in ('voice_tts','voice_gender'):
                if key in old:contact[key]=old[key]
    errors=validate_scenario(rebuilt)
    if errors:raise ValueError('; '.join(errors))
    return Task.model_validate(rebuilt).model_dump()
