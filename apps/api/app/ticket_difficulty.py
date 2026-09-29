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
    1:'Все исходные сведения доступны сразу, увеличен учебный срок.',
    2:'Адрес известен сразу; нужно уточнить сведения о людях и обстоятельствах.',
    3:'Самостоятельный сбор сведений и стандартная последовательность действий.',
    4:'Нужно дополнительно уточнить адрес и доступ к месту, зафиксировать ответы.',
    5:'Неполная исходная информация, дополнительные уточнения и задержка бригады.'}

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
        task['limit_seconds']={1:90,2:60,3:45,4:40,5:30}[stars]
        card=task['initial_card'];caller=next(c for c in task['contacts'] if c['id']=='caller')
        # Restore the complete starting information for lower levels.
        if stars<=3:card['address_note']=facts['address_note']
        if stars>=4:
            card['house']='';card['address_note']='Номер дома и подход к месту требуют уточнения.'
            task['expected_card'].update(house=facts['house'],address_note=facts['address_note'])
            task['intro']=f"Получена карточка: {facts['city']}, {facts['street']}. {card['description']} Номер дома и подход к месту уточните у заявителя."
            caller['questions']=[{'id':'address','question':'Уточните номер дома и подход к месту.','answer':f"{address}. {facts['address_note']}"}]
            task['criteria'] += [
                {'id':'clarify-caller','kind':'contact','expected':'caller','label':'Уточнены сведения у заявителя','weight':10,'skill':'Уточнение сведений'},
                {'id':'clarify-house','kind':'field','field':'house','expected':facts['house'],'label':'Уточнён номер дома','weight':10,'critical':True,'skill':'Точность адреса'}]
        delays={1:[35,80,130],2:[30,65,100],3:[25,50,80],4:[20,45,70],5:[15,35,60]}[stars]
        for event,delay in zip(task['service_events'],delays):event['after']=delay
        if stars==5:
            report='На подъезде задерживаемся. Уточните у заявителя ориентир и передайте его бригаде.'
            task['service_events'][0]['text']=report
            task['contacts'][0]['updates'][0]=report
            for criterion in task['criteria']:
                if criterion['id']=='comments':criterion['expected']=' | '.join(e['text'] for e in task['service_events'])
            task['criteria'].append({'id':'delay-report','kind':'manual','label':'Зафиксирована задержка и передано уточнение бригаде','expected':'В комментариях отражена задержка бригады; после обращения к заявителю бригаде передан ориентир: '+facts['address_note'],'weight':15,'skill':'Координация бригады'})
    task['criteria']=[c for c in task['criteria'] if c['kind']!='time']
    task['criteria'].append({'id':'time','kind':'time','label':f"Учебный срок: {task['limit_seconds']} секунд",'expected':task['limit_seconds'],'weight':10,'skill':'Время'})
