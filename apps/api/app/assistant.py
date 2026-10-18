"""Teacher assistant, stage 1: rule-based commands for navigation and reading.

No model is involved: frequent commands are parsed with regular expressions,
students are resolved deterministically on the server, every command is audited.
"""
import hmac, hashlib, json, re, secrets, time
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import main as m
from .db import User, Attempt
from . import assistant_tickets as tickets

router=APIRouter(prefix='/api/assistant')

PAGES=[
    ('journal','/journal','журнал',r'журнал'),
    ('reviews','/reviews','проверку работ',r'провер'),
    ('stations','/','рабочие места',r'рабоч\w* мест|рабоч\w* станц|\bкласс\b|\bпк\b'),
    ('modes','/classroom/modes','режимы обучения',r'режим'),
    ('students','/users','список студентов',r'студент|ученик'),
    ('analytics','/analytics','аналитику',r'аналитик|статистик'),
    ('tickets','/tickets','билеты',r'билет'),
    ('questions','/learning','минивопросы',r'мини ?вопрос|вопрос'),
    ('lessons','/lessons','занятия',r'заняти|урок'),
]
HELP=('Понимаю команды текстом и голосом.\n'
      'Страницы: «открой журнал», «проверка работ», «рабочие места», «режимы», «студенты», «аналитика», «билеты», «минивопросы», «занятия».\n'
      'Ученики: «какие работы нужно проверить», «найди последнюю работу у Кузнецова», «по Кузнецову есть рекомендации?», «кто сейчас в классе?», «где сидит Кузнецов?».\n'
      'Билеты: «создай билет про пожар на 3 звезды для ДДС» — соберу недостающее и попрошу подтвердить; «в билете 12 поменяй сложность на 4», «переименуй билет про лифт в «Лифт застрял»».\n'
      '«Закрой» закрывает окно.')
STOP={'у','по','о','об','про','с','со','и','а','в','на','за','к','ко','из','для','от','до','ли','же','бы','ну','есть','что','кто','где','какие','какой','какая','каких','какого','кого','чем','сейчас','сидит','находится','работает','сидел','студент','студента','студенту','студентом','студентке','студентки','ученик','ученика','ученику','учеником','ученица','ученицы','ученице','покажи','покажите','найди','найти','открой','открыть','дай','скажи','мне','нам','работу','работа','работы','работ','попытку','попытка','попытки','карточку','карточка','последнюю','последняя','последний','последнее','последние','крайнюю','крайняя','крайний','рекомендации','рекомендация','рекомендаций','ошибки','ошибка','ошибок','профиль','результаты','результат','успеваемость','пк','компьютером','компьютер','компьютера','рабочим','местом','место','места','каким','каком','рабочем','ассистент','нет','его','ее','их','пожалуйста','надо','нужно','все','всё','проверить','провер','проверка','проверку','сдал','сдала','дела','успехи','какую','как','это','ещё','еще','вообще','сегодня','вчера'}

def normalize(text):
    return re.sub(r'\s+',' ',str(text).lower().replace('ё','е')).strip()

GLUE=r'(подключени[ея]|подключись|подключиться|перейди|перейти|открой|открыть|покажи|показать|найди|найти|сидит|работ[аыу]|билет[ыа]?)(к|ко|на|в|во|у|по|за|из)\b'
def clean_speech(text):
    """Recognised speech comes with trailing punctuation and words Whisper glued to a preposition («подключениек»)."""
    text=re.sub(r'\s+',' ',str(text)).strip().strip(' .!?…,;:')
    return re.sub(GLUE,r'\1 \2',text,flags=re.I)

def words(text):
    return re.findall(r'[а-яa-z0-9-]+',normalize(text))

def student_query(text):
    """Name candidates left after service words are removed; empty means no name was given."""
    return [w for w in words(text) if w not in STOP and len(w)>=2 and not w.isdigit() and not re.match(r'(не)?провер|работ|попыт|рекоменд|ошиб|студент|учени|последн|крайн|карточ|результат|успева|мест|компьют|рабоч',w)]

