"""A single explicit scenario supplies the DDS card, sources, calls and rubric."""
import re
import secrets
from .schemas import TicketData
from .scenario_facts import phone
from .scenario_contract import scenario_fact_snapshot


def work_reports(config, facts):
    """Define fictional training outcomes before writing dialogue; never borrow another service's work."""
    service = config.own_service.casefold()
    incident = config.incident_type.casefold()
    if '103' in service or 'скор' in service or 'медицин' in service:
        if facts.get('victims_state') == 'no':
            return ('Проверяем место вызова; людей, которым нужна медицинская помощь, не обнаружили.',
                    'Проверка завершена, обращений за медицинской помощью на месте нет.')
        if facts.get('victims_state') != 'yes':
            return ('Осматриваем место вызова и уточняем, кому требуется медицинская помощь.',
                    'Проверка места вызова завершена. Результаты обследования переданы диспетчеру. Дополнительных вызовов с этого адреса пока нет.')
        return ('Осматриваем пострадавших и оказываем медицинскую помощь.',
                'Осмотр и помощь на месте завершены. Результаты осмотра переданы диспетчеру; сведений о госпитализации пока нет.')
    if '102' in service or 'полиц' in service:
        return ('Обеспечиваем порядок на месте, опрашиваем очевидцев и уточняем обстоятельства.',
                'Первичные действия завершены, сведения очевидцев зафиксированы. Материал передан для дальнейшей проверки.')
    if '104' in service or 'газ' in service:
        return ('Проверяем газовое оборудование и ограничиваем доступ к опасному участку.',
                'Проверка завершена, опасный участок изолирован. Дальнейшие работы переданы профильной службе.')
    if ('101' in service or 'пожар' in service or 'спас' in service) and re.search('пожар|дым|задым|гор', incident):
        if re.search('дым|задым',incident) and not re.search('пожар|горит|открытое пламя',facts.get('description','').casefold()):
            return ('Проводим разведку, устанавливаем источник дыма и проверяем место задымления.',
                    'Источник дыма устранён, место проверено. Распространения задымления не обнаружено.')
        return ('Проводим разведку места пожара и работы по ликвидации очага.',
                'Очаг ликвидирован, проверка места завершена. Открытого горения и угрозы распространения нет.')
    if 'лифт' in incident:
        occupied=bool(re.search(r'(?:люди|человек|пассажир|реб[её]нок|ребята|двое|трое|жител).*?(?:кабин|лифт|застр)|(?:кабин|лифт).*?(?:люди|человек|пассажир|реб[её]нок|ребята|двое|трое)|застревание в лифте', facts.get('description','').casefold()+' '+incident))
        if occupied:
            return ('Проводим освобождение людей из остановившегося лифта.',
                    'Люди освобождены. Лифт остановлен до проверки обслуживающей организацией.')
        return ('Обследуем неисправный лифт; его использование приостановлено.',
                'Обследование завершено. Лифт остановлен до проверки обслуживающей организацией.')
    if re.search('отключ|отсутств|нет ',incident) and re.search('вод|водоснабж',incident):
        return ('Проверяем участок водоснабжения и устанавливаем причину отсутствия воды.',
                'Проверка завершена, причина отключения установлена. Заявка на восстановление передана обслуживающей организации.')
    if re.search('вод|труб|затоп|канализ', incident):
        return ('Локализуем аварийный участок и устраняем поступление воды.',
                'Поступление воды прекращено, аварийный участок локализован. Восстановительные работы переданы обслуживающей организации.')
    if re.search('электр|энерг|освещ', incident):
        return ('Проверяем повреждённый участок электроснабжения и обеспечиваем безопасность работ.',
                'Проверка завершена, повреждённый участок изолирован. Заявка на восстановление передана профильной службе.')
    return (f'Обследуем место происшествия «{config.incident_type}» и фиксируем выявленные обстоятельства.',
            'Обследование завершено, сведения зафиксированы и переданы ответственной службе для дальнейшей работы.')


def default_brigade_reports(config, facts):
    working, done = work_reports(config, facts)
    return [f'Приняли заявку по происшествию «{config.incident_type}», выезжаем к месту.',
            'Едем к адресу. Уточните удобный подъезд к месту происшествия.',
            'Прибыли к указанному адресу. Находимся на месте происшествия.', working, done]


