"""Deterministic Russian speech text; ticket facts remain unchanged."""
import re

ONES = 'ноль один два три четыре пять шесть семь восемь девять'.split()
TEENS = 'десять одиннадцать двенадцать тринадцать четырнадцать пятнадцать шестнадцать семнадцать восемнадцать девятнадцать'.split()
TENS = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто']
HUNDREDS = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот', 'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']

def number(n, feminine=False):
    n = int(n)
    if n == 0: return ONES[0]
    if n >= 1000000000: return ' '.join(ONES[int(d)] for d in str(n))
    parts = []
    for scale, forms in [(1000000, ('миллион', 'миллиона', 'миллионов')), (1000, ('тысяча', 'тысячи', 'тысяч'))]:
        if n >= scale:
            count, n = divmod(n, scale)
            form = 2 if 11 <= count % 100 <= 14 else 0 if count % 10 == 1 else 1 if 2 <= count % 10 <= 4 else 2
            parts.extend([number(count, scale == 1000), forms[form]])
    if n >= 100: parts.append(HUNDREDS[n // 100]); n %= 100
    if 10 <= n < 20: parts.append(TEENS[n - 10])
    else:
        if n >= 20: parts.append(TENS[n // 10])
        if n % 10: parts.append({1: 'одна', 2: 'две'}.get(n % 10, ONES[n % 10]) if feminine else ONES[n % 10])
    return ' '.join(parts)

def spoken_text(text):
    def phone(match):
        return ' '.join(ONES[int(d)] for d in match[0] if d.isdigit())
    text = re.sub(r'(?<!\w)(?:\+7|8)[\s(\-]*\d{3}[\s)\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)', phone, text)
    text = re.sub(r'(?<!\d)(\d{1,2}):(\d{2})(?!\d)', lambda m: number(m[1]) + ' часов ' + number(m[2]) + ' минут', text)
    text = re.sub(r'(\d+)[,.](\d+)', lambda m: number(m[1]) + ' точка ' + ' '.join(ONES[int(d)] for d in m[2]), text)
    text = re.sub(r'(\d+)\s*/\s*(\d+)', lambda m: number(m[1]) + ' дробь ' + number(m[2]), text)
    text = re.sub(r'\d+', lambda m: ' '.join(ONES[int(d)] for d in m[0]) if len(m[0]) > 1 and m[0].startswith('0') else number(m[0]), text)
    return text.replace('№', ' номер ').replace('%', ' процентов ')

def identity_answer(text, questions):
    """Do not ask a small generative model to remember the caller's identity."""
    query = text.casefold().replace('ё', 'е')
    if not re.search(r'зовут|ваше?\s+имя|фамили|отчеств|представьтесь|к\s+вам\s+обращаться|кто\s+(?:вы|говорит|звонит)', query):
        return None
    return next((q for q in questions if q['id'] == 'name' or re.search(r'зовут|ваше?\s+имя|обращаться|фамили', q['question'], re.I)), None)


def fact_answer(text, context):
    questions=context.get('questions',[])
    query=text.casefold().replace('ё','е')
    # Identity of a victim or a third party must not be replaced by caller identity.
    if not re.search(r'пострадавш|сосед|ребен|ребён|муж|жен',query):
        identity=identity_answer(text,questions)
        if identity:return identity
    specific=[('vehicle_count',r'сколько.*(?:машин|авто|транспорт)|количеств.*(?:машин|авто)'),('vehicle_colors',r'цвет'),('children',r'дети|детей|ребен'),('animals',r'животн|собак|кошк'),('kilometer',r'километр'),('direction',r'направлен|сторону'),('blocked_people',r'заблок|зажат'),('fuel',r'топлив|бензин|разлив'),('smoke_source',r'откуда.*дым|источник.*дым'),('fire',r'пламя|горит'),('when',r'когда|давно'),('access',r'подъехать|проезд'),('location',r'вы.*сейчас|вы.*наход'),('people_count',r'сколько(?!.*(?:пострад|ранен|травм)).*(?:людей|человек)')]
    for key,pattern in specific:
        if re.search(pattern,query):
            q=next((q for q in questions if q['id']==key),None)
            if q:return q
    intents=[*[(k,pattern,pattern) for k,pattern in [('street',r'улиц'),('house',r'номер дома|какой дом|дом какой'),('entrance',r'подъезд'),('floor',r'этаж'),('apartment',r'квартир'),('code',r'домофон')]],('address',r'адрес|где.*(?:наход|случ|произош|жив)|куда.*(?:ехать|приех|направ)',r'адрес'),
             ('phone',r'телефон|номер.*(?:связ|перезвон)',r'телефон'),
             ('victims',r'пострад|ранен|травм|жертв',r'пострадав|ранен'),
             ('details',r'что.*(?:случ|произош)|обстоятельств',r'произош|случил')]
    for key,pattern,question_pattern in intents:
        if re.search(pattern,query):
            found=next((q for q in questions if q['id']==key),None) or next((q for q in questions if re.search(question_pattern,q['question'],re.I)),None)
            if found:return found
    return None
