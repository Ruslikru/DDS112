import re
from datetime import datetime
from .writing import address_checks

SERVICES = ['Служба 101','Служба 102','Служба 103','Служба 104','ДДС района','Мослифт','ЦОДД','Мосводоканал','Деп. ЖКХ','ЦЭМП']
CARD_FIELDS = ['name','caller_status','phone','contact_phone','site_phone','country','region','city','district','area','object','street','house','building','structure','apartment','entrance','floor','code','address_note','description','incident_type','victims','victims_count','traits','medical_refusal','blocked','no_contact','call_lost']
EMPTY_CARD = {**{k:'' for k in CARD_FIELDS},'country':'Россия','region':'Москва','city':'Москва','victims':'unknown','traits':[]}

def normalize(value):
    return re.sub(r'[\s.,()\-]+', '', str(value).lower().replace('ё','е'))

def duration(attempt):
    end = attempt.submitted_at or datetime.now().astimezone().isoformat()
    start = attempt.state.get('accepted_at') or attempt.started_at
    elapsed = (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()
    paused = attempt.state.get('paused_seconds',0)
    if attempt.state.get('mini_started'):
        paused += max(0,datetime.fromisoformat(end).timestamp()-attempt.state['mini_started'])
    if attempt.state.get('pause_at'):
        paused += (datetime.fromisoformat(end)-datetime.fromisoformat(attempt.state['pause_at'])).total_seconds()
    return max(0, int(elapsed-paused))

def routes(task, card):
    result=[]
    for rule in task.get('routing',[]):
        if rule.get('type') and rule['type'] != card.get('incident_type'): continue
        if not set(rule.get('traits',[])).issubset(card.get('traits',[])): continue
        if rule.get('victims') and rule['victims'] != card.get('victims'): continue
        for s in rule.get('services',[]):
            if s not in result: result.append(s)
    return result

def allowed_statuses(history):
    last=history[-1]['status'] if history else 'Получена службой'
    if last in ['Добавлена','Получена службой']: return ['Принята','Не принята']
    if last=='Не принята': return ['Принята']
    order=['Принята','Начало реагирования','Прибытие','Проведение работ','Работы завершены']
    if last in order[:-1]: return order[order.index(last)+1:]+['Отказ от выполнения работ']
    return []

def assess(attempt):
    task=attempt.snapshot
    state=attempt.state
    results=[]
    for c in task['criteria']:
        kind=c['kind']; actual=None; passed=False
        if kind=='field':
            actual=attempt.card.get(c['field'],'')
            expected=c['expected']
            if isinstance(expected,list): passed=set(actual if isinstance(actual,list) else [actual])==set(expected)
            else: passed=normalize(actual)==normalize(expected)
        elif kind=='question':
            actual=c['expected'] in state.get('asked',[]); passed=actual
        elif kind=='service':
            actual=list(state.get('services',{})); passed=c['expected'] in actual
        elif kind=='status':
            actual=[h['status'] for h in state.get('services',{}).get(task['own_service'],[])]
            passed=c['expected'] in actual
        elif kind=='time':
            if task['mode']=='dds':
                history=state.get('services',{}).get(task['own_service'],[])
                ack=next((h for h in history if h['status'] in ['Принята','Не принята']),None)
                actual=state.get('ack_seconds',round((datetime.fromisoformat(ack['at'])-datetime.fromisoformat(attempt.started_at)).total_seconds())) if ack else None
            else: actual=state.get('fill_seconds',duration(attempt))
            passed=actual is not None and actual<=float(c['expected'])
        elif kind=='contact':
            actual=state.get('contacts',[]); passed=c['expected'] in actual
        elif kind=='validation':
            actual=state.get('validation',{}).get('comment',''); passed=None
        elif kind=='manual':
            actual=attempt.card.get('description','') if not c['field'] else attempt.card.get(c['field'],'')
            if task['mode']=='dds': actual='; '.join(h.get('comment','') for h in state.get('services',{}).get(task['own_service'],[]))+' | Связь: '+'; '.join(m.get('text','') for m in state.get('messages',[]) if m.get('who','').startswith('Диспетчер'))
            passed=None
        results.append({**c,'actual':actual,'passed':passed})
    dialogue=state.get('dialogue',[]) if task['mode']=='112' else state.get('messages',[])
    spoken=[m for m in dialogue if m.get('who','').startswith(('Оператор','Диспетчер'))]
    if spoken and not any(c['id']=='phone_conversation' for c in results):
        expected=task.get('expected_card',{}) or task.get('initial_card',{})
        results.append({'id':'phone_conversation','kind':'manual','field':'conversation','label':'Телефонный разговор: сведения и передача заявки','skill':'Опрос и передача информации','weight':20,'critical':False,'actual':'\n'.join(m.get('who','')+': '+m.get('text','') for m in spoken),'expected':'Оцените только реплики ученика: для 112 уточнены существенные сведения, для ДДС переданы адрес и обстоятельства. Не требуйте повторно спрашивать сведения, которые заявитель уже сообщил. Не засчитывайте слова абонента как слова ученика. Факты билета: '+str(expected),'passed':None})
    measured=state.get('ack_seconds') if task['mode']=='dds' else state.get('fill_seconds',duration(attempt))
    return score({'criteria':results,'duration':duration(attempt),'norm_seconds':task['limit_seconds'],'measured_seconds':measured,'measurement':'Первичное решение ДДС' if task['mode']=='dds' else 'Заполнение карточки','deviation_seconds':measured-task['limit_seconds'] if measured is not None else None,'text_checks':text_checks(attempt.card.get('description','')+' '+ ' '.join(h.get('comment','') for h in state.get('services',{}).get(task['own_service'],[]))),'assisted':bool(state.get('teacher_assisted')), 'reviews':[], 'address_checks':address_checks(attempt.card,task.get('expected_card',{}))})

def score(result):
    checked=[c for c in result['criteria'] if c['passed'] is not None]
    total=sum(c['weight'] for c in checked)
    result['score']=round(100*sum(c['weight']*c.get('credit',1 if c['passed'] else 0) for c in checked)/total) if total else None
    result['pending']=any(c['passed'] is None for c in result['criteria'])
    result['critical_errors']=sum(c['critical'] and c['passed'] is False for c in result['criteria'])
    result['ai_preliminary']=any(c.get('ai_evaluation') and not c.get('teacher_reviewed') for c in result['criteria'])
    result['passed']=not result['pending'] and result['score'] is not None and result['score']>=70 and not result['critical_errors']
    return result


def text_checks(text):
    """Conservative offline writing hints; not semantic or grammatical grading."""
    issues=[]
    for pattern,label in [(r'([!?.,])\1{2,}', 'Повторяющиеся знаки препинания'),
                          (r'\b([а-яё]+)\s+\1\b', 'Повтор слова'),
                          (r'[а-яё][A-Za-z]|[A-Za-z][а-яё]', 'Смешение латиницы и кириллицы')]:
        for match in re.finditer(pattern,text,re.I):
            issues.append({'message':label,'fragment':match.group(0),'offset':match.start()})
    from .writing import spelling
    return (issues+spelling(text))[:50]
