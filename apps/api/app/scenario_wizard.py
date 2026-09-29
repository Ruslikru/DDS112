"""Small-step authoring: explicit facts constrain the locally generated draft."""
import json
import logging
import re
import secrets
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import main as m
from .db import Classifier
from .classroom_models import ServiceDefinition
from .voice import runtime
def complete(*args,**kwargs):
    try:return runtime.complete_pre(*args,**kwargs)
    except Exception as e:m.fail(str(e),503)
from .dds_scenarios import generated_dds, default_brigade_reports
from .schemas import TicketData
from .scenario_facts import base_facts, enrich_facts, GEOGRAPHY_PROMPT, scene_seed, scene_matches
from .ticket_difficulty import assess_wizard, legacy_level, apply_difficulty, DIFFICULTY_HINTS

router=APIRouter(prefix='/api')
class WizardIn(BaseModel):
    incident_type:str=Field(min_length=3,max_length=300)
    mode:Literal['112','dds']='dds'
    victims_state:Literal['yes','no','unknown']='unknown'
    victims_count:int=Field(default=0,ge=0,le=10000)
    animals:bool=False
    district:str=Field(default='',max_length=160)
    own_service:str=Field(default='ДДС района',max_length=160)
    services:list[str]=Field(min_length=1,max_length=30)
    traits:list[str]=Field(default_factory=list,max_length=12)
    affiliation:str=''
    difficulty_stars:int=Field(default=0,ge=0,le=5)

