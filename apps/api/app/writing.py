"""Offline spelling hints and exact address checks. Never silently fixes a student's text."""
import re
from functools import lru_cache

@lru_cache(maxsize=1)
def dictionary():
    from spellchecker import SpellChecker
    spell=SpellChecker(language='ru',distance=1)
    spell.word_frequency.load_words(['ддс','мчс','жкх','аон','цодд','моэк','мослифт','мосводоканал','росгвардия'])
    return spell

def spelling(text):
    corrections={'задымленее':'задымление','пожарр':'пожар','постродавшие':'пострадавшие','проишествие':'происшествие','происшествее':'происшествие','заявител':'заявитель','растояния':'расстояния','растояние':'расстояние','растоянии':'расстоянии'}
    return [{'message':'Возможная опечатка: '+corrections[m.group().lower()], 'fragment':m.group(), 'offset':m.start(), 'kind':'spelling'}
            for m in re.finditer(r'\b[А-Яа-яЁё]{3,}\b',text) if m.group().lower() in corrections][:30]

def address_checks(card,expected):
    labels={'street':'Название улицы','house':'Номер дома','building':'Корпус','structure':'Строение'}
    def normalize(x):return ' '.join(str(x).strip().casefold().split())
    return [{'message':label+' отличается от данных задания','fragment':str(card.get(field,'')),
             'expected':str(expected[field]),'field':field,'kind':'address'}
        for field,label in labels.items() if expected.get(field) and normalize(card.get(field,''))!=normalize(expected[field])]