def levenshtein(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        row=[i]
        for j,y in enumerate(b,1):row.append(min(previous[j]+1,row[j-1]+1,previous[j-1]+(x!=y)))
        previous=row
    return previous[-1]

def resolve_students(db,u,query):
    """Visible students whose name matches the query: exact word, word stem (5 letters), then Levenshtein ≤2."""
    terms=[w for w in (query if isinstance(query,list) else words(query)) if w]
    if not terms:return []
    students=[s for s in db.scalars(select(User).where(User.role=='student',User.deleted_at.is_(None)).order_by(User.name)) if m.visible(db,u,s.id)]
    names={s.id:[w for w in re.split(r'[\s-]+',normalize(s.name)) if w] for s in students}
    def stem(w):return w[:5]
    def close(a,b):return len(a)>=4 and len(b)>=4 and levenshtein(a,b)<=(1 if min(len(a),len(b))<6 else 2)
    for match in (lambda q,n:q==n, lambda q,n:stem(q)==stem(n), close):
        found=[s for s in students if all(any(match(q,n) for n in names[s.id]) for q in terms)]
        if found:return found
    return []

def student_card(s):return {'kind':'student','id':s.id,'label':s.name}

def attempt_needs_review(p):
    grade=p.get('assessment') or {}
    return p.get('status')=='completed' and not (grade.get('reviews') and not grade.get('pending') and not grade.get('ai_preliminary'))

def pending_reviews(u,db):
    out=[]
    for a in m.assignments(u,db):
        for p in a['attempts']:
            if attempt_needs_review(p):
                task=a['tasks'][p['task_index']] if 0<=p['task_index']<len(a['tasks']) else {}
                out.append({'attempt_id':p['id'],'student_id':a['student_id'],'student':a['student'],'title':task.get('title') or a['title']})
    return out

def detect(text):
    """Intent from normalized text, following the priority of the command catalogue."""
    t=normalize(text)
    if not t or re.search(r'что (ты )?(умеешь|можешь)|помощь|помоги|справка|список команд|\bhelp\b',t):return 'help'
    if re.search(r'\bне (надо|нужно|открывай|показывай|закрывай|делай|ищи|создавай|подключай|сейчас)|пока не\b|\bпотом\b|можно ли|умеешь ли|а можно|получится ли',t):return 'refused'
    if re.search(r'^(закрой|закрыть|отмена|отменить|хватит|спасибо)\b',t):return 'close'
    if re.search(tickets.CREATE_TICKET,t):return 'create_ticket'
    if re.search(tickets.EDIT_TICKET,t):return 'edit_ticket'
    if re.search(r'кто (сейчас |уже |еще |из учеников |из студентов )*(в классе|онлайн|в сети|подключ|на месте|на местах|работает|присутств|отсутств|не в сети|не подключ|вошел|зашел)|кого (сейчас )?нет|список (подключ|онлайн)|сколько (учеников|студентов|человек) (сейчас )?(в сети|подключ|онлайн|в классе)',t):return 'who_online'
    if re.search(r'^где\b|\bгде (сидит|находится|сейчас|работает)|за каким (пк|комп|рабочим)|на каком (пк|рабочем|месте|комп)|какой (пк|компьютер) у|номер пк',t):return 'where_student'
    if re.search(r'провер',t) and (re.search(r'нужно|надо|каки[ехм]|ждут|ожида|непровер|требу|осталось|непроверенн|на проверку|^провер(ь|ить) (работы|задания|что)',t)):return 'show_reviews'
    if re.search(r'(последн|крайн)\w* (работ|попыт|карточк)|(работ|попыт)\w* (последн|крайн)|найди (работу|попытку|карточку)',t):return 'find_last_attempt'
    if re.search(r'рекомендац|ошибк|профил|успеваем|результат|как (дела|успехи)|что (с|у) ',t) and student_query(t):return 'student_profile'
    for key,path,label,pattern in PAGES:
        if re.search(pattern,t):return 'open_page:'+key
    return 'unknown'

class Dialog(BaseModel):
    intent:str=Field(default='',max_length=40)
    slots:dict=Field(default_factory=dict)

class Interpret(BaseModel):
    text:str=Field(default='',max_length=500)
    context:dict=Field(default_factory=dict)
    dialog:Dialog|None=None

STUDENT_INTENTS={'where_student','find_last_attempt','student_profile'}
DIALOG_INTENTS={'create_ticket','edit_ticket'}
EXECUTE_INTENTS={'create_ticket','edit_ticket','save_ticket'}
TOKEN_KEY=secrets.token_bytes(32)
TOKEN_TTL=600

def reply(intent,preview,*,slots=None,missing=None,candidates=None,action=None,confirm=None,links=None):
    return {'intent':intent,'slots':slots or {},'missing':missing or [],'candidates':candidates or [],'preview':preview,'confirm_required':bool(confirm),'confirm_token':confirm,'action':action,'links':links or []}

def _signature(u,intent,slots,issued):
    body=json.dumps([u.id,intent,slots,issued],ensure_ascii=False,sort_keys=True).encode()
    return hmac.new(TOKEN_KEY,body,hashlib.sha256).hexdigest()[:32]

def confirm_token(u,intent,slots):
    """Stateless proof that this user saw exactly these slots; valid for ten minutes."""
    issued=int(time.time())
    return f'{issued}.{_signature(u,intent,slots,issued)}'

def check_token(u,intent,slots,token):
    issued,_,signature=str(token or '').partition('.')
    if not issued.isdigit() or not hmac.compare_digest(signature,_signature(u,intent,slots,int(issued))):m.fail('Подтверждение не совпадает с командой. Повторите команду.',403)
    if time.time()-int(issued)>TOKEN_TTL:m.fail('Подтверждение устарело. Повторите команду.',409)

@router.post('/interpret')
def interpret(data:Interpret,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    text=clean_speech(data.text)
    intent=detect(text)
    query=student_query(text)
    dialog=data.dialog
    if dialog and dialog.slots.get('answer_slot')=='student' and dialog.intent in STUDENT_INTENTS:dialog.slots['student_query']=text
    if dialog and dialog.intent in STUDENT_INTENTS and (dialog.slots.get('student_id') or dialog.slots.get('student_query')):
        intent=dialog.intent
        if dialog.slots.get('student_query'):query=student_query(dialog.slots['student_query']) or words(dialog.slots['student_query'])
    if dialog and dialog.intent in DIALOG_INTENTS and intent not in ('close','refused') and not (intent=='help' and text):
        step=tickets.create_step if dialog.intent=='create_ticket' else tickets.edit_step
        result=step(dict(dialog.slots),text,dialog.slots.get('answer_slot'),u,db)
    elif intent in DIALOG_INTENTS:
        step=tickets.create_step if intent=='create_ticket' else tickets.edit_step
        result=step({},text,None,u,db)
    else:result=handle(intent,text,query,dialog,u,db)
    detail={'text':text[:300],'intent':result['intent'],'page':str(data.context.get('page',''))[:100]}
    for key in ('student_id','attempt_id','ticket_id','incident_type','field'):
        if result['slots'].get(key):detail[key]=result['slots'][key]
    m.audit(db,u,'assistant_command',result['intent'],detail);db.commit()
    return result

def pick_student(intent,query,dialog,u,db):
    """Returns (student, reply) — exactly one of them is set."""
    if dialog and dialog.slots.get('student_id'):
        s=db.get(User,int(dialog.slots['student_id']))
        if s and s.role=='student' and not s.deleted_at and m.visible(db,u,s.id):return s,None
        return None,reply(intent,'Этот ученик недоступен.')
    if not query:return None,reply(intent,'Какого ученика найти? Напишите фамилию или имя.',missing=[{'slot':'student','question':'Какого ученика найти?'}])
    found=resolve_students(db,u,query)
    label=' '.join(query)
    if not found:return None,reply(intent,f'Не нашёл ученика «{label}» среди ваших студентов.',slots={'student_query':label})
    if len(found)>1:return None,reply(intent,'Нашёл несколько учеников. Кого вы имели в виду?',slots={'student_query':label},candidates=[student_card(s) for s in found])
    return found[0],None

def handle(intent,text,query,dialog,u,db):
    if intent=='help':return reply('help',HELP)
    if intent=='refused':return reply('unknown','Понял, ничего не делаю.')
    if intent=='close':return reply('close','Закрываю.',action={'kind':'close'})
    if intent=='unknown':return reply('unknown','Не понял команду. Напишите «что умеешь?», чтобы увидеть примеры.')
    if intent.startswith('open_page:'):
        key,path,label,_=next(p for p in PAGES if p[0]==intent.split(':')[1])
        return reply('open_page',f'Открываю {label}.',slots={'page':key},action={'kind':'navigate','to':path})
    if intent=='show_reviews':
        items=pending_reviews(u,db);student=None
        if query:
            found=resolve_students(db,u,query)
            if len(found)==1:student=found[0];items=[x for x in items if x['student_id']==student.id]
            elif len(found)>1:return reply(intent,'Нашёл несколько учеников. Кого вы имели в виду?',slots={'student_query':' '.join(query)},candidates=[student_card(s) for s in found])
            elif found==[] and query:return reply(intent,f'Не нашёл ученика «{" ".join(query)}» среди ваших студентов.')
        to='/reviews?state=review'+(f'&student={student.id}' if student else '')
        if not items:preview='Все работы проверены'+(f' у {student.name}' if student else '')+'. Открываю проверку работ.'
        else:preview=f'Нужна проверка: {len(items)} '+plural(len(items),'работа','работы','работ')+'.\n'+'\n'.join(f'• {x["student"]} · {x["title"]}' for x in items[:10])+('\n…' if len(items)>10 else '')+'\nОткрываю проверку работ с фильтром «Нужна проверка».'
        return reply(intent,preview,slots={'count':len(items),**({'student_id':student.id} if student else {})},action={'kind':'navigate','to':to},links=[{'label':'Проверка работ','to':to}])
    if intent=='who_online':
        rows=[r for r in station_rows(u,db) if r['role']=='student']
        online=[r for r in rows if r['online']]
        if re.search(r'не в сети|отсутств|кого нет|не подключ',normalize(text)):
            ids={r['user_id'] for r in online}
            absent=[s for s in db.scalars(select(User).where(User.role=='student',User.deleted_at.is_(None),User.active==True).order_by(User.name)) if s.id not in ids and m.visible(db,u,s.id)]
            preview='Все ваши ученики в сети.' if not absent else 'Не в сети: '+', '.join(s.name for s in absent)+'.'
            return reply(intent,preview,slots={'count':len(absent)},links=[{'label':'Рабочие места','to':'/'}])
        if not online:return reply(intent,'Сейчас никто из учеников не подключён.',slots={'count':0},links=[{'label':'Рабочие места','to':'/'}])
        preview=f'В классе {len(online)} '+plural(len(online),'ученик','ученика','учеников')+':\n'+'\n'.join(f'• ПК {r["number"]} · {r["name"]}'+(f' · {r["page"]}' if r['page'] else '') for r in online)
        return reply(intent,preview,slots={'count':len(online)},links=[{'label':'Рабочие места','to':'/'}])
    if intent in STUDENT_INTENTS:
        s,answer=pick_student(intent,query,dialog,u,db)
        if answer:return answer
        slots={'student_id':s.id,'student':s.name}
        if intent=='where_student':
            row=next((r for r in station_rows(u,db) if r['user_id']==s.id),None)
            if not row or not row['online']:return reply(intent,f'{s.name} сейчас не в сети.',slots=slots,links=[{'label':'Рабочие места','to':'/'}])
            return reply(intent,f'{s.name}: ПК №{row["number"]}'+(f', открыта страница {row["page"]}' if row['page'] else '')+'.',slots={**slots,'station':row['number']},links=[{'label':'Рабочие места','to':'/'}])
        if intent=='find_last_attempt':
            p=db.scalar(select(Attempt).where(Attempt.student_id==s.id).order_by(Attempt.id.desc()).limit(1))
            if not p:return reply(intent,f'У ученика {s.name} ещё нет работ.',slots=slots)
            grade=p.assessment or {}
            score='' if grade.get('score') is None else f', балл {grade["score"]}'
            state={'completed':'завершена','aborted':'прервана','paused':'на паузе','ringing':'входящий вызов','active':'в работе'}.get(p.status,p.status)
            check=' · нужна проверка' if attempt_needs_review({'status':p.status,'assessment':grade}) else ''
            return reply(intent,f'Последняя работа {s.name}: «{p.snapshot.get("title","Билет")}», {state}{score}{check}. Открываю карточку.',slots={**slots,'attempt_id':p.id},action={'kind':'navigate','to':f'/attempts/{p.id}'},links=[{'label':'Карточка работы','to':f'/attempts/{p.id}'},{'label':'Проверка работ','to':f'/reviews?student={s.id}&state=completed'}])
        if intent=='student_profile':
            from .teacher import student_profile
            profile=student_profile(db,s)
            lines=[f'{s.name}: средний балл '+('—' if profile.get('score') is None else f'{profile["score"]}%')+f', проверено работ: {profile.get("confirmed",0)}, освоено звёзд: {profile.get("mastered_stars") or 0}.']
            if profile.get('errors'):lines.append('Частые ошибки: '+'; '.join(f'{x["label"]} ({x["errors"]} из {x["total"]})' for x in profile['errors'][:3])+'.')
            lines.append('Рекомендации:\n'+'\n'.join('• '+r for r in profile.get('recommendations',[])))
            if profile.get('comparison'):lines.append(profile['comparison']+'.')
            return reply(intent,'\n'.join(lines),slots=slots,links=[{'label':'Студенты','to':'/users'},{'label':'Работы ученика','to':f'/reviews?student={s.id}&state=completed'}])
    return reply('unknown','Не понял команду. Напишите «что умеешь?», чтобы увидеть примеры.')

class Execute(BaseModel):
    intent:str=Field(max_length=40)
    slots:dict=Field(default_factory=dict)
    confirm_token:str=Field(default='',max_length=80)

@router.post('/execute')
def execute(data:Execute,u=Depends(m.current),db=Depends(m.getdb)):
    """Runs a confirmed changing command through the ordinary routes under the same user."""
    m.staff(u)
    if data.intent not in EXECUTE_INTENTS:m.fail('Эту команду нельзя выполнить')
    check_token(u,data.intent,data.slots,data.confirm_token)
    runner={'create_ticket':tickets.execute_create,'edit_ticket':tickets.execute_edit,'save_ticket':tickets.execute_save}[data.intent]
    result=runner(data.slots,u,db)
    m.audit(db,u,'assistant_executed',data.intent,{'intent':data.intent,'ticket_id':data.slots.get('ticket_id'),'version_id':result.get('version_id'),'draft_id':data.slots.get('draft_id') or result.get('slots',{}).get('draft_id'),'incident_type':data.slots.get('incident_type'),'field':data.slots.get('field')});db.commit()
    return {'ok':True,'intent':result.get('intent',data.intent),'preview':result['preview'],'action':result.get('action'),'links':result.get('links',[]),
            'slots':result.get('slots',{}),'confirm_required':bool(result.get('confirm')),'confirm_token':result.get('confirm')}

def station_rows(u,db):
    from .classroom import stations
    return stations(u,db)

def plural(n,one,few,many):
    n=abs(n)%100
    if 11<=n<=19:return many
    return {1:one,2:few,3:few,4:few}.get(n%10,many)
