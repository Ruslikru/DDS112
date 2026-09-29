"""A single set of facts supplies the DDS card, contacts, reports and rubric."""
import secrets
from .schemas import TicketData
from .scenario_facts import phone


def default_brigade_reports(config,facts):
    incident=config.incident_type.lower()
    if config.own_service=='Служба 103':
        count=getattr(config,'victims_count',1)
        people=(f"{count} {'пострадавшего' if count%10==1 and count%100!=11 else 'пострадавших' if count%10>=5 or 11<=count%100<=14 else 'пострадавших'}" if facts.get('victims_state')=='yes' else 'пострадавших')
        return [f'Приняли вызов по происшествию «{incident}», выезжаем к месту.',
                'Подъезжаем к адресу. Уточните, свободен ли подъезд для машины скорой помощи.',
                f'Мы на месте, осматриваем {people}. Уточняем состояние и оказываем необходимую помощь.',
                'Осмотр завершён. При необходимости госпитализируем для обследования; сообщаем диспетчеру результат и маршрут.']
    return [f'Приняли заявку по происшествию «{incident}», выезжаем к месту.',
            'Подъезжаем к адресу. Уточните удобный подъезд к месту происшествия.',
            f'Мы на месте. Проверяем обстановку по заявке «{incident}» и приступаем к необходимым действиям.',
            'Основные действия на месте выполнены. Передаём диспетчеру результат и сведения, которые ещё требуют проверки.']


def generated_dds(config,facts,meta,reports=None):
    address=f"{facts['city']}, {facts['street']}, дом {facts['house']}"
    services=list(dict.fromkeys([config.own_service]+[s.strip() for s in config.services if s.strip()]))
    reports=reports or default_brigade_reports(config,facts)
    statuses=['Начало реагирования','Прибытие','Проведение работ','Работы завершены']
    card={'name':facts['caller_name'],'phone':facts.get('phone') or phone(),'city':facts['city'],
          'area':config.district,'street':facts['street'],'house':facts['house'],
          'description':facts['description']+' '+facts['victims'],
          'incident_type':config.incident_type,'victims':facts['victims_state']}
    card.update({k:facts[k] for k in ['country','region','district','area','object','caller_status','entrance','floor','apartment','code','address_note','traits'] if k in facts})
    card.update(contact_phone=card['phone'],site_phone=card['phone'])
    clarify_access=getattr(config,'mode','dds')=='dds' and facts.get('difficulty_stars',1)>=4 and not any(
        sign in ' '.join(facts.get('traits',[])).casefold() for sign in ('доступ свободен','нет доступа','заблокирован'))
    if clarify_access:
        card.update(blocked='unknown',address_note='Доступ к месту пока не уточнён')
    contacts=[{'id':'brigade','name':'Старший учебной бригады','kind':'brigade','phone':'1001',
               'response':f'Задание принято: {address}. {reports[0]}','updates':reports[1:]},
              {'id':'caller','name':facts['caller_name'],'kind':'caller','phone':card['phone'],
               'response':f"Обращение в 112 по поводу: {facts['description']} Адрес: {address}. {facts['victims']}"}]
    if clarify_access:
        contacts[1]['questions']=[{'id':'access','question':'Как подъехать к месту происшествия?',
                                  'answer':facts['address_note']+'. Проезд для машины свободен.'}]
    contacts += [{'id':f'service-{i}','name':s,'kind':'service','service':s,'phone':'',
                 'response':f'Получена карточка: {address}.'} for i,s in enumerate(services) if s!=config.own_service]
    criteria=[{'id':'accept','kind':'status','label':'Карточка принята своей службой','expected':'Принята','weight':15,'critical':True,'skill':'Принятие карточки'},
              {'id':'time','kind':'time','label':'Первичное решение за 30 секунд','expected':30,'weight':10,'skill':'Время'},
              {'id':'dispatch','kind':'contact','label':'Связь со старшим бригады','expected':'brigade','weight':15,'skill':'Организация реагирования'}]
    criteria += [{'id':f'stage-{i}','kind':'status','label':status,'expected':status,'weight':10,'skill':'Статусы ДДС'} for i,status in enumerate(statuses)]
    criteria.append({'id':'comments','kind':'manual','label':'Комментарии соответствуют докладам и действиям',
                     'expected':' | '.join(f'{s}: {r}' for s,r in zip(statuses,reports)),
                     'weight':20,'skill':'Комментарии ДДС'})
    task={'id':secrets.token_hex(8),'title':facts['title'][:200],'mode':'dds','category':config.incident_type[:100],
          'intro':f"Получена карточка: {address}. {card['description']} Примите решение и организуйте реагирование.",'phone':card['phone'],
          'own_service':config.own_service,'services':services,'initial_card':card,'type_options':[config.incident_type],
          'expected_card':{},'questions':[],'contacts':contacts,'criteria':criteria,'limit_seconds':30,
          'source':'Черновик локальной модели: '+meta['model'],
          'method_note':f'Преподаватель проверяет принадлежность службы, адрес и доклады. Подчинённость объекта: {config.affiliation or "не указана"}. Получатели предложены по фактам сценария и настройкам служб.',
          'service_events':[{'after':delay,'kind':'incoming_call','contact_id':'brigade','trigger_contact':'brigade',
                             'who':'Старший учебной бригады','text':f'{address}. {report}'}
                            for delay,report in zip([20,45,70],reports[1:])]}
    return TicketData(title=facts['title'][:200],description=facts['description'][:4000],
                      difficulty_stars=facts.get('difficulty_stars',0),difficulty_reason=facts.get('difficulty_reason',''),tasks=[task])
