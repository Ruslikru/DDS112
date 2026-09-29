"""Complete the caller catalog without letting the language model invent facts."""
import copy
import re


def caller_questions(task):
    questions = copy.deepcopy(task.get('questions', []))
    if task.get('mode') != '112':
        return questions
    card={**task.get('initial_card',{}),**task.get('expected_card',{})}
    address=', '.join(str(card[k]) for k in ('city','street','house','building','apartment','address_note') if card.get(k))
    facts=[('name','Как вас зовут? Как к вам обращаться?',card.get('name') or 'Алексей Соколов.','зовут|обращаться|фамили'),
           ('address','Назовите точный адрес',address,'адрес'),
           ('phone','Назовите телефон для связи',card.get('phone') or task.get('phone'),'телефон'),
           ('victims','Есть ли пострадавшие?',{'no':'Пострадавших нет.','yes':'Есть пострадавшие.'}.get(card.get('victims')),'пострадав'),
           ('details','Что произошло?',card.get('description'),'произош|случил'),
           *[(k,prompt,card.get(k),pattern) for k,prompt,pattern in [('street','Какая улица?','улиц'),('house','Номер дома?','номер дома'),('entrance','Какой подъезд?','подъезд'),('floor','Какой этаж?','этаж'),('apartment','Номер квартиры?','квартир'),('code','Код домофона?','домофон')]]]
    for key,prompt,answer,pattern in facts:
        if any(q['id']==key or re.search(pattern,q['question'],re.I) for q in questions):continue
        questions.append({'id':key,'question':prompt,'answer':answer or 'Не знаю, не могу уточнить.','required':False,'source':'card'})
    return questions



def contact_questions(task,contact,progress=None):
    card=task.get('initial_card',{})
    address=', '.join(str(card.get(k,'')) for k in ['city','street','house','address_note'] if card.get(k))
    return [
        {'id':'dispatch','question':'Передаю заявку, направьте бригаду, организуйте выезд по адресу','answer':contact['response']},
        {'id':'progress','question':'Доложите обстановку, ход работ, выезд, прибытие или завершение','answer':progress or ('Новых сведений о ходе работ пока нет.' if contact['kind']!='caller' else contact['response'])},
        {'id':'name','question':'Представьтесь, как вас зовут, кто звонит?','answer':contact['name']},
        {'id':'address','question':'Назовите адрес происшествия, где это случилось?','answer':address or 'Точный адрес мне неизвестен.'},
        {'id':'details','question':'Что произошло, по какому поводу вы звонили?','answer':card.get('description') or contact['response']},
        *contact.get('questions',[]),
    ]


def caller_gender(task):
    if task.get('caller_gender') in ('male','female'):return task['caller_gender']
    card={**task.get('initial_card',{}),**task.get('expected_card',{})}
    name=str(card.get('name') or next((q.get('answer') for q in task.get('questions',[]) if q.get('id')=='name'),None) or 'Алексей Соколов')
    if re.search(r'овна|евна|ична|Елена|Анна|Мария|Ольга|Наталья',name,re.I):return 'female'
    if re.search(r'ович|евич|Алексей|Дмитрий|Александр|Иван|Сергей',name,re.I):return 'male'
    return 'female'

DETAIL_QUESTIONS=[('children','Есть ли дети?'),('animals','Есть ли животные?'),('vehicle_count','Сколько машин участвовало?'),('vehicle_colors','Какого цвета машины?'),('kilometer','Какой точный километр?'),('direction','Какое направление движения?'),('blocked_people','Есть ли заблокированные люди?'),('fire','Видно ли открытое пламя?'),('fuel','Есть ли разлив топлива?'),('access','Как подъехать к месту?'),('when','Когда это произошло?'),('location','Где вы сейчас находитесь?'),('danger','Есть ли сейчас опасность рядом с вами?'),('people_count','Сколько людей на месте?'),('smoke_source','Откуда идёт дым?')]

def enrich_task(task):
    """Persist an authored question catalogue; live calls never invent missing details."""
    if task.get('mode')!='112':return task
    task=copy.deepcopy(task);task['caller_gender']=caller_gender(task)
    questions=caller_questions(task);details=task.get('scenario_details',{})
    for key,prompt in DETAIL_QUESTIONS:
        if any(q['id']==key for q in questions):continue
        questions.append({'id':key,'question':prompt,'answer':details.get(key) or 'Я этого не знаю, не могу уверенно уточнить.','required':False})
    from .schemas import Question
    task['questions']=[Question.model_validate(q).model_dump() for q in questions]
    return task


def generated_details(task):
    """Author fictional supplementary facts once; preserve explicit facts and questions."""
    card={**task.get('initial_card',{}),**task.get('expected_card',{})}
    text=(str(card.get('incident_type',''))+' '+str(card.get('description',''))).casefold()
    crash=bool(re.search(r'дтп|столкнул|столкнов',text))
    details={
        'children':'Детей на месте не вижу.', 'animals':'Животных на месте не вижу.',
        'vehicle_count':'Две легковые машины.' if crash else 'Автомобили в происшествии не участвуют.',
        'vehicle_colors':'Одна машина белая, другая тёмно-синяя.' if crash else 'Повреждённых автомобилей здесь нет.',
        'kilometer':'Место рядом с указанным домом, километровой отметки здесь нет.',
        'direction':card.get('address_note') or 'Со стороны ближайшего перекрёстка к указанному дому.',
        'blocked_people':'Людей, которые не могут выбраться, не вижу.',
        'fire':'Вижу пламя.' if re.search(r'горит|открытое пламя',text) and not re.search(r'пламени не|пламя не',text) else 'Открытого пламени не вижу.',
        'fuel':'Разлива топлива не вижу.',
        'access':card.get('address_note') or 'Подъезд со стороны улицы свободен.',
        'when':'Я заметил это примерно две минуты назад.',
        'location':'Я рядом с местом происшествия, на безопасном расстоянии.',
        'danger':'Близко не подхожу, наблюдаю со стороны.',
        'people_count':'Рядом со мной двое взрослых.',
        'smoke_source':'Дыма не вижу.'}
    if 'мкад' in text+' '+str(card.get('street','')).lower():
        details['kilometer']='Тридцать второй километр МКАД.'
    if 'мусоропровод' in text:details['smoke_source']='Дым идёт из мусоропровода.'
    elif 'дым' in text:details['smoke_source']=card.get('description','Источник дыма точно не вижу.')
    if 'лифт' in text:details['blocked_people']='В лифте находятся двое взрослых.'
    if 'животн' in text:details['animals']=card.get('description','Есть животные.')
    if 'три машин' in text or 'три автомоб' in text:details['vehicle_count']='Три машины.'
    details.update(task.get('scenario_details',{}))
    for q in task.get('questions',[]):
        if q['id'] in details:details[q['id']]=q['answer']
    return details
