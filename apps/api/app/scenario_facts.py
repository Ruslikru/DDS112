"""Shared, internally consistent facts for fictional Moscow training calls."""
import re
import secrets

# Street/district pairs verified against Moscow's published address lists.
# https://www.mos.ru/upload/documents/oiv/prilojenie_2_2%281%29.pdf
# https://parking.mos.ru/upload/iblock/27f/gdmicqchuoiydjitk92fml55sremdl4m.pdf
MOSCOW_STREETS = [
    ('СВАО', 'Южное Медведково', 'Ясный проезд'),
    ('СВАО', 'Отрадное', 'улица Хачатуряна'),
    ('СВАО', 'Отрадное', 'улица Декабристов'),
    ('СВАО', 'Бибирево', 'улица Конёнкова'),
    ('СЗАО', 'Хорошёво-Мнёвники', 'набережная Новикова-Прибоя'),
]
GEOGRAPHY_PROMPT = 'Все истории происходят в Москве. Используй только переданный московский адрес, район и округ. Не заменяй их учебными или вымышленными названиями.'

def scene_seed(incident, traits=()):
    """Concrete fictional observations matched to the classifier's actual subtype.

    No canned story is safer than claiming a bare classifier heading is a scene.
    Unsupported types can be authored explicitly or described by the model.
    """
    topic=incident.casefold()
    signs=' '.join(traits).casefold()
    if 'трамва' in topic or 'сход трамвая' in signs:
        scene='На улице трамвай сошёл с рельсов и остановился на путях. Пассажиры находятся в вагоне, движение трамваев остановлено.'
        if 'провод' in signs or 'контактн' in signs:
            scene+=' Рядом с вагоном повреждены провода контактной сети.'
        return scene
    if re.search(r'пожар|возгоран',topic):
        for pattern,scene in [
            ('мусор|контейнер','Во дворе горит мусор в металлическом контейнере. Из контейнера поднимаются пламя и густой дым, рядом припаркованы автомобили.'),
            ('балкон','На балконе жилого дома горят вещи. Пламя видно с улицы, дым поднимается к окнам выше.'),
            ('квартир','Из окна квартиры жилого дома видны пламя и густой дым. На лестничной площадке чувствуется запах гари.'),
            ('машин|автомобил|транспорт','На обочине горит припаркованный автомобиль. Пламя выходит из моторного отсека, виден густой дым.'),
            ('школ|образовател','В кабинете школы горит мебель. Из окна выходит густой дым, в коридоре чувствуется запах гари.'),
            ('трав|раститель','На пустыре вдоль дороги горит сухая трава. Пламя распространяется по сухой растительности к ограждению.'),
            ('лес','На опушке леса горит сухая подстилка. Дым идёт между деревьями, огонь распространяется вдоль тропы.'),
            ('подвал','Из подвального окна жилого дома видны пламя и дым. У входа в подвал чувствуется сильный запах гари.'),
            ('подъезд','В подъезде жилого дома горят оставленные у лестницы вещи. Дым поднимается на верхние этажи.'),
            ('крыш|кровл','На крыше здания горит покрытие кровли. С улицы видны пламя и дым над краем крыши.'),
            ('гараж','Из гаража выходит густой дым. Через открытые ворота видно горящие вещи внутри.'),
            ('склад','В складском помещении горят коробки. Из дверного проёма выходит густой дым.'),
            ('магазин|торгов','В торговом помещении горит витрина с товаром. Дым выходит через входную дверь.'),
        ]:
            if re.search(pattern,topic):return scene
        if topic in ('пожар','возгорание'):
            return 'Во дворе горит мусорный контейнер рядом с припаркованными автомобилями. Видно открытое пламя и густой дым.'
        return ''
    if re.search(r'дым|задым',topic):
        if 'квартир' in topic:return 'Из окна квартиры выходит густой дым. На лестничной площадке пахнет гарью, открытого пламени не видно.'
        if 'подвал' in topic:return 'Из подвала жилого дома выходит густой дым. У входа чувствуется запах гари, открытого пламени не видно.'
        if 'автомобил' in topic:return 'Из-под капота автомобиля идёт густой дым. Возле машины пахнет горелой проводкой, открытого пламени не видно.'
        return 'В подъезде жилого дома дым из мусоропровода. На лестничной площадке пахнет гарью, открытого пламени не видно.'
    if 'дтп' in topic or 'дорожно-транспорт' in topic:
        return 'На дороге рядом с жилым домом столкнулись два легковых автомобиля. Машины занимают одну полосу движения.'
    if 'газ' in topic and 'взрыв' in topic:
        return 'В жилом доме произошёл хлопок газа. В окнах повреждены стёкла, из помещения выходит дым.'
    if 'газ' in topic:
        return 'В подъезде жилого дома чувствуется резкий запах газа. Запах сильнее возле двери подвала, источник визуально не виден.'
    if 'лифт' in topic:
        if re.search('застр|останов|блок',topic) or topic=='лифт':
            return 'В жилом доме остановился лифт между этажами. В кабине находятся два человека, они отвечают через дверь.'
        return 'В жилом доме не работает лифт. Пустая кабина стоит на первом этаже, двери не открываются при нажатии кнопки вызова.'
    if re.search('канализ|сточн',topic):
        return 'Из канализационного колодца во дворе вытекают сточные воды. Вода растекается по дорожке, чувствуется резкий запах.'
    if re.search('отоплен|теплоснабж|теплосет',topic):
        return 'Из повреждённой трубы отопления в подвале течёт горячая вода. В подвальном помещении виден пар, у входа образовалась лужа.'
    if re.search('электроснабж|отключение.*элект|нет.*свет|освещен',topic):
        return 'В подъезде жилого дома погас свет на лестнице и в квартирах. Соседи сообщают, что отключение произошло одновременно.'
    if re.search('отключ|отсутств|нет ',topic) and re.search('вод|водоснабж',topic):
        return 'В жилом доме прекратилась подача воды. При открытии кранов вода не идёт, соседи сообщают о таком же отключении.'
    if re.search('вод|труб|затоп|прорыв',topic) or topic=='коммунальная авария':
        return 'В подвале жилого дома из повреждённой трубы течёт вода. Вода покрывает пол и вытекает к входной двери.'
    if re.search('травм|падение.*человек',topic) or topic in ('скорая помощь','пострадавшие'):
        return 'Во дворе жилого дома человек упал на ступенях. Он в сознании, жалуется на сильную боль в ноге и не может встать.'
    if topic in ('полиция','правонарушение') or 'драк' in topic:
        return 'Во дворе жилого дома двое мужчин дерутся возле припаркованной машины. Очевидец наблюдает происходящее с безопасного расстояния.'
    if 'люк' in topic:
        return 'На пешеходной дорожке обнаружен открытый колодец без крышки люка. Ограждения вокруг отверстия нет, рядом проходят люди.'
    return ''


