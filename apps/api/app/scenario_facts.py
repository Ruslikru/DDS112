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
    """A concrete subject helps the small local model avoid generic filler."""
    topic=incident.casefold()
    signs=' '.join(traits).casefold()
    if 'трамва' in topic or 'сход трамвая' in signs:
        scene='На улице трамвай сошёл с рельсов и остановился на путях. Пассажиры находятся в вагоне, движение трамваев остановлено.'
        if 'провод' in signs or 'контактн' in signs:
            scene+=' Рядом с вагоном повреждены провода контактной сети.'
        return scene
    if topic in ['дым','задымление']:
        return secrets.choice(['В подъезде жилого дома дым из мусоропровода. На лестничной площадке пахнет гарью. Открытого пламени не видно.', 'Из подвала жилого дома выходит густой дым. У входа чувствуется запах гари. Дверь подвала закрыта.'])
    if topic=='пожар':
        return secrets.choice(['Во дворе горит мусорный контейнер рядом с припаркованными автомобилями. Видно открытое пламя и густой дым.', 'В квартире жилого дома горит балкон. Дым поднимается к окнам верхних этажей. Дом газифицирован.'])
    if topic=='дтп':return 'На дороге рядом с жилым домом столкнулись два легковых автомобиля. Машины занимают одну полосу движения.'
    if topic in ['вода','коммунальная авария']:return 'В подъезде жилого дома из повреждённой трубы течёт вода. Вода растекается по полу и попадает к входной двери.'
    if topic=='лифт':return 'В жилом доме остановился лифт между этажами. В кабине находятся два человека, они отвечают через дверь.'
    if topic in ['скорая помощь','травма','пострадавшие']:return 'Во дворе жилого дома человек упал на ступенях. Он в сознании, жалуется на сильную боль в ноге и не может встать.'
    if topic in ['полиция','правонарушение']:return 'Во дворе жилого дома двое мужчин дерутся возле припаркованной машины. Очевидец наблюдает происходящее с безопасного расстояния.'
    return f'Очевидец сообщает о происшествии: {incident}.'


def scene_matches(incident, traits, description):
    """Reject a small model's unrelated story before it enters a ticket."""
    topic=incident.casefold()
    signs=' '.join(traits).casefold()
    story=description.casefold()
    if 'трамва' in topic or 'сход трамвая' in signs:
        return ('трамва' in story and ('рельс' in story or 'пут' in story)
                and not re.search(r'лестниц|ступен|подъезд|квартир',story)
                and ('провод' not in signs and 'контактн' not in signs or 'провод' in story or 'контактн' in story))
    if 'дтп' in topic:
        return any(word in story for word in ('автомоб','машин','трамва','автобус','мотоцикл'))
    if topic in ('пожар','задымление','дым'):
        return any(word in story for word in ('огонь','горит','плам','дым','задым','гарь'))
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
    police=bool(re.search(r'\bдтп\b|столкнов|трамва|сход с рельс|драка|краж|угроз|правонаруш|нападен',text))
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
    facts['object']='Жилой дом' if indoor else 'Участок улицы' if re.search(r'дтп|автомобил|столкнов|трамва|рельс',text) else 'Дворовая территория'
    facts['caller_status']='Очевидец'
    facts['address_note']='Вход со двора' if indoor else 'Рядом с указанным домом, со стороны проезжей части' if facts['object']=='Участок улицы' else 'Во дворе указанного дома'
    if indoor:
        facts.update(entrance=str(secrets.randbelow(4)+1),floor=str(secrets.randbelow(8)+1),code=str(secrets.randbelow(80)+10))
        if 'квартир' in text:facts['apartment']=str(secrets.randbelow(80)+1)
    return facts
