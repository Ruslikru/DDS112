"""Teacher assistant, stage 1: rule-based commands for navigation and reading.

No model is involved: frequent commands are parsed with regular expressions,
students are resolved deterministically on the server, every command is audited.
"""
import hmac, hashlib, json, re, secrets, time
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import main as m
from .db import User, Attempt, Group
from .learning import MiniQuestion
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
    ('questions','/learning','минивопросы',r'мини ?вопрос'),
    ('lessons','/lessons','занятия',r'заняти|урок'),
]
HELP=('Понимаю команды текстом и голосом.\n'
      'Страницы: «открой журнал», «проверка работ», «рабочие места», «режимы», «студенты», «аналитика», «билеты», «минивопросы», «занятия».\n'
      'Рабочие места: «подключись к рабочему месту Кузнецова», «покажи первый компьютер», «выйди с этого ПК». Если имя неоднозначно, уточню ученика.\n'
      'Ученики: «какие работы нужно проверить», «найди последнюю работу у Кузнецова», «по Кузнецову есть рекомендации?», «кто сейчас в классе?», «где сидит Кузнецов?».\n'
      'Группы и ученики: «создай группу», «открой мне группу», «создай нового ученика». Уточню недостающие сведения.\n'
      'Билеты: «создай новый билет», «отправь билет Кузнецову на ПК 2», «в билете 12 поменяй сложность на 4».\n'
      'Минивопросы: «создай мини задание: какой ответ? варианты А; Б; В; верный ответ Б», «отредактируй минивопрос 5».\n'
      'Экраны: «открой рабочий стол Кузнецова», «открой рабочий стол 2», «закрой рабочий стол», «выйди из всех ПК».\n'
      '«Закрой» закрывает окно.')
STOP={'у','по','о','об','про','с','со','и','а','в','на','за','к','ко','из','для','от','до','ли','же','бы','ну','есть','что','кто','где','какие','какой','какая','каких','какого','кого','чем','сейчас','сидит','находится','работает','сидел','студент','студента','студенту','студентом','студентке','студентки','ученик','ученика','ученику','учеником','ученица','ученицы','ученице','покажи','покажите','найди','найти','открой','открыть','дай','скажи','мне','нам','работу','работа','работы','работ','попытку','попытка','попытки','карточку','карточка','последнюю','последняя','последний','последнее','последние','крайнюю','крайняя','крайний','рекомендации','рекомендация','рекомендаций','ошибки','ошибка','ошибок','профиль','результаты','результат','успеваемость','пк','компьютером','компьютер','компьютера','рабочим','местом','место','места','каким','каком','рабочем','ассистент','нет','его','ее','их','пожалуйста','надо','нужно','все','всё','проверить','провер','проверка','проверку','сдал','сдала','дела','успехи','какую','как','это','ещё','еще','вообще','сегодня','вчера'}

def normalize(text):
    return re.sub(r'\s+',' ',str(text).lower().replace('ё','е')).strip()

GLUE=r'(подключени[ея]|подключись|подключиться|перейди|перейти|открой|открыть|покажи|показать|найди|найти|сидит|работ[аыу]|билет[ыа]?)(к|ко|на|в|во|у|по|за|из)\b'
"""Cardinal number words Whisper writes out instead of digits; only the plain forms, the inflected ones («двух», «двое») are read by the ticket rules."""
UNITS={'ноль':0,'один':1,'одна':1,'одно':1,'два':2,'две':2,'три':3,'четыре':4,'пять':5,'шесть':6,'семь':7,'восемь':8,'девять':9,'десять':10,'одиннадцать':11,'двенадцать':12,'тринадцать':13,'четырнадцать':14,'пятнадцать':15,'шестнадцать':16,'семнадцать':17,'восемнадцать':18,'девятнадцать':19}
TENS={'двадцать':20,'тридцать':30,'сорок':40,'пятьдесят':50,'шестьдесят':60,'семьдесят':70,'восемьдесят':80,'девяносто':90}
HUNDREDS={'сто':100,'двести':200,'триста':300,'четыреста':400,'пятьсот':500,'шестьсот':600,'семьсот':700,'восемьсот':800,'девятьсот':900}
ORDINALS={'перв':1,'втор':2,'трет':3,'четверт':4,'пят':5,'шест':6,'седьм':7,'восьм':8,'девят':9,'десят':10,'одиннадцат':11,'двенадцат':12,'тринадцат':13,'четырнадцат':14,'пятнадцат':15,'шестнадцат':16,'семнадцат':17,'восемнадцат':18,'девятнадцат':19,'двадцат':20}
NUMBER_WORD=r'(?:'+'|'.join(list(HUNDREDS)+list(TENS)+list(UNITS))+r')'
def spoken_numbers(text):
    """«сто два» → «102», «на три звезды» → «на 3 звезды», «в двенадцатом билете» → «в билете 12». Quoted text stays as written."""
    def convert(m):
        total=0;group=0
        for word in m.group(0).lower().replace('ё','е').split():
            if word in HUNDREDS:group+=HUNDREDS[word]
            elif word in TENS:group+=TENS[word]
            else:group+=UNITS[word]
        return str(total+group)
    def part(chunk):
        # Whisper splits «сто» from a glued unit: «с тодва», «с то два».
        chunk=re.sub(r'\bс\s?то\s?(?=(один|одна|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|одиннадцать|двенадцать)\b)','сто ',chunk,flags=re.I)
        chunk=re.sub(r'\b'+NUMBER_WORD+r'(?:\s+'+NUMBER_WORD+r'){0,2}\b',convert,chunk,flags=re.I)
        # A round number already in digits followed by a smaller one («100 1» from «сто один»): one number.
        chunk=re.sub(r'\b(\d{2,3})\s+(\d{1,2})\b',lambda m:str(int(m.group(1))+int(m.group(2))) if (int(m.group(1))%100==0 and int(m.group(2))<100) or (int(m.group(1))%10==0 and int(m.group(1))<100 and int(m.group(2))<10) else m.group(0),chunk)
        chunk=re.sub(r'\b('+'|'.join(ORDINALS)+r')(ый|ий|ого|ом|ому|ую|ая|ой|ые|ых|ем|ье|ья|ью|ьем)\s+(билет\w*|пк|компьютер\w*|мест[оеа])\b',lambda m:f'{m.group(3)} {ORDINALS[m.group(1)]}',chunk,flags=re.I)
        return chunk
    parts=re.split(r'(«[^»]*»|"[^"]*")',text)
    return ''.join(chunk if i%2 else part(chunk) for i,chunk in enumerate(parts))