def scene_matches(incident, traits, description):
    """Reject title-only filler and a rewrite that changes the supplied object."""
    topic=incident.casefold()
    signs=' '.join(traits).casefold()
    story=description.casefold()
    if len(story.strip())<30 or re.search(r'^тип происшествия:|^происшествие:|очевидец сообщает о происшествии:|обстоятельства не (?:указаны|заданы)|требуется (?:описание|уточнить обстоятельства)',story):return False
    if 'трамва' in topic or 'сход трамвая' in signs:
        return ('трамва' in story and ('рельс' in story or 'пут' in story)
                and not re.search(r'лестниц|ступен|подъезд|квартир',story)
                and ('провод' not in signs and 'контактн' not in signs or 'провод' in story or 'контактн' in story))
    if 'дтп' in topic:
        return any(word in story for word in ('автомоб','машин','трамва','автобус','мотоцикл'))
    if re.search(r'пожар|возгоран|дым|задым',topic):
        if not any(word in story for word in ('огонь','горит','горят','плам','дым','задым','гарь','гари')):return False
        for subtype in ('мусор','квартир','балкон','подвал','подъезд','школ','гараж','склад'):
            if subtype in topic and subtype not in story:return False
        if re.search('машин|автомобил',topic) and not re.search('машин|автомобил',story):return False
    if 'лифт' in topic and 'лифт' not in story:return False
    return True


def phone():
    digits = ''.join(str(secrets.randbelow(10)) for _ in range(7))
    return f'+7 ({secrets.choice([916, 926, 903, 915])}) {digits[:3]}-{digits[3:5]}-{digits[5:]}'

def base_facts(incident):
    district, area, street = secrets.choice(MOSCOW_STREETS)
    return {'title':incident, 'caller_name':secrets.choice(['Алексей Викторович Смирнов', 'Елена Андреевна Соколова', 'Иван Сергеевич Петров']),
            'phone':phone(), 'city':'Москва', 'country':'Россия', 'region':'Москва',
            'district':district, 'area':area, 'street':street, 'house':str(secrets.randbelow(30)+1)}

