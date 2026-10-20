"""Versioned routing matrix. Unknown conditions are exposed, never guessed by Qwen."""
import json
import re
from functools import lru_cache
from .db import ROOT

MATRIX_FILE = 'classifier-routing-046-11.json'
SERVICES = {
    'O':'Служба 101','P':'Служба 101','Q':'Пожарно-спасательный центр Москвы',
    'R':'Пожарно-спасательный центр Москвы','S':'Пожарно-спасательный центр Москвы',
    'T':'Пожарно-спасательный центр Москвы','U':'МГПСС',
    'V':'Служба 102','W':'Служба 102','X':'Служба 102',
    'Y':'Служба 103','Z':'Служба 103','AA':'Служба 103','AB':'Служба 104','AC':'Служба 104',
    **dict.fromkeys(['AD','AE','AF','AG','AH'],'ЦЭМП'),
    'AI':'ФСБ','AJ':'ФСБ','AK':'Мособлгаз','AL':'ГБУ «Автомобильные дороги»',
    **dict.fromkeys(['AM','AN','AO'],'Мосгортранс'), 'AP':'Городское хозяйство',
    **dict.fromkeys(['AQ','AR','AS','AT'],'ГБУ «Гормост»'),
    'AU':'Канал имени Москвы','AV':'МГТС','AW':'МГТС','AX':'Московский метрополитен',
    'AY':'Мосводоканал','AZ':'МОЭК','BA':'Россети Московский регион','BB':'ОЭК','BC':'Мослифт',
    'BD':'ЦОДД','BE':'Деп. ЖКХ','BF':'ГКУ МОСБЕЗ','BG':'ГКУ МОСБЕЗ',
    'BH':'Аппарат Мэра','BI':'Москоллектор','BJ':'РЖД','BK':'Департамент образования',
    'BL':'Московско-Окское БВУ','BM':'Военная комендатура','BN':'ОАТИ','BO':'Мосводосток',
    'BP':'Департамент природопользования','BQ':'Департамент труда и социальной защиты',
    'BR':'РСВО','BS':'ЭВАЖД','BT':'МСППН','BU':'ГБУ Ритуал','BV':'ДТУ','BW':'Росгвардия',
    'BX':'Территориальные ОИВ','BY':'Территориальные ОИВ ТиНАО',
    'BZ':'Автомобильные дороги АО г. Москвы','CA':'Департамент строительства',
    'CB':'Департамент строительства','CC':'Комитет ветеринарии','CD':'Мосжилинспекция',
    'CE':'Департамент культуры','CF':'ЦСА имени Е. П. Глинки','CG':'ГКУ НТУ','CH':'ФСО',
    'CI':'ГУП МСР','CJ':'Комитет по туризму','CK':'Департамент градостроительной политики',
    'CL':'Департамент градостроительной политики',
}
CONDITIONS = {
    'O':'!access','P':'access','Q':'!rescue','R':'threat','S':'victims','T':'access',
    'V':'!police','W':'crime','X':'victims','Y':'!victims','Z':'victims','AA':'absent',
    'AB':'!gas','AC':'gas','AD':'!medical_flags','AE':'threat','AF':'victims',
    'AG':'medical','AH':'evacuation','AI':'!mass','AJ':'mass',
    'AM':'!transport_flags','AN':'victims','AO':'road_blocked',
    'AQ':'!bridge_flags','AR':'tunnel','AS':'pedestrian_bridge','AT':'road_bridge',
    'AW':'telecom','CA':'!construction','CB':'construction','CE':'culture_list',
    'BX':'old_moscow','BY':'tinao',
}


@lru_cache(maxsize=1)
def matrix():
    path = ROOT/'content'/MATRIX_FILE
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'source':{},'rows':[]}


def _norm(text):
    return re.sub(r'\s+', ' ', str(text or '').casefold().replace('ё','е')).strip()