@router.post('/ai/wizard')
def wizard(data:WizardIn,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    active_services=db.scalars(select(ServiceDefinition).where(ServiceDefinition.active==True)).all()
    available={service.name for service in active_services}
    if any(s not in available for s in data.services) or data.own_service not in available:m.fail('Выберите действующие службы')
    if data.incident_type.strip().casefold() in {'пострадавшие','скорая помощь','полиция'}:
        m.fail('Выберите конкретное происшествие, например «Трамвай сход с рельс» или «Травма»')
    known_type=bool(db.scalar(select(Classifier.code).where(Classifier.title==data.incident_type).limit(1)))
    service_tag=any(data.incident_type.casefold() in {tag.strip().casefold() for tag in (service.config or {}).get('tags',[])}
                    for service in active_services if service.name in data.services)
    if not known_type and not service_tag:m.fail('Выберите тип из классификатора или тег выбранной службы')
    if data.victims_state=='yes' and data.victims_count<1:m.fail('Укажите количество пострадавших')
    facts=base_facts(data.incident_type)
    data.district=facts['area']
    keys=['description']
    schema={'type':'object','properties':{k:{'type':'string'} for k in keys},'required':keys,'additionalProperties':False}
    db.rollback()
    victims=f"Пострадавших людей: {data.victims_count}." if data.victims_state=='yes' else 'Пострадавших людей нет.' if data.victims_state=='no' else 'Наличие пострадавших людей неизвестно.'
    seed=scene_seed(data.incident_type,data.traits)
    prompt=seed+' Признаки: '+', '.join(data.traits) if data.traits else seed
    generated,meta=complete(GEOGRAPHY_PROMPT+' Rewrite the supplied Russian witness report in natural Russian, 2 or 3 short sentences. Preserve its specific object and visible signs. Do not add an address, casualties, responders or rescue actions. Return JSON with one field: description.',prompt,schema,tokens=220,temperature=.2)
    if any(not isinstance(generated.get(k),str) or not generated[k].strip() for k in keys):m.fail('Модель вернула неполный черновик. Повторите.',502)
    facts.update(generated)
    if not scene_matches(data.incident_type,data.traits,facts['description']) or re.search(r'\b(?:район|округ)\b',facts['description'].casefold()):
        facts['description']=seed
    victims=f"Пострадавших людей: {data.victims_count}." if data.victims_state=='yes' else 'Пострадавших людей нет.' if data.victims_state=='no' else 'Наличие пострадавших людей неизвестно.'
    if data.animals:victims+=' Есть пострадавшие животные.'
    facts.update(victims=victims,victims_state=data.victims_state)
    enrich_facts(facts,data)
    first=facts['description'].split('.')[0].strip()
    facts['title']=f"{first[:110]} — {facts['street']}"[:200]
    from .learning import automatic_services
    data.services=list(dict.fromkeys(data.services+automatic_services(db,{'incident_type':data.incident_type,'description':facts['description'],'traits':facts['traits'],'victims':data.victims_state,'object':facts['object']})))
    stars,reason=assess_wizard(data,facts,data.services)
    if data.difficulty_stars:stars=data.difficulty_stars;reason=DIFFICULTY_HINTS[stars]
    facts.update(difficulty_stars=stars,difficulty_reason=reason,difficulty=legacy_level(stars))
    reports=None
    if data.mode=='dds':
        defaults=default_brigade_reports(data,facts)
        report_schema={'type':'object','properties':{key:{'type':'string','maxLength':180} for key in ('approach','on_scene','outcome')},
                       'required':['approach','on_scene','outcome'],'additionalProperties':False}
        report_context={'service':data.own_service,'incident':data.incident_type,'description':facts['description'],
                        'victims':victims,'traits':facts['traits'],'address':f"{facts['city']}, {facts['street']}, дом {facts['house']}"}
        try:
            generated_reports,_=complete(
                'Напиши на русском три коротких, разных и живых доклада старшего бригады диспетчеру по телефону. '
                'Это учебный сценарий. 1 approach: бригада едет к адресу, при необходимости сообщает конкретную помеху в пути; '
                '2 on_scene: бригада прибыла, описывает проверенное наблюдение и действие; '
                '3 outcome: сообщает конкретный результат и дальнейшее действие. '
                'Используй только факты JSON, не меняй происшествие, адрес и число пострадавших, не выдумывай диагноз. '
                'Госпитализацию упоминай только для скорой помощи и только если пострадавшие есть. '
                'Каждый доклад — одно предложение до 120 символов. Не повторяй адрес: он уже известен диспетчеру. '
                'Избегай одинаковых шаблонных фраз и названий полей. Верни только JSON.',
                json.dumps(report_context,ensure_ascii=False),report_schema,tokens=900,temperature=.25)
            ordered=[generated_reports.get(key) for key in ('approach','on_scene','outcome')]
            if all(isinstance(value,str) and 25<=len(value.strip())<=350 for value in ordered) and len({value.strip().casefold() for value in ordered})==3:
                text=' '.join(ordered).casefold()
                unrelated_tram='трамва' in data.incident_type.casefold() and bool(re.search(r'лестниц|ступен|квартир',text))
                if ('госпитал' not in text or data.own_service=='Служба 103' and data.victims_state=='yes') and not unrelated_tram:
                    reports=[defaults[0]]+[value.strip() for value in ordered]
        except Exception as error:
            logging.warning('Brigade report generation fell back: %s',error)
        meta['brigade_reports']='model' if reports else 'fallback'
    ticket=generated_dds(data,facts,meta,reports=reports).model_dump();ticket['difficulty']=facts['difficulty'];task=ticket['tasks'][0]
    classifier=db.scalar(select(Classifier).where(Classifier.title==data.incident_type).limit(1))
    incident_name=data.incident_type.casefold()
    classifier_signs=[tag for tag in (classifier.traits or []) if tag.casefold() not in {incident_name,'дтп','дтп пострадавшие','сход трамвая с рельс'}] if classifier else []
    selected_signs=facts['traits']+classifier_signs
    if data.victims_state=='yes':selected_signs.append('Есть пострадавшие')
    elif data.victims_state=='no':selected_signs.append('Нет пострадавших')
    task['traits']=list(dict.fromkeys(selected_signs))
    task['initial_card'].update(traits=facts['traits'],victims_count=str(data.victims_count) if data.victims_state=='yes' else '')
    if data.mode=='112':
        expected=task['initial_card'].copy()
        task.update(mode='112',title=facts['title'],intro=facts['description'],initial_card={},expected_card=expected,
            questions=[{'id':'address','question':'Где это произошло?','answer':f"{facts['city']}, {facts['street']}, дом {facts['house']}, район {facts['area']}. {facts['address_note']}"},
                       {'id':'name','question':'Как вас зовут?','answer':facts['caller_name']},
                       {'id':'phone','question':'По какому номеру можно с вами связаться?','answer':facts['phone']},
                       {'id':'access','question':'Как пройти к месту происшествия?','answer':facts['address_note']+('. Подъезд '+facts['entrance']+', этаж '+facts['floor']+', домофон '+facts['code'] if facts.get('entrance') else '')},
                       {'id':'victims','question':'Есть пострадавшие?','answer':victims},
                       {'id':'details','question':'Что произошло?','answer':facts['description']}],
            service_events=[],contacts=[],limit_seconds=300,
            routing=[{'type':data.incident_type,'services':[data.own_service]}],
            criteria=[{'id':k,'label':label,'kind':'field','field':k,'expected':expected[k],'weight':15,'critical':k=='street'} for k,label in [('street','Точная улица'),('house','Номер дома'),('incident_type','Тип происшествия'),('victims','Сведения о пострадавших')]]+
                [{'id':'service-'+str(i),'kind':'service','expected':s,'label':'Оповещена '+s,'weight':10} for i,s in enumerate(data.services)]+
                [{'id':'description','kind':'manual','expected':facts['description'],'label':'Понятное описание обстоятельств','weight':20}])
        from .caller import generated_details, enrich_task
        task['scenario_details']=generated_details(task)
        if data.animals:task['scenario_details']['animals']='Есть пострадавшие животные.'
        ticket['tasks'][0]=enrich_task(task)
        ticket['title']=facts['title']
    if data.difficulty_stars:apply_difficulty(ticket,facts,data.difficulty_stars)
    validated=TicketData.model_validate(ticket).model_dump()
    m.audit(db,u,'wizard_draft_generated',detail={'incident':data.incident_type,**meta});db.commit()
    return {'data':validated,'meta':meta}

@router.post('/attempts/{id}/routing-preview')
def routing(id:int,data:dict,u=Depends(m.current),db=Depends(m.getdb)):
    p=db.get(m.Attempt,id)
    if not p or p.student_id!=u.id or p.snapshot['mode']!='112':m.fail('Карточка недоступна',403)
    from .domain import routes
    from .learning import automatic_services
    return {'services':list(dict.fromkeys(routes(p.snapshot,data)+automatic_services(db,data)))}