def positive_facts(text):
    """Discard negated clauses before broad routing (e.g. 'дом не газифицирован')."""
    clauses=re.split(r'[.!?;\n,]', str(text).casefold())
    return ' '.join(c for c in clauses if not re.search(r'\b(не|нет|без|отсутств\w*)\b', c))

def semantic_services(services, card):
    traits=card.get('traits') or []
    if isinstance(traits,str):traits=[traits]
    text=positive_facts('. '.join([str(card.get(k,'')) for k in ['incident_type','description','object']]+traits))
    medical=card.get('victims')=='yes' or 'Есть пострадавшие' in traits or bool(re.search(r'травм|ранен|нужна скорая',text))
    gas=bool(re.search(r'\bгаз\w*|запах газа',text))
    fire=bool(re.search(r'пожар|задым|\bдым\b|горит|пламя',text))
    police=bool(re.search(r'\bдтп\b|столкнов|трамва|сход с рельс|драка|краж|угроз|правонаруш|нападен|поджог|подозреваем',text))
    result=[]
    for service in services:
        if (service.config or {}).get('rules'):
            continue  # Explicit administrator rules take precedence over tag matching.
        name=service.name.casefold()
        tags=(service.config or {}).get('tags',[])
        tag_text=re.sub(r'[^.!?]*животн[^.!?]*', '', text) if re.search(r'103|скор|медицин',name) and not medical else text
        match_tag=any(re.search(r'(?<!\w)'+re.escape(tag.strip().casefold())+r'(?!\w)',tag_text)
                      for tag in tags if len(tag.strip())>=3)
        if (medical and re.search(r'103|скор|медицин',name) or gas and re.search(r'104|газ',name)
            or fire and re.search(r'101|пожар',name) or police and re.search(r'102|полиц',name) or match_tag):
            result.append(service.name)
    return result

def enrich_facts(facts, config):
    text=(config.incident_type+'. '+facts['description']+'. '+'. '.join(config.traits)).casefold()
    selected=list(config.traits)
    for pattern,label in [(r'дым|задым','Дым'),(r'открытое пламя|горит','Открытое пламя'),
                          (r'запах гари','Запах гари'),(r'газифицирован|газовая плита|газовая колонка','Газифицированный дом'),
                          (r'мусоропровод','Мусоропровод'),(r'подъезд','Подъезд'),(r'квартир','Квартира'),
                          (r'заблокирован','Есть заблокированные'),(r'течёт вода|прорыв|утечка воды','Утечка воды')]:
        if re.search(pattern,positive_facts(text)):selected.append(label)
    selected=list(dict.fromkeys(selected))
    if config.animals:selected.append('Есть пострадавшие животные')
    facts['traits']=selected
    indoor=bool(re.search(r'подъезд|квартир|лифт|мусоропровод|подвал|в доме|жилого дома|дом газифицирован',text)) and not bool(re.search(r'во дворе|возле дома',text))
    yard=bool(re.search(r'во дворе|дворов\w*\s+(?:территор|площад)',text))
    facts['object']='Жилой дом' if indoor else 'Участок улицы' if not yard and re.search(r'дтп|автомобил|столкнов|трамва|рельс',text) else 'Дворовая территория'
    facts['caller_status']='Очевидец'
    facts['address_note']=('Въезд во двор справа от дома, через открытые ворота. Вход в подъезд со стороны двора.' if indoor else
        'Подъезд по улице к указанному дому. Место происшествия у правой обочины, рядом с пешеходным переходом.' if facts['object']=='Участок улицы' else
        'Въезд во двор слева от указанного дома, через открытые ворота. Место происшествия у площадки за воротами.')
    if indoor:
        facts.update(entrance=str(secrets.randbelow(4)+1),floor=str(secrets.randbelow(8)+1),code=str(secrets.randbelow(80)+10))
        if 'квартир' in text:facts['apartment']=str(secrets.randbelow(80)+1)
    return facts

def clean_story(text):
    """A model's scene without what the card holds elsewhere: invented district or okrug names
    («в районе Северный, округе Боровицкий») and sentences about casualties, which come from the victims field."""
    text=re.sub(r',?\s*(?:\bв\s+)?\b(?:район|округ)\w*\s+[А-ЯЁ][\w-]*(?:\s+[А-ЯЁ][\w-]*)*','',str(text))
    text=' '.join(s for s in re.split(r'(?<=[.!?])\s+',text) if not re.search(r'пострада|ранен',s.casefold()))
    return re.sub(r'\s+([.,!?])',r'\1',re.sub(r'\s+',' ',text)).strip()