def flags(card):
    from .scenario_facts import positive_facts
    traits = card.get('traits') or []
    if isinstance(traits,str):
        traits=[traits]
    raw = _norm(' '.join(str(card.get(k,'')) for k in ['incident_type','description','object'])+' '+' '.join(traits))
    text = positive_facts(raw)
    has = lambda pattern: bool(re.search(pattern,text))
    victims = {'yes':True,'no':False}.get(card.get('victims'))
    # Unknown casualties are not silently treated as absent.
    if victims is None and has(r'есть пострадавш|ранен|погибш'):
        victims = True
    territory = _norm(' '.join(str(card.get(k,'')) for k in ['city','region','district','area']))
    tinao = bool(re.search(r'тинао|троицк|новомосков|вороновск|коммунар|щербин|сосенск',territory))
    moscow = 'москва' in territory
    result = {
        'victims':victims, 'absent':card.get('victims_absent') in (True,'yes') or
            bool(re.search(r'пострадавш\w*\s+не\s+на\s+месте|пострадавш\w*\s+покинул\w*\s+место',raw)),
        'access':card.get('blocked')=='yes' or 'нет доступа' in raw or has(r'заблокирован'),
        'threat':has(r'угроза людям|угрожает людям'), 'crime':has(r'правонаруш|поджог|нападен'),
        'gas':has(r'газифиц|газовая плита|газовая колонка|есть газ|проведен газ'),
        'medical':has(r'медицинск.*помощ|нужна скорая'), 'evacuation':has(r'эвакуац'),
        'mass':None, 'road_blocked':has(r'перекры.*движ|перекры.*проезж|движение перекры'),
        'tunnel':has(r'тонн?ел'), 'pedestrian_bridge':has(r'пешеходн.*(?:мост|переход)'),
        'road_bridge':has(r'автомобильн.*мост|эстакад'),
        'telecom':has(r'объект.*связи|телефонн.*станц'),
        'construction':has(r'стройк|строительн.*объект'), 'culture_list':card.get('culture_list'),
        'tinao':tinao if moscow or tinao else None,
        'old_moscow':not tinao if moscow or tinao else None,
    }
    try:
        count=int(card.get('victims_count') or 0)
        if count or victims is False:result['mass']=count>5
    except (TypeError,ValueError):
        pass
    def any_known(keys):
        values=[result[k] for k in keys]
        return True if True in values else None if None in values else False
    for name,keys in [('rescue',['threat','victims','access']),('police',['crime','victims']),
                      ('medical_flags',['threat','victims','medical','evacuation']),
                      ('transport_flags',['victims','road_blocked']),
                      ('bridge_flags',['tunnel','pedestrian_bridge','road_bridge'])]:
        result[name]=any_known(keys)
    return result


def resolve(card):
    data=matrix()
    code=str(card.get('classifier_code') or '')
    rows=[r for r in data['rows'] if r['code']==code] if code else [r for r in data['rows'] if _norm(r['title'])==_norm(card.get('incident_type'))]
    report={'matched':len(rows)==1,'services':[],'entries':[],'excluded':[],'unresolved':[],
            'source':data['source'],'warning':''}
    if card.get('city') and _norm(card['city']) not in ('москва','г. москва','г москва','город москва'):
        report.update(matched=False,warning='Матрица относится к Москве. Для другого города проверьте получателей вручную.')
        return report
    if len(rows)!=1:
        report['warning']='Для этого названия нет однозначной строки в матрице 046_11. Получателей должен проверить преподаватель.'
        return report
    row=rows[0];report.update(code=row['code'],row=row['row'],lead_service=row['lead_service'],scenario=row['scenario'])
    values=flags(card)
    # A default service classification remains usable when the workbook has no
    # alternate value for the selected feature. Keep the actual source cell.
    fallbacks={'O':['P'],'Q':['R','S','T'],'V':['W','X'],'Y':['Z','AA'],'AB':['AC'],
               'AD':['AE','AF','AG','AH'],'AI':['AJ'],'AM':['AN','AO'],
               'AQ':['AR','AS','AT'],'CA':['CB']}
    headers={c['column']:c['headers'] for c in data['columns']}
    for col,cell in row['cells'].items():
        service=SERVICES[col];value=str(cell.get('value') or '').strip()
        entry={'service':service,'cell':f"{col}{row['row']}",'value':value,'condition':headers[col][-1]}
        if cell.get('note'):
            entry['note']=cell['note']
            if 'исключено' in _norm(cell['note']):
                report['excluded'].append(entry);continue
        if not value:continue
        if re.search(r'нет реагирования|без оповещения',value,re.I):
            report['excluded'].append(entry);continue
        condition=CONDITIONS.get(col)
        applicable=True
        if condition:
            applicable=values.get(condition.lstrip('!'))
            if applicable is not None and condition.startswith('!'):applicable=not applicable
            if applicable is False and col in fallbacks:
                alternatives=[other for other in fallbacks[col]
                              if values.get(CONDITIONS[other]) is True]
                if alternatives and not any(row['cells'].get(other,{}).get('value') for other in alternatives):
                    applicable=True
                    entry['fallback']='В матрице отсутствует отдельный код для выбранного признака.'
        if applicable is None:
            report['unresolved'].append(entry);continue
        if applicable:
            report['entries'].append(entry)
            if service not in report['services']:report['services'].append(service)
    if report['unresolved']:
        report['warning']='Часть условий назначения не уточнена: '+', '.join(dict.fromkeys(e['service'] for e in report['unresolved']))+'. Проверьте признаки и получателей.'
    return report


def seed_services(db):
    """Only add missing reference entries; preserve administrator edits and disabled services."""
    from .classroom_models import ServiceDefinition
    for name in sorted(set(SERVICES.values())):
        if not db.get(ServiceDefinition,name):
            db.add(ServiceDefinition(name=name,config={'tags':[],'questions':[],'rules':[],'source':'classifier-046_11'}))
    db.flush()
