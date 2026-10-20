"""Explainable five-star difficulty from facts known before the lesson."""
import re


def legacy_level(stars: int) -> str:
    return 'Базовый' if stars <= 2 else 'Средний' if stars == 3 else 'Сложный'


def assess_wizard(config, facts, services):
    reasons = []
    if config.victims_state == 'unknown':
        reasons.append('сведения о пострадавших нужно уточнить')
    elif config.victims_state == 'yes':
        reasons.append('есть пострадавшие')
        if config.victims_count >= 3:
            reasons.append('несколько пострадавших')
    if len(set(services)) >= 2:
        reasons.append('нужна координация служб')
    if len(set(services)) >= 3:
        reasons.append('задействованы три и более службы')
    if config.animals:
        reasons.append('есть пострадавшие животные')
    evidence = ' '.join([config.incident_type, facts.get('description', ''), *facts.get('traits', [])]).casefold()
    if re.search(r'газ|провод|контактн|открытое пламя|заблок|нет доступа|сход.*рельс', evidence):
        reasons.append('есть дополнительный опасный фактор')
    stars = min(5, 1 + len(reasons))
    reason = '; '.join(reasons) if reasons else 'обстоятельства понятны, дополнительных факторов нет'
    return stars, reason


DIFFICULTY_HINTS={
    1:'Одна понятная ситуация: принять заявку, получить результат и закрыть карточку.',
    2:'К обычному ходу работ добавлено одно уточнение у заявителя или бригады.',
    3:'Несколько последовательных докладов; изменения нужно отразить в карточке.',
    4:'Возникает задержка бригады: уточните адрес и доступ, зафиксируйте решение.',
    5:'Возникают несколько связанных обстоятельств; сопоставьте доклады бригады и другой службы.'}

def apply_difficulty(ticket, facts, stars):
    """Explicit author choice changes playable facts, questions, pacing and rubric together."""
    task=ticket['tasks'][0]
    ticket.update(difficulty_stars=stars,difficulty=legacy_level(stars),difficulty_reason=DIFFICULTY_HINTS[stars])
    address=f"{facts['city']}, {facts['street']}, дом {facts['house']}"
    if task['mode']=='112':
        task['limit_seconds']={1:420,2:360,3:300,4:240,5:180}[stars]
        if stars==1:
            task['intro']=f"{facts['description']} Адрес: {address}. {facts['address_note']} Заявитель: {facts['caller_name']}. {facts['victims']}"
        elif stars==2:task['intro']=f"{facts['description']} Адрес: {address}."
        required=['address','victims'] if stars>=3 else ['victims'] if stars==2 else []
        if stars>=4:required+=['access']
        if stars==5:required+=['phone','details']
        for key in required:
            q=next(q for q in task['questions'] if q['id']==key);q['required']=True
            task['criteria'].append({'id':'clarify-'+key,'kind':'question','expected':key,'label':q['question'],'weight':10,'skill':'Уточнение сведений'})
    else:
        # All DDS criteria refer to actions available in the read-only received card.
        # Source selection is part of generated_dds; difficulty changes pacing, not truth.
        task['limit_seconds']=300
        delays={1:[35,80,125,170],2:[30,75,120,165],3:[25,65,105,145],4:[25,75,125,175],5:[25,85,145,205]}[stars]
        calls=[event for event in task['service_events'] if event.get('kind')=='incoming_call']
        for event,delay in zip(calls,delays):event['after']=delay
    task['criteria']=[c for c in task['criteria'] if c['kind']!='time']
    task['criteria'].append({'id':'time','kind':'time','label':f"Учебный срок: {task['limit_seconds']} секунд",'expected':task['limit_seconds'],'weight':10,'skill':'Время'})
