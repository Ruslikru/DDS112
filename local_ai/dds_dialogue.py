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


def accepted_response(text):
    if re.search(r'не можем|не прин|не выед|уточните|повторите|непонят|не понял|нет возможности',text,re.I):return False
    return bool(re.search(r'приня|получ|зарегистр|выезж|выех|направ|отправ|приступ|подтвержда',text,re.I))


def reply(text, task, contact, state, options, complete):
    """One inference at most; goodbye and explicit dispatch need none."""
    started=time.perf_counter()
    history=[m for m in state.get('messages',[]) if m.get('contact_id')==contact['id']][-4:]
    contacted=bool(state.get('contact_counts',{}).get(contact['id']))
    incoming=any(m.get('contact_id')==contact['id'] and m.get('direction')=='incoming' for m in state.get('messages',[]))
    def result(intent,answer,end=False,meta=None):
        return {'question_id':intent,'answer':answer,'call_end':end,
                'ai':{**(meta or {}),'seconds':round(time.perf_counter()-started,3),'source':'model' if meta else 'rule'}}
    bye=closing(text)
    if bye:return result('unknown',bye.replace('Понял','Поняла') if contact.get('voice_gender')=='female' else bye,True)
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
        'На предложения объясняй препятствие. Не меняй роль. При передаче новой заявки action=dispatch, иначе answer. JSON.',
        json.dumps(prompt,ensure_ascii=False),schema,tokens=64,temperature=.2)
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