def generated_dds(config, facts, meta, reports=None):
    address = f"{facts['city']}, {facts['street']}, дом {facts['house']}"
    services = list(dict.fromkeys([config.own_service] + [s.strip() for s in config.services if s.strip()]))
    # Free model reports are intentionally not accepted: all texts must come from the same plan.
    reports = default_brigade_reports(config, facts)
    stars = facts.get('difficulty_stars', 1) or 1
    source = getattr(config, 'access_source', 'auto') if getattr(config,'mode','dds')=='dds' else 'card'
    other = next((s for s in services if s != config.own_service), '')
    if source == 'auto':
        source = 'service_history' if stars >= 5 and other else 'caller' if stars >= 4 else 'card'
    if source == 'service_history' and not other:
        raise ValueError('Для сведений из истории другой службы добавьте вторую службу.')
    known_access = facts.get('address_note', '').strip() or 'Подъезд к месту со стороны улицы; въезд свободен.'
    answer = 'Сведений о подъезде нет.' if source == 'unknown' else known_access
    card = {'name': facts['caller_name'], 'phone': facts.get('phone') or phone(), 'city': facts['city'],
            'area': config.district, 'street': facts['street'], 'house': facts['house'],
            'description': facts['description'] + ' ' + facts['victims'],
            'incident_type': config.incident_type, 'victims': facts['victims_state']}
    card.update({k: facts[k] for k in ['country','region','district','area','object','caller_status','entrance','floor','apartment','code','traits'] if k in facts})
    card.update(contact_phone=card['phone'], site_phone=card['phone'])
    if facts.get('victims_state')=='yes':
        card['victims_count']=str(facts.get('victims_count') or getattr(config,'victims_count','') or '')
    card['address_note'] = answer if source in ('card','unknown') else ('Сведения о подъезде — в истории другой службы.' if source == 'service_history' else 'Подъезд уточните у заявителя.')
    stages = [{'id': name, 'status': status, 'report': report, 'report_id': 'report-' + name}
              for name, status, report in zip(['dispatch','approach','arrived','working','done'],
                ['Начало реагирования','','Прибытие','Проведение работ','Работы завершены'], reports)]
    access = {'source': source, 'answer': answer, 'service': other if source == 'service_history' else '',
              'report_id': 'access-source' if source == 'service_history' else '', 'available_after': 0}
    contacts = [{'id':'brigade','name':'Старший учебной бригады','kind':'brigade','phone':'1001',
                 'response':f'Задание принято: {address}. {reports[0]}','updates':reports[1:]},
                {'id':'caller','name':facts['caller_name'],'kind':'caller','phone':card['phone'],
                 'response':f"Обращение в 112: {facts['description']} Адрес: {address}. {facts['victims']}",
                 'questions':[{'id':'access','question':'Как подъехать к месту происшествия?',
                               'answer':known_access if source in ('caller','card') else 'Мне неизвестен удобный подъезд.'}]}]
    events = []
    for i, service in enumerate(s for s in services if s != config.own_service):
        note = known_access if source == 'service_history' and service == other else 'Карточка получена. Сведения переданы ответственному диспетчеру нашей службы.'
        contacts.append({'id':f'service-{i}','name':'Диспетчер '+service,'kind':'service','service':service,
                         'phone':str(1002+i),'response':note,'questions':[{'id':'access','question':'Что известно о подъезде?',
                          'answer':known_access if source == 'service_history' and service == other else 'Подтверждённых сведений о подъезде у нашей службы нет.'}]})
        if source == 'service_history' and service == other:
            events.append({'id':'access-source','report_id':'access-source','stage_id':'access-source','kind':'service_report',
                           'after':0,'service':service,'status':'Комментарий','comment':note,'text':note,
                           'who':'Диспетчер '+service,'unit':'Учебный наряд 2'})
    for stage, delay in zip(stages[1:], [25,65,105,145]):
        events.append({'id':stage['report_id'],'report_id':stage['report_id'],'stage_id':stage['id'],
                       'status':stage['status'],'after':delay,'kind':'incoming_call','contact_id':'brigade',
                       'trigger_contact':'brigade','who':contacts[0]['name'],'text':stage['report']})
    criteria = [{'id':'accept','kind':'status','label':'Карточка принята своей службой','expected':'Принята','weight':10,'critical':True,'skill':'Принятие карточки'},
                {'id':'dispatch','kind':'contact','label':'Связь со старшим бригады','expected':'brigade','weight':10,'skill':'Организация реагирования'}]
    for stage in stages:
        if stage['status']:
            criteria.append({'id':'status-'+stage['id'],'kind':'status','label':stage['status'],'expected':stage['status'],
                             'weight':5,'skill':'Статусы ДДС','stage_id':stage['id'],'report_id':stage['report_id'],'status':stage['status'],'evidence_source':'service_reports'})
        criteria.append({'id':'record-'+stage['id'],'kind':'manual','label':'Запись события: '+(stage['status'] or 'Уточнение подъезда'),
                         'expected':stage['report'] if stage['id'] != 'approach' else 'Бригада уточнила подъезд. Переданы сведения: '+answer,
                         'weight':8,'skill':'Комментарии ДДС','evidence_source':'written','required_record':True,
                         'stage_id':stage['id'],'report_id':stage['report_id'],'status':stage['status']})
    criteria.append({'id':'access-speech','kind':'manual','label':'Бригаде переданы доступные сведения о подъезде',
                     'expected':answer,'weight':15,'skill':'Передача сведений','evidence_source':'speech',
                     'stage_id':'approach','report_id':'report-approach'})
    task = {'id':secrets.token_hex(8),'title':facts['title'][:200],'mode':'dds','category':config.incident_type[:100],
            'intro':f"Получена карточка: {address}. {card['description']} Примите решение и организуйте реагирование.",
            'phone':card['phone'],'own_service':config.own_service,'services':services,'initial_card':card,
            'type_options':[config.incident_type],'expected_card':{},'questions':[],'contacts':contacts,
            'criteria':criteria,'limit_seconds':300,'source':'Учебный сценарий: '+meta['model'],
            'method_note':'Проверьте обстоятельства происшествия и назначение служб. Статусы, письменные записи и передача сведений оцениваются отдельно.',
            'scenario':{'version':2,'facts':{'incident':config.incident_type,'address':address,'description':card['description'],
                        'victims':facts['victims'],'service':config.own_service,**scenario_fact_snapshot(card)},'access':access,'stages':stages},'service_events':events}
    return TicketData(title=facts['title'][:200],description=facts['description'][:4000],
                      difficulty_stars=stars,difficulty_reason=facts.get('difficulty_reason',''),tasks=[task])