"""Whole phrases Whisper mishears as one word."""
MISHEARD={'десидит':'где сидит','гдесидит':'где сидит','ктовклассе':'кто в классе'}
def clean_speech(text):
    """Recognised speech comes with trailing punctuation, words Whisper glued to a preposition («подключениек») and numbers written in words."""
    text=re.sub(r'\s+',' ',str(text)).strip().strip(' .!?…,;:')
    text=re.sub(r'\b('+'|'.join(MISHEARD)+r')\b',lambda m:MISHEARD[m.group(1).lower()].capitalize() if m.group(1)[:1].isupper() else MISHEARD[m.group(1).lower()],text,flags=re.I)
    return spoken_numbers(re.sub(GLUE,r'\1 \2',text,flags=re.I))

def words(text):
    return re.findall(r'[а-яa-z0-9-]+',normalize(text))

def student_query(text):
    """Name candidates left after service words are removed; empty means no name was given."""
    return [w for w in words(text) if w not in STOP and len(w)>=2 and not w.isdigit() and not re.match(r'(не)?провер|работ|попыт|рекоменд|ошиб|студент|учени|последн|крайн|карточ|результат|успева|мест|компьют|рабоч|подключ|покаж|откро|перейд|стол|настольн|перв|втор|трет|каки',w)]

