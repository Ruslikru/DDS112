"""Small, portable DDS conversation policy. State changes remain in the application."""
import json
import re
import time


def closing(text):
    words=text.casefold().replace('ё','е').strip()
    if '?' in words or re.search(r'не\s+(?:прощ|клад|веш|отключ)|пока\s+(?:стой|жд|не|ост)',words):
        return None
    if re.search(r'(?:позвон|перезвон|сообщ|долож|набер).{0,45}(?:как|когда|по прибыт|после)',words):
        return 'Понял. Как будет изменение, перезвоним.'
    if re.search(r'до\s*свидан|до\s*свидень|до связи|всего добр|на этом все',words) or re.fullmatch(r'(?:ну\s+)?пока[.!\s]*',words):
        return 'Понял, до связи.'
    return None


def acknowledge_report(text, report):
    words=text.casefold().replace('ё','е');report=report.casefold().replace('ё','е')
    if '?' in words or re.search(r'\bне\b|почему|когда|сколько|уточни|повтори|подожд|не веш',words):return None
    if re.search(r'не (?:прибы|соответству|заверш|устран)|опасность (?:не|сохраня)',report):return None
    done=bool(re.search(r'заверш|устран|ликвид|потуш|очищ',report))
    arrived=bool(re.search(r'прибы|приеха|соответству.{0,15}заяв',report))
    accepted=bool(re.search(r'принял|приняла|понял|поняла|зафиксир|спасибо|молодц|возвращ|\bждем\b.{0,30}баз|приступайте|работайте|продолжайте работ',words))
    if not accepted:return None
    if done:return 'Понял, возвращаемся на базу. До связи.'
    if arrived:return 'Принято, приступаем к работам. Доложим о завершении.'
    return None


def short_incoming_reply(text, report, turns):
    """Approach clarification is one answer; other reports allow at most two operator turns."""
    words=text.casefold().replace('ё','е');report=report.casefold().replace('ё','е')
    if re.search(r'не (?:вешай|отключай|клади)|подожд|оставайтесь на линии',words):return None
    access=bool(re.search(r'подъезд|подъехать|подьезд|проехать|проезд|заезд|подход|как добрать',report))
    if access:
        if re.search(r'местн|людей|жител|прохож|спрос|карт[уыае]|навигатор',words):
            return 'Ладно, понял. Уточним дорогу на месте. До связи.'
        if re.search(r'не знаю|неизвест|нет (?:данных|сведений|информации)|данных нет|сведений нет|информации нет|не могу (?:сказать|подсказать|уточнить)',words):
            return 'Понял, тогда сами найдём подъезд. До связи.'
        if re.search(r'справ|слева|правой|левой|сторон|подъезд|подьезд|двор|арку|ворот|въезд|заезд|объезд|обьезд|проезж|поверн|поворач|обогн|второ|перв|свобод|открыт|закрыт|перекрыт|пешком|сзади|спереди',words):
            return 'Понял, подъезд уточнили. Дальше сориентируемся на месте. До связи.'
        if turns>=2:return 'Понял, уточним подъезд на месте. До связи.'
        return ''
    if turns>=2:return 'Понял вас. Продолжаем по обстановке, об изменениях доложим. До связи.'
    return None


def accepted_response(text):
    if re.search(r'не можем|не прин|не выед|уточните|повторите|непонят|не понял|нет возможности',text,re.I):return False
    return bool(re.search(r'приня|получ|зарегистр|выезж|выех|направ|отправ|приступ|подтвержда',text,re.I))