def levenshtein(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        row=[i]
        for j,y in enumerate(b,1):row.append(min(previous[j]+1,row[j-1]+1,previous[j-1]+(x!=y)))
        previous=row
    return previous[-1]

"""Expected-words hint for Whisper: the command vocabulary, so short commands are not heard as look-alikes."""
SPEECH_PROMPT=('Команды преподавателю тренажёра ДДС: открой журнал, покажи работы для проверки, аналитика, минивопросы, режимы обучения. '
               'Подключись к рабочему месту Артёма Кузнецова. Подключись к первому компьютеру. Выйди с этого ПК. '
               'Найди последнюю работу Кузнецова. Покажи рекомендации ученика. Создай группу, добавь всех активных студентов. Открой мне группу. '
               'Создай билет ДДС. Добавь минивопрос. Отредактируй минивопрос. Закрой ассистента.')
def speech_prompt(db,u):
    """The vocabulary hint for Whisper with the names of the active services, so «служба сто два» comes back as «Служба 102»."""
    names=[s.name for s in tickets.active_services(db)]
    students=[s.name for s in db.scalars(select(User).where(User.role=='student',User.active==True,User.deleted_at.is_(None))) if m.visible(db,u,s.id)][:40]
    groups=[g.name for g in db.scalars(select(Group).order_by(Group.id.desc())) if u.role=='admin' or g.teacher_id==u.id][:30]
    return SPEECH_PROMPT+(' Службы: '+', '.join(names)+'.' if names else '')+(' Ученики: '+', '.join(students)+'.' if students else '')+(' Группы: '+', '.join(groups)+'.' if groups else '')
"""Command words a recognised phrase is corrected to when a word is one typo away («белет» → «билет»). Normalized forms, ё as е."""
VOCAB=set('''журнал журнала журнале проверка проверку проверки проверить проверь работ работы работу работа рабочие рабочих места место месте
режимы режим режима студенты студентов студента студент ученики учеников ученика ученик аналитика аналитику статистика билет билеты билете билета билетов
минивопрос минивопросы вопросы вопрос занятия занятие занятий открой открыть покажи показать найди найти перейди последнюю последний попытку попытка карточку карточка
рекомендации ошибки профиль результаты успеваемость классе класс онлайн сети сидит находится работает компьютер компьютером создай создать сделай новый
сложность сложный сложного простой звезды звезд звезда пожар пожара переименуй поменяй измени назови закрой закрыть отмена отменить выполни выполнить сохрани сохранить
пострадавших пострадавшие пострадавший служба службы службу служб диспетчер диспетчера оператор оператора норматив описание название признаки признак
нужно надо какие какой сейчас уровень режиме подключен подключены подключи рабочий мастер версия версию критерии контакты события адрес адресу улица улице проспект переулок'''.split())
def fix_keywords(text,protected=()):
    """Replaces words one typo away from a command word (two for long words). Quoted text and protected words (student names) stay as written."""
    protected={normalize(w) for w in protected}
    def fix(word):
        w=normalize(word)
        if len(w)<4 or w in VOCAB or w in STOP or w in protected or w.isdigit():return word
        limit=1 if len(w)<8 else 2
        best=[v for v in VOCAB if abs(len(v)-len(w))<=limit and levenshtein(w,v)<=limit]
        if not best:return word
        best.sort(key=lambda v:(levenshtein(w,v),v[0]!=w[0],-len(v)))
        # Two different candidates at the same distance: the word is left alone rather than guessed.
        if len(best)>1 and levenshtein(w,best[0])==levenshtein(w,best[1]) and (best[0][0]!=w[0])==(best[1][0]!=w[0]) and best[0][:3]!=best[1][:3]:return word
        value=best[0]
        return value.capitalize() if word[:1].isupper() else value
    parts=re.split(r'(«[^»]*»|"[^"]*")',text)
    return ''.join(part if i%2 else re.sub(r'[А-Яа-яЁё]+',lambda m:fix(m.group(0)),part) for i,part in enumerate(parts))

def resolve_students(db,u,query):
    """Visible students whose name matches the query: exact word, word stem (5 letters), then Levenshtein ≤2."""
    terms=[w for w in (query if isinstance(query,list) else words(query)) if w]
    if not terms:return []
    students=[s for s in db.scalars(select(User).where(User.role=='student',User.deleted_at.is_(None)).order_by(User.name)) if m.visible(db,u,s.id)]
    def forms(name):
        parts=[w for w in re.split(r'[\s-]+',normalize(name)) if w]
        variants=parts[:]
        for word in parts:
            if word.endswith(('ова','ева','ина')):
                variants.extend(word[:-1]+ending for ending in ('ой','у','ы','е'))
        return variants
    names={s.id:forms(s.name) for s in students}
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
    if re.search(r'(?:выйди|выходи|выйти).*всех? (?:пк|компьютер|рабочих мест)|до завтра',t):return 'exit_all'
    if re.search(r'(закрой|закрыть|выйди|выйти).*(рабочий стол|рабочего стола|рабочее место|удаленн)',t):return 'close_desktop'
    if re.search(r'^(закрой|закрыть|отмена|отменить|хватит|спасибо)\b',t):return 'close'
    if re.search(r'^(выйди|выйти|выход|разлогинь)\b',t):return 'exit_pc'
    if re.search(r'(созда|сдела|добав|новую|новый).*(групп)',t):return 'create_group'
    if re.search(r'(созда|добав|заведи|зарегистрир).*(ученик|учениц|студент|новичк)',t):return 'create_student'
    if re.search(r'(открой|открыть|покаж|найди|перейд|список|состав).*(групп)|^групп[ауы]?\b',t):return 'open_group'
    if re.search(r'(созда|сдела|добав|новый).*(мини[ -]?вопрос|мини[ -]?задани)',t):return 'create_question'
    if re.search(r'(редакт|измен|поменя|исправ).*(мини[ -]?вопрос|мини[ -]?задани)',t):return 'edit_question'
    if re.search(r'опублику|публикац',t):return 'publish_ticket'
    if re.search(r'делай как я',t):return 'demo_mode'
    if re.search(r'(отправ|назнач|выдай|передай).*(билет|задани)',t):return 'assign_ticket'
    if re.search(r'(подключ|покаж|открой|перейд).*(рабоч|компьют|\bпк\b|стол)',t) and not re.search(r'рабочие места|рабочих мест',t):
        return 'connect_station' if re.search(r'\b\d+\b|перв|втор|трет|четвер|пят|шест|седьм|восьм|девят|десят',t) else 'connect_student'
    if re.search(tickets.CREATE_TICKET,t):return 'create_ticket'
    if re.search(tickets.EDIT_TICKET,t):return 'edit_ticket'
    if re.search(r'кто (сейчас |уже |еще |из учеников |из студентов )*(в классе|онлайн|в сети|подключ|на месте|на местах|работает|присутств|отсутств|не в сети|не подключ|вошел|зашел)|кого (сейчас )?нет|список (подключ|онлайн)|сколько (учеников|студентов|человек) (сейчас )?(в сети|подключ|онлайн|в классе)',t):return 'who_online'
    if re.search(r'^где\b|\bгде (сидит|находится|сейчас|работает)|за каким (пк|комп|рабочим)|на каком (пк|рабочем|месте|комп)|какой (пк|компьютер) у|номер пк',t):return 'where_student'
    if re.search(r'провер',t) and (re.search(r'нужно|надо|каки[ехм]|ждут|ожида|непровер|требу|осталось|непроверенн|на проверку|^провер(ь|ить) (работы|задания|что)',t)):return 'show_reviews'
    if re.search(r'(последн|крайн)\w* (работ|попыт|карточк)|(работ|попыт)\w* (последн|крайн)|найди (работу|попытку|карточку)',t):return 'find_last_attempt'
    if re.search(r'(открой|открыть|покажи|показать).*\b(студента|ученика)\b',t) and student_query(t):return 'student_profile'
    if re.search(r'рекомендац|ошибк|профил|успеваем|результат|как (дела|успехи)|что (с|у) ',t) and student_query(t):return 'student_profile'
    for key,path,label,pattern in PAGES:
        if re.search(pattern,t):return 'open_page:'+key
    if re.search(r'^(открой|открыть|покажи|показать)\b',t) and student_query(t):return 'student_profile'
    return 'unknown'

class Dialog(BaseModel):
    intent:str=Field(default='',max_length=40)
    slots:dict=Field(default_factory=dict)

class Interpret(BaseModel):
    text:str=Field(default='',max_length=500)
    context:dict=Field(default_factory=dict)
    dialog:Dialog|None=None

STUDENT_INTENTS={'where_student','find_last_attempt','student_profile','connect_student'}
DIALOG_INTENTS={'create_ticket','edit_ticket','create_group','open_group','create_question','edit_question','create_student','assign_ticket','publish_ticket'}
EXECUTE_INTENTS={'create_ticket','edit_ticket','save_ticket','create_group','create_question','edit_question','create_student','assign_ticket','publish_ticket'}
TOKEN_KEY=secrets.token_bytes(32)
TOKEN_TTL=7200

def reply(intent,preview,*,slots=None,missing=None,candidates=None,action=None,confirm=None,links=None):
    return {'intent':intent,'slots':slots or {},'missing':missing or [],'candidates':candidates or [],'preview':preview,'confirm_required':bool(confirm),'confirm_token':confirm,'action':action,'links':links or []}

def _signature(u,intent,slots,issued):
    body=json.dumps([u.id,intent,slots,issued],ensure_ascii=False,sort_keys=True).encode()
    return hmac.new(TOKEN_KEY,body,hashlib.sha256).hexdigest()[:32]

def confirm_token(u,intent,slots):
    """Stateless proof that this user saw exactly these slots; valid for two hours."""
    issued=int(time.time())
    return f'{issued}.{_signature(u,intent,slots,issued)}'

def check_token(u,intent,slots,token):
    issued,_,signature=str(token or '').partition('.')
    if not issued.isdigit() or not hmac.compare_digest(signature,_signature(u,intent,slots,int(issued))):m.fail('Подтверждение не совпадает с командой. Повторите команду.',403)
    if time.time()-int(issued)>TOKEN_TTL:m.fail('Подтверждение устарело. Повторите команду.',409)

def group_step(slots,text,answer_slot,u,db):
    if answer_slot=='name':slots['name']=text.strip(' «»"')[:160]
    elif answer_slot=='members':slots['members_text']=text.strip()
    elif not slots:
        slots['all_active']=bool(re.search(r'всех|все[хм]? активн',normalize(text)))
        named=re.search(r'групп[уы]?\s+[«"]([^»"]+)[»"]',text)
        if named:slots['name']=named.group(1).strip()[:160]
    if not slots.get('name'):return reply('create_group','Как назвать новую группу?',slots=slots,missing=[{'slot':'name','question':'Название группы'}])
    if not slots.get('all_active') and not slots.get('members_text'):
        return reply('create_group','Кого добавить в группу? Назовите учеников через запятую или скажите «всех активных».',slots=slots,missing=[{'slot':'members','question':'Участники группы'}])
    members=[]
    if slots.get('all_active') or re.search(r'всех|все[хм]? активн',normalize(slots.get('members_text',''))):
        members=[s for s in db.scalars(select(User).where(User.role=='student',User.active==True,User.deleted_at.is_(None))) if m.visible(db,u,s.id)]
        slots['all_active']=True
    else:
        for name in re.split(r',|\s+и\s+',slots['members_text']):
            name=name.strip()
            if not name:continue
            found=resolve_students(db,u,student_query(name) or words(name))
            if len(found)!=1:return reply('create_group',f'Не могу однозначно найти ученика «{name}». Уточните состав группы, перечислив полные имена через запятую.',slots={**slots,'members_text':''},missing=[{'slot':'members','question':'Участники группы'}])
            members.append(found[0])
    if not members:return reply('create_group','Не нашёл доступных активных учеников. Уточните состав группы.',slots={**slots,'members_text':''},missing=[{'slot':'members','question':'Участники группы'}])
    slots['student_ids']=list(dict.fromkeys(s.id for s in members))
    return reply('create_group',f'Создать группу «{slots["name"]}» и добавить {len(slots["student_ids"])} учеников: '+', '.join(s.name for s in members)+'?',slots=slots,confirm=confirm_token(u,'create_group',slots))

def open_group_step(slots,text,answer_slot,u,db):
    groups=[g for g in db.scalars(select(Group).order_by(Group.name,Group.id)) if u.role=='admin' or g.teacher_id==u.id]
    if not groups:return reply('open_group','Групп пока нет.',links=[{'label':'Студенты','to':'/users'}])
    selected=None
    if slots.get('group_id'):
        selected=next((g for g in groups if g.id==int(slots['group_id'])),None)
        if not selected:return reply('open_group','Эта группа недоступна. Выберите другую.',candidates=[{'kind':'group','slot':'group_id','id':g.id,'label':g.name} for g in groups],missing=[{'slot':'group_id','question':'Какую группу открыть?'}])
    else:
        name=normalize(text)
        name=re.sub(r'^(?:(?:открой|открыть|покажи|показать|найди|перейди|список|состав|мне|пожалуйста|группу|группа|группы|группе|в|к|на|из)\s+)+', '', name)
        name=name.strip(' «»".,!?')
        if name:
            found=[g for g in groups if normalize(g.name)==name]
            if not found:found=[g for g in groups if name in normalize(g.name)]
            if len(found)==1:selected=found[0]
            elif len(found)>1:groups=found
            elif answer_slot=='group_id':return reply('open_group',f'Группу «{text}» не нашёл. Выберите группу из списка.',candidates=[{'kind':'group','slot':'group_id','id':g.id,'label':g.name} for g in groups],missing=[{'slot':'group_id','question':'Какую группу открыть?'}])
    if not selected:
        return reply('open_group','Какую группу открыть? Выберите из списка или назовите её.',candidates=[{'kind':'group','slot':'group_id','id':g.id,'label':g.name} for g in groups],missing=[{'slot':'group_id','question':'Название группы'}])
    students=list(db.scalars(select(User).where(User.role=='student',User.group_id==selected.id,User.deleted_at.is_(None)).order_by(User.name)))
    to=f'/users?group={selected.id}'
    members='\n'.join('• '+s.name for s in students) if students else 'Пока нет учеников.'
    return reply('open_group',f'Группа «{selected.name}» ({len(students)}):\n{members}',slots={'group_id':selected.id},action={'kind':'navigate','to':to},links=[{'label':'Открыть группу','to':to}])

def question_step(intent,slots,text,answer_slot,u,db):
    if answer_slot=='question_id':
        number=re.search(r'\d+',text)
        if number:slots['question_id']=int(number.group())
    if intent=='edit_question' and not slots.get('question_id'):
        number=re.search(r'(?:номер|№|мини ?вопрос|вопрос)\s*(\d+)\b',normalize(text))
        if number:slots['question_id']=int(number.group(1))
        else:
            candidates=[q for q in db.scalars(select(MiniQuestion)) if normalize(q.data.get('prompt','')) in normalize(text)]
            if len(candidates)==1:slots['question_id']=candidates[0].id
        if not slots.get('question_id'):return reply(intent,'Какой минивопрос изменить? Назовите его номер.',slots=slots,missing=[{'slot':'question_id','question':'Номер минивопроса'}])
    if intent=='edit_question':
        q=db.get(MiniQuestion,slots.get('question_id')) if slots.get('question_id') else None
        if not q:return reply(intent,'Минивопрос с таким номером не найден.',slots={'question_id':None},missing=[{'slot':'question_id','question':'Номер минивопроса'}])
        if answer_slot=='field':slots['field']=normalize(text).strip()
        elif answer_slot=='value':slots['value']=text.strip()
        if not slots.get('field'):return reply(intent,f'Минивопрос №{q.id}: «{q.data.get("prompt","")}». Что изменить: вопрос, ответ или текст озвучки?',slots=slots,missing=[{'slot':'field','question':'Поле'}])
        fields={'вопрос':'prompt','формулиров':'prompt','ответ':'answer','озвуч':'audio_text','звук':'audio_text'}
        key=slots['field'] if slots['field'] in ('prompt','answer','audio_text') else next((value for word,value in fields.items() if word in slots['field']),None)
        if not key:return reply(intent,'Можно изменить вопрос, ответ или текст озвучки. Что выбрать?',slots={**slots,'field':''},missing=[{'slot':'field','question':'Поле'}])
        slots['field']=key
        if not slots.get('value'):return reply(intent,'Продиктуйте новый текст.',slots=slots,missing=[{'slot':'value','question':'Новый текст'}])
        return reply(intent,f'Изменить минивопрос №{q.id}: {key} → «{slots["value"]}»?',slots=slots,confirm=confirm_token(u,intent,slots))
    if not slots and text:
        body=re.sub(r'^.*?(?:мини\s?(?:вопрос|задани[ея]))\s*[.:—-]?\s*','',text,flags=re.I).strip()
        parts=re.split(r'\bвариант[ыа]?\b',body,maxsplit=1,flags=re.I)
        if len(parts)==2:
            slots['prompt']=parts[0].strip(' ,.:;')
            choices=re.split(r'\bверн(?:ый|ого)\s+ответ\b',parts[1],maxsplit=1,flags=re.I)
            slots['options']=[v.strip(' ,.:;') for v in re.split(r'[;,]',choices[0]) if v.strip(' ,.:;')]
            if len(choices)==2:slots['answer']=choices[1].strip(' ,.:;.!?')
            slots['audio_answered']=True
    if answer_slot=='prompt':slots['prompt']=text.strip()
    elif answer_slot=='answer':slots['answer']=text.strip()
    elif answer_slot=='audio_text':
        slots['audio_text']='' if re.search(r'^без (звука|озвучки)|^не нужно|^нет$',normalize(text)) else text.strip()
        slots['audio_answered']=True
    if not slots.get('prompt'):return reply(intent,'Сформулируйте минивопрос.',slots=slots,missing=[{'slot':'prompt','question':'Вопрос'}])
    if not slots.get('answer'):return reply(intent,'Какой правильный ответ?',slots=slots,missing=[{'slot':'answer','question':'Ответ'}])
    if not slots.get('audio_answered'):return reply(intent,'Нужна озвучка? Напишите текст для озвучки или «без озвучки».',slots=slots,missing=[{'slot':'audio_text','question':'Текст озвучки'}])
    sound='; озвучка: «'+slots['audio_text']+'»' if slots.get('audio_text') else '; без озвучки'
    return reply(intent,f'Создать минивопрос «{slots["prompt"]}» с ответом «{slots["answer"]}»{sound}?',slots=slots,confirm=confirm_token(u,intent,slots))

def student_step(slots,text,answer_slot,u,db):
    if answer_slot=='name':slots['name']=text.strip(' .«»"')
    elif answer_slot=='group_id' and slots.get('group_id'):pass
    elif text and not slots.get('name'):
        found=re.search(r'([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)',text)
        if found:slots['name']=found.group(1)
    name=slots.get('name','').strip()
    if not name:return reply('create_student','Как зовут нового ученика? Назовите фамилию, имя и отчество.',slots=slots,missing=[{'slot':'name','question':'ФИО ученика'}])
    if len(name.split())<2:return reply('create_student','Укажите как минимум фамилию и имя.',slots={},missing=[{'slot':'name','question':'ФИО ученика'}])
    if db.scalar(select(User.id).where(User.role=='student',User.name==name,User.deleted_at.is_(None))):return reply('create_student',f'Ученик {name} уже есть. Откройте его профиль.',links=[{'label':'Студенты','to':'/users'}])
    groups=list(db.scalars(select(Group).where(Group.teacher_id==u.id).order_by(Group.name)))
    if u.role=='admin':groups=list(db.scalars(select(Group).order_by(Group.name)))
    if not groups:return reply('create_student','Сначала создайте группу для нового ученика.',links=[{'label':'Группы','to':'/users'}])
    if not slots.get('group_id'):
        if len(groups)==1:slots['group_id']=groups[0].id
        else:return reply('create_student','В какую группу добавить ученика?',slots=slots,missing=[{'slot':'group_id','question':'Группа','options':[{'value':g.id,'label':g.name} for g in groups]}])
    group=next((g for g in groups if g.id==int(slots['group_id'])),None)
    if not group:return reply('create_student','Выберите свою группу.',slots={k:v for k,v in slots.items() if k!='group_id'},missing=[{'slot':'group_id','question':'Группа','options':[{'value':g.id,'label':g.name} for g in groups]}])
    return reply('create_student',f'Добавить ученика {name} в группу «{group.name}»? После подтверждения покажу логин и одноразовый код для первого входа.',slots=slots,confirm=confirm_token(u,'create_student',slots))

def publication_step(slots,text,u,db):
    if slots.get('answer_slot')=='ticket_id':slots.pop('version_id',None)
    rows=tickets.latest_tickets(u,db)
    number=re.search(r'билет(?:а)?\s*(?:№|номер)?\s*(\d+)',normalize(text))
    if number:slots['ticket_id']=int(number.group(1));slots.pop('version_id',None)
    selected=next((v for v in rows if v['id']==slots.get('version_id') or v['ticket_id']==slots.get('ticket_id')),None)
    if not selected:
        return reply('publish_ticket','Какой билет опубликовать? Выберите черновик.',slots=slots,candidates=[tickets.ticket_card(v) for v in rows if not v['published']])
    slots={'version_id':selected['id'],'ticket_id':selected['ticket_id']}
    return reply('publish_ticket',f'Опубликовать билет №{selected["ticket_id"]} «{selected["data"]["title"]}»?',slots=slots,confirm=confirm_token(u,'publish_ticket',slots))

def assignment_step(slots,text,answer_slot,u,db):
    if answer_slot=='student' and text:slots['student_query']=text
    elif answer_slot=='ticket' and text:
        found=re.search(r'\d+',text)
        slots['ticket_id']=int(found.group()) if found else None
    elif text and not slots:
        found=re.search(r'билет(?:\s*№)?\s*(\d+)',normalize(text))
        if found:slots['ticket_id']=int(found.group(1))
        name=re.search(r'(?:ученику|студенту|для)\s+([А-ЯЁа-яё][А-ЯЁа-яё-]+)',text)
        if name:slots['student_query']=text[name.start(1):]
        station=re.search(r'(?:рабоч(?:ее|ем) место|пк|компьютер)\s*(\d+)',normalize(text))
        if station:slots['station']=station.group(1)
    rows=tickets.latest_tickets(u,db)
    version=next((v for v in rows if v['ticket_id']==slots.get('ticket_id')),None) if slots.get('ticket_id') else next((v for v in rows if v['published']),None)
    if not version:return reply('assign_ticket','Какой билет отправить? Назовите его номер.',slots=slots,missing=[{'slot':'ticket','question':'Номер билета'}])
    slots['ticket_id']=version['ticket_id'];slots['version_id']=version['id']
    recipient_text=str(slots.get('student_query') or text)
    chunks=re.split(r'\s+и\s+|[,;]',recipient_text)
    if len(chunks)>1 or slots.get('student_ids'):
        ids=list(slots.get('student_ids') or [])
        unresolved=[]
        for chunk in chunks if not ids else []:
            station_match=re.search(r'(?:пк|компьютер|место)\s*(\d+)',normalize(chunk))
            if station_match:
                row=next((r for r in station_rows(u,db) if str(r['number'])==station_match.group(1) and r['online'] and r['role']=='student'),None)
                found=[db.get(User,row['user_id'])] if row else []
            else:
                query=re.sub(r'^.*?(?:билет(?:\s*№?\s*\d+)?|задание)\s*','',chunk,flags=re.I)
                query=re.sub(r'\b(?:отправь|отправить|назначь|ученикам|студентам|ученику|студенту)\b','',query,flags=re.I)
                found=resolve_students(db,u,student_query(query))
            if len(found)==1:ids.append(found[0].id)
            else:unresolved.append(chunk.strip())
        if unresolved:return reply('assign_ticket','Уточните получателей: '+', '.join(unresolved)+'. Назовите фамилии через «и».',slots={k:v for k,v in slots.items() if k not in ('student_query','student_ids')},missing=[{'slot':'student','question':'Получатели'}])
        members=[db.get(User,sid) for sid in dict.fromkeys(ids)]
        if members and all(s and s.role=='student' and m.visible(db,u,s.id) for s in members):
            slots['student_ids']=[s.id for s in members]
            return reply('assign_ticket',f'Отправить билет №{version["ticket_id"]} «{version["data"]["title"]}»: '+', '.join(s.name for s in members)+'?',slots=slots,confirm=confirm_token(u,'assign_ticket',slots))
    student=None
    if slots.get('student_id'):
        candidate=db.get(User,int(slots['student_id']))
        if candidate and candidate.role=='student' and m.visible(db,u,candidate.id):student=candidate
    if not student and not slots.get('student_query') and not slots.get('station'):
        candidate_query=re.sub(r'^.*?(?:билет(?:\s*№?\s*\d+)?|задание)\s*','',text,flags=re.I)
        if candidate_query!=text and student_query(candidate_query):slots['student_query']=candidate_query
    if not student and slots.get('student_query'):
        found=resolve_students(db,u,student_query(slots['student_query']) or words(slots['student_query']))
        if len(found)>1:return reply('assign_ticket','Нашёл нескольких учеников. Выберите одного.',slots=slots,candidates=[student_card(s) for s in found])
        if found:student=found[0]
    if not student and slots.get('station'):
        row=next((r for r in station_rows(u,db) if str(r['number'])==str(slots['station']) and r['online'] and r['role']=='student'),None)
        if row:student=db.get(User,row['user_id'])
    if not student:return reply('assign_ticket','Какому ученику отправить билет? Назовите фамилию или номер его рабочего места.',slots=slots,missing=[{'slot':'student','question':'Ученик'}])
    if slots.get('station'):
        row=next((r for r in station_rows(u,db) if str(r['number'])==str(slots['station']) and r['online']),None)
        if not row or row['user_id']!=student.id:return reply('assign_ticket',f'{student.name} сейчас не работает за ПК №{slots["station"]}. Уточните ученика или рабочее место.',slots={k:v for k,v in slots.items() if k not in ('student_id','student_query','station')},missing=[{'slot':'student','question':'Ученик'}])
    slots['student_id']=student.id
    return reply('assign_ticket',f'Отправить билет №{version["ticket_id"]} «{version["data"]["title"]}» ученику {student.name}'+(f' на ПК №{slots["station"]}' if slots.get('station') else '')+'?',slots=slots,confirm=confirm_token(u,'assign_ticket',slots))

@router.post('/interpret')
def interpret(data:Interpret,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    text=clean_speech(data.text)
    # Typos and mis-heard command words are corrected, but never the names of the teacher's students.
    names=[w for s in db.scalars(select(User).where(User.role=='student',User.deleted_at.is_(None))) if m.visible(db,u,s.id) for w in re.split(r'[\s-]+',s.name) if w]
    text=fix_keywords(text,names)
    intent=detect(text)
    query=student_query(text)
    dialog=data.dialog
    if intent=='publish_ticket':
        target=re.search(r'/tickets/(\d+)',str(data.context.get('page','')))
        context_version=int(target.group(1)) if target else data.context.get('version_id')
        dialog=Dialog(intent=intent,slots={**(dict(dialog.slots) if dialog and dialog.intent==intent else {}),**({'version_id':context_version} if context_version else {})})
    if dialog and intent!=dialog.intent and (intent.startswith('open_page:') or intent in {'show_reviews','find_last_attempt','close_desktop','exit_all','exit_pc','who_online','where_student','student_profile','connect_station','connect_student','demo_mode'}):
        dialog=None
    if dialog and dialog.slots.get('answer_slot')=='student' and dialog.intent in STUDENT_INTENTS:dialog.slots['student_query']=text
    if dialog and dialog.intent in STUDENT_INTENTS and (dialog.slots.get('student_id') or dialog.slots.get('student_query')):
        intent=dialog.intent
        if dialog.slots.get('student_query'):query=student_query(dialog.slots['student_query']) or words(dialog.slots['student_query'])
    if dialog and dialog.intent in DIALOG_INTENTS and intent not in ('close','refused') and not (intent=='help' and text):
        if dialog.intent in ('create_ticket','edit_ticket'):
            step=tickets.create_step if dialog.intent=='create_ticket' else tickets.edit_step
            result=step(dict(dialog.slots),text,dialog.slots.get('answer_slot'),u,db)
        elif dialog.intent=='create_group':result=group_step(dict(dialog.slots),text,dialog.slots.get('answer_slot'),u,db)
        elif dialog.intent=='open_group':result=open_group_step(dict(dialog.slots),text,dialog.slots.get('answer_slot'),u,db)
        elif dialog.intent=='create_student':result=student_step(dict(dialog.slots),text,dialog.slots.get('answer_slot'),u,db)
        elif dialog.intent=='publish_ticket':result=publication_step(dict(dialog.slots),text,u,db)
        elif dialog.intent=='assign_ticket':result=assignment_step(dict(dialog.slots),text,dialog.slots.get('answer_slot'),u,db)
        else:result=question_step(dialog.intent,dict(dialog.slots),text,dialog.slots.get('answer_slot'),u,db)
    elif intent in DIALOG_INTENTS:
        if intent in ('create_ticket','edit_ticket'):
            step=tickets.create_step if intent=='create_ticket' else tickets.edit_step
            result=step({},text,None,u,db)
        elif intent=='create_group':result=group_step({},text,None,u,db)
        elif intent=='open_group':result=open_group_step({},text,None,u,db)
        elif intent=='create_student':result=student_step({},text,None,u,db)
        elif intent=='publish_ticket':result=publication_step({},text,u,db)
        elif intent=='assign_ticket':result=assignment_step({},text,None,u,db)
        else:result=question_step(intent,{},text,None,u,db)
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
    if intent=='demo_mode':return reply(intent,'Открываю «Делай как я». Выберите учеников и нажмите «Начать трансляцию».',action={'kind':'navigate','to':'/classroom/modes?mode=demo'})
    if intent=='help':return reply('help',HELP)
    if intent=='refused':return reply('unknown','Понял, ничего не делаю.')
    if intent=='close':return reply('close','Закрываю.',action={'kind':'close'})
    if intent=='close_desktop':return reply(intent,'Закрываю просмотр рабочего стола.',action={'kind':'navigate','to':'/?close_remote=1'})
    if intent=='exit_all':
        from .management import remote, lock, enqueue, state, can_manage, server_id
        from .classroom_models import Workstation
        with lock:
            for wid,session in list(remote.items()):
                if session['owner']==u.id:remote.pop(wid,None)
            queued=0
            for station in db.scalars(select(Workstation).where(Workstation.blocked==False)):
                if station.id==server_id() or not can_manage(db,u,station):continue
                person=db.get(m.User,station.user_id) if station.user_id else None
                if not person or person.role!='student' or time.time()-state.get(station.id,{}).get('seen',0)>15:continue
                enqueue(db,station.id,'logout');queued+=1
            db.commit()
        if 'до завтра' in normalize(text):return reply(intent,'До завтра! Выходим из учётной записи.',action={'kind':'logout'})
        return reply(intent,f'Просмотр закрыт. Команда выхода отправлена на {queued} рабочих мест.',action={'kind':'navigate','to':'/?close_remote=1'})
    if intent=='exit_pc':return reply(intent,'Выхожу из учётной записи на этом ПК.',action={'kind':'logout'})
    if intent=='unknown':return reply('unknown','Не понял команду. Напишите «что умеешь?», чтобы увидеть примеры.')
    if intent=='connect_station':
        t=normalize(text)
        number=re.search(r'\b\d+\b',t)
        target=number.group() if number else next((str(value) for stem,value in ORDINALS.items() if stem in t),None)
        if not target:return reply(intent,'Какой номер рабочего места открыть?')
        rows=[r for r in station_rows(u,db) if str(r['number'])==target]
        if not rows:return reply(intent,f'Рабочее место №{target} не найдено или недоступно.')
        row=rows[0]
        if not row['online']:return reply(intent,f'Рабочее место №{target} сейчас не в сети.')
        to='/?remote='+row['id']
        return reply(intent,f'Открываю рабочее место №{target}: {row["name"]}.',slots={'station':target},action={'kind':'navigate','to':to})
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
        if intent=='connect_student':
            row=next((r for r in station_rows(u,db) if r['user_id']==s.id),None)
            if not row or not row['online']:return reply(intent,f'{s.name} сейчас не подключён к рабочему месту.',slots=slots)
            to='/?remote='+row['id']
            return reply(intent,f'Открываю рабочее место №{row["number"]}: {s.name}.',slots={**slots,'station':row['number']},action={'kind':'navigate','to':to})
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
            lines=[f'{s.name}: средний балл '+('нет' if profile.get('score') is None else f'{profile["score"]}%')+f', проверено работ: {profile.get("confirmed",0)}, освоено звёзд: {profile.get("mastered_stars") or 0}.']
            if profile.get('errors'):lines.append('Частые ошибки: '+'; '.join(f'{x["label"]} ({x["errors"]} из {x["total"]})' for x in profile['errors'][:3])+'.')
            lines.append('Рекомендации:\n'+'\n'.join('• '+r for r in profile.get('recommendations',[])))
            if profile.get('comparison'):lines.append(profile['comparison']+'.')
            return reply(intent,'\n'.join(lines),slots=slots,action={'kind':'navigate','to':f'/users?student={s.id}'},links=[{'label':'Студенты','to':'/users'},{'label':'Работы ученика','to':f'/reviews?student={s.id}&state=completed'}])
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
    if data.intent in ('create_ticket','edit_ticket','save_ticket'):
        runner={'create_ticket':tickets.execute_create,'edit_ticket':tickets.execute_edit,'save_ticket':tickets.execute_save}[data.intent]
        result=runner(data.slots,u,db)
    elif data.intent=='create_group':
        ids=data.slots.get('student_ids',[])
        if not isinstance(ids,list) or not ids or len(ids)>100:m.fail('Уточните состав группы')
        students=[db.get(User,sid) for sid in ids]
        if any(not s or s.role!='student' or s.deleted_at or not m.visible(db,u,s.id) for s in students):m.fail('Состав группы изменился. Повторите команду.',409)
        if u.role!='admin' and any(s.group_id and (old:=db.get(Group,s.group_id)) and old.teacher_id!=u.id for s in students):m.fail('Перенос из группы другого преподавателя выполняет администратор',403)
        name=str(data.slots.get('name','')).strip()[:160]
        if not name:m.fail('Укажите название группы')
        group=Group(name=name,teacher_id=u.id);db.add(group);db.flush()
        for s in students:s.group_id=group.id
        db.commit()
        result={'preview':f'Группа «{name}» создана. Добавлено учеников: {len(students)}.','action':{'kind':'navigate','to':f'/users?group={group.id}'},'slots':{'group_id':group.id}}
    elif data.intent=='create_student':
        from argon2 import PasswordHasher
        name=str(data.slots.get('name','')).strip()
        group=db.get(Group,int(data.slots.get('group_id') or 0))
        if not group or u.role!='admin' and group.teacher_id!=u.id:m.fail('Группа недоступна',403)
        if len(name.split())<2 or len(name)>160:m.fail('Укажите фамилию и имя ученика')
        if db.scalar(select(User.id).where(User.name==name,User.deleted_at.is_(None))):m.fail('Ученик с таким ФИО уже есть')
        alphabet={'й':'y','ц':'ts','у':'u','к':'k','е':'e','н':'n','г':'g','ш':'sh','щ':'sch','з':'z','х':'h','ъ':'','ф':'f','ы':'y','в':'v','а':'a','п':'p','р':'r','о':'o','л':'l','д':'d','ж':'zh','э':'e','я':'ya','ч':'ch','с':'s','м':'m','и':'i','т':'t','ь':'','б':'b','ю':'yu','ё':'yo'}
        parts=name.lower().replace('ё','е').split()
        base=''.join(alphabet.get(c,c) for c in parts[0])+'.'+''.join(alphabet.get(p[0],p[0]) for p in parts[1:])
        login=base;number=2
        while db.scalar(select(User.id).where(User.login==login)):login=f'{base}{number}';number+=1
        code=f'{secrets.randbelow(10000):04d}'
        student=User(login=login,name=name,role='student',group_id=group.id,password_hash=PasswordHasher().hash(code),must_change_password=True)
        db.add(student);db.flush();db.commit()
        result={'preview':f'{name} добавлен в группу «{group.name}».\nЛогин: {login}\nОдноразовый код для первого входа: {code}\nПосле входа ученик задаст свой пароль. Передайте код лично ученику.','slots':{'student_id':student.id},'links':[{'label':'Открыть список учеников','to':f'/users?group={group.id}'}]}
    elif data.intent=='publish_ticket':
        version=db.get(m.TicketVersion,int(data.slots.get('version_id') or 0))
        if not version:m.fail('Билет не найден',404)
        m.publish(version.id,u,db)
        result={'preview':f'Билет «{version.data["title"]}» опубликован. Теперь его можно отправить ученикам.','slots':{'version_id':version.id,'ticket_id':version.ticket_id},'action':{'kind':'navigate','to':f'/tickets/{version.id}'}}
    elif data.intent=='assign_ticket':
        from .schemas import AssignmentIn
        version=db.get(m.TicketVersion,int(data.slots.get('version_id') or 0))
        ids=data.slots.get('student_ids') or [data.slots.get('student_id')]
        students=[db.get(User,int(sid or 0)) for sid in dict.fromkeys(ids)]
        if not version or not students or any(not student or student.role!='student' or not m.visible(db,u,student.id) for student in students):m.fail('Билет или ученик недоступен',403)
        m.assign(AssignmentIn(version_id=version.id,students=[s.id for s in students],start_mode='self',training=True),u,db)
        result={'preview':f'Билет «{version.data["title"]}» отправлен: '+', '.join(s.name for s in students)+'.','slots':{'student_ids':[s.id for s in students],'version_id':version.id},'links':[{'label':'Назначения','to':'/assignments'}]}
    else:
        from .learning import MiniIn, save_question
        q=db.get(MiniQuestion,data.slots.get('question_id')) if data.intent=='edit_question' else None
        if data.intent=='edit_question' and not q:m.fail('Минивопрос не найден',404)
        options=data.slots.get('options') or []
        payload={**q.data,'active':q.active} if q else {'prompt':data.slots.get('prompt'),'answer':data.slots.get('answer'),'audio_text':data.slots.get('audio_text',''),'kind':'choice' if options else 'text','options':options,'level':1,'mode':'dds'}
        if q:payload[data.slots.get('field')]=data.slots.get('value')
        saved=save_question(MiniIn.model_validate(payload),q.id if q else None,u,db)
        result={'preview':f'Минивопрос №{saved["id"]} сохранён.','action':{'kind':'navigate','to':'/learning?question='+str(saved['id'])},'slots':{'question_id':saved['id']}}
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