def reply(text, task, contact, state, options, complete):
    """One inference at most; goodbye and explicit dispatch need none."""
    started=time.perf_counter()
    history=[m for m in state.get('messages',[]) if m.get('contact_id')==contact['id']][-4:]
    contacted=bool(state.get('contact_counts',{}).get(contact['id']))
    all_messages=[m for m in state.get('messages',[]) if m.get('contact_id')==contact['id']]
    incoming_index=next((i for i in range(len(all_messages)-1,-1,-1) if all_messages[i].get('direction')=='incoming'),None)
    current=all_messages[incoming_index+1:] if incoming_index is not None else []
    incoming=incoming_index is not None and not any(m.get('call_end') for m in current)
    def result(intent,answer,end=False,meta=None):
        return {'question_id':intent,'answer':answer,'call_end':end,
                'ai':{**(meta or {}),'seconds':round(time.perf_counter()-started,3),'source':'model' if meta else 'rule'}}
    bye=closing(text)
    if bye:return result('unknown',bye.replace('Понял','Поняла') if contact.get('voice_gender')=='female' else bye,True)
    report=next((m.get('text','') for m in reversed(state.get('messages',[])) if m.get('contact_id')==contact['id'] and m.get('direction')=='incoming'),'')
    acknowledged=acknowledge_report(text,report) if report and incoming else None
    if acknowledged:return result('unknown',acknowledged.replace('Понял','Поняла') if contact.get('voice_gender')=='female' else acknowledged,True)
    if incoming and (contact.get('kind')=='brigade' or contact['id']=='brigade'):
        turns=1+sum(m.get('who','').startswith('Диспетчер') for m in current)
        short=short_incoming_reply(text,report,turns)
        if short is not None:
            end=bool(short)
            answer=short or 'У нас уточнение по подъезду. Есть сведения, с какой стороны удобнее заехать?'
            if contact.get('voice_gender')=='female':answer=answer.replace('Понял','Поняла').replace('понял','поняла')
            return result('unknown',answer,end)
    if not contacted and not incoming and not re.search(r'\bне\b',text,re.I) and re.search(r'примите.{0,25}(?:заявк|вызов)|передаю.{0,25}(?:заявк|вызов)|(?:выезжайте|езжайте|направьте|отправьте|вышлите)',text,re.I):
        accepted=accepted_response(contact['response'])
        return result('dispatch' if accepted else 'unknown',contact['response'],accepted)
    catalog={q['id']:q for q in options}
    normalized=lambda s:re.sub(r'[^а-яёa-z0-9]+',' ',s.casefold()).strip()
    for q in options:
        if q['id']!='dispatch' and normalized(q['question'])==normalized(text):
            return result(q['id'],q['answer'])
    for pattern,intent in [(r'как вас зовут|представьтесь|кто звонит','name'),(r'назовите адрес|какой адрес','address'),(r'^доложите обстановку[.!?\s]*$|вы уже (?:приехали|доехали|прибыли)|где (?:вы|сейчас)|как обстановка','progress'),(r'что произошло|по какому поводу','details')]:
        if re.search(pattern,text,re.I) and intent in catalog:return result(intent,catalog[intent]['answer'])
    # Copy catalog facts verbatim, especially names, addresses and current progress.
    schema={'type':'object','properties':{'action':{'type':'string','enum':['answer','dispatch']},'text':{'type':'string'}},'required':['action','text'],'additionalProperties':False}
    # The current incident report is an anchor, not the model's previous improvisation.
    report=next((m['text'] for m in reversed(state.get('messages',[])) if m.get('contact_id')==contact['id'] and m.get('direction')=='incoming'),contact['response'])
    if not contacted and not incoming:report='Ожидаем новую заявку от диспетчера.'
    words=set(normalized(text).split())
    for q in options:
        qw=set(normalized(q['question']).split())
        if q['id'] not in ('dispatch','progress','name','address','details') and len(words&qw)>=2 and len(words&qw)/max(1,len(qw))>=.7:
            return result(q['id'],q['answer'])
    prompt={'current_report':report[:350],
            'incident':str(task.get('initial_card',{}).get('incident_type') or task.get('category') or '')[:80],
            'history':[{'speaker':m['who'],'text':m['text'][:120]} for m in history[-2:]],'message':text}
    role='старшая бригады' if contact.get('voice_gender')=='female' else 'старший бригады'
    if contact.get('kind')=='service':role='дежурная службы' if contact.get('voice_gender')=='female' else 'дежурный службы'
    if contact.get('kind')=='caller':role='заявительница' if contact.get('voice_gender')=='female' else 'заявитель'
    value,meta=complete(
        f'Ты {role}, отвечаешь диспетчеру по-русски. До 12 слов, от первого лица. '
        'Текущий доклад неизменен: не придумывай прибытие или завершение. '
        'Не повторяй вопрос и препятствие после ответа диспетчера. Стремись завершить короткий деловой разговор. Не меняй роль. При передаче новой заявки action=dispatch, иначе answer. JSON.',
        json.dumps(prompt,ensure_ascii=False),schema,tokens=48,temperature=.2)
    intent='dispatch' if value.get('action')=='dispatch' and not contacted and not incoming else value.get('id','unknown')
    if intent=='dispatch' and (contacted or incoming):intent='unknown'
    if intent in catalog:
        accepted=intent=='dispatch' and accepted_response(catalog[intent]['answer'])
        return result('unknown' if intent=='dispatch' and not accepted else intent,catalog[intent]['answer'],accepted,meta)
    answer=str(value.get('text','')).strip()
    if not answer or len(answer)>600 or re.search('[a-zA-Z]',answer):
        answer='Не совсем понял. Уточните вопрос по нашему происшествию.'
        meta={**meta,'validation':'invalid_reply'}
    if re.search(r'пробк|не можем (?:проехать|выехать)|застрял',report,re.I) and re.search(r'прибыли|приехали|выбрались|проехали|потушили|завершили|не в нашей зоне',answer,re.I):
        answer='Пока стоим в пробке, проехать ещё не удалось.'
        meta={**meta,'validation':'kept_current_report'}
    # Ending a call is a state-machine decision, never a model-generated side effect.
    return result('unknown',answer,False,meta)
