"""Small-step authoring: explicit facts constrain the locally generated draft."""
import re
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import main as m
from .db import Classifier
from .classroom_models import ServiceDefinition
from local_ai.engine import engine as text_engine
def complete(*args,**kwargs):
    try:return text_engine.complete(*args,**kwargs)
    except Exception as e:m.fail(str(e),503)
from .dds_scenarios import generated_dds
from .schemas import TicketData
from .scenario_facts import base_facts, clean_story, enrich_facts, GEOGRAPHY_PROMPT, scene_seed, scene_matches
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
    address:str=Field(default='',max_length=160)
    access_source:Literal['auto','card','service_history','caller','unknown']='auto'

def split_address(value):
    """«улица Ленина, дом 5» → («улица Ленина», «5»); without a number the street is kept and the house stays random."""
    value=re.sub(r'\s+',' ',value).strip(' ,.')
    found=re.search(r'^(.*?)[,\s]+(?:дом|д\.)?\s*(\d+[а-яa-z]?(?:/\d+)?(?:\s*к(?:орп\.?|орпус)?\s*\d+)?)$',value,flags=re.I)
    if found and found.group(1).strip():return found.group(1).strip(' ,'),found.group(2).strip()
    return value,''

@router.post('/ai/wizard')
def wizard(data:WizardIn,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    from .training_modes import operator_112_enabled
    if data.mode=='112' and not operator_112_enabled(db):m.fail('Режим 112 отключён администратором')
    validated,meta=build_draft(data,db)
    m.audit(db,u,'wizard_draft_generated',detail={'incident':data.incident_type,**meta});db.commit()
    return {'data':validated,'meta':meta}

def build_draft(data,db,fixed=None,meta=None):
    """One draft from explicit facts. `fixed` holds facts the author already gave
    (description, caller_name, object, seed — the scene the model rewrites).
    With a fixed description, all derived stages are built without another model call."""
    fixed=fixed or {}
    active_services=db.scalars(select(ServiceDefinition).where(ServiceDefinition.active==True)).all()
    available={service.name for service in active_services}
    if any(s not in available for s in data.services) or data.own_service not in available:m.fail('Выберите действующие службы')
    if data.incident_type.strip().casefold() in {'пострадавшие','скорая помощь','полиция'}:
        m.fail('Выберите конкретное происшествие, например «Трамвай сход с рельс» или «Травма»')
    known_type=bool(db.scalar(select(Classifier.code).where(Classifier.title==data.incident_type).limit(1)))
    service_tag=any(data.incident_type.casefold() in {tag.strip().casefold() for tag in (service.config or {}).get('tags',[])}
                    for service in active_services if service.name in data.services)
    if not known_type and not service_tag and not fixed.get('trusted_type'):m.fail('Выберите тип из классификатора или тег выбранной службы')
    if data.victims_state=='yes' and data.victims_count<1:m.fail('Укажите количество пострадавших')
    facts=base_facts(data.incident_type)
    if data.address.strip():
        # The teacher named the place: street and house replace the random ones, the district stays from the table.
        street,house=split_address(data.address)
        facts['street']=street
        if house:facts['house']=house
    if fixed.get('caller_name'):facts['caller_name']=fixed['caller_name']
    place=fixed.get('place') or {}
    if place.get('city') and place['city'].casefold()!='москва':
        # Another city: the Moscow district and okrug from the table would contradict it.
        facts.update(city=place['city'],region='',district='',area='')
    data.district=facts['area']
    db.rollback()
    if fixed.get('description'):
        facts['description']=fixed['description']
        meta=dict(meta or {'model':'rules','mode':'rules','seconds':0})
    else:
        keys=['description']
        schema={'type':'object','properties':{k:{'type':'string'} for k in keys},'required':keys,'additionalProperties':False}
        seed=fixed.get('seed') or scene_seed(data.incident_type,data.traits)
        prompt=(seed or ('Тип происшествия: '+data.incident_type))+(' Признаки: '+', '.join(data.traits) if data.traits else '')
        instruction=(' Rewrite the supplied Russian witness report in natural Russian, 2 or 3 short sentences. Preserve its specific object and visible signs.' if seed else
                     ' Create a fictional Russian training report of 2 or 3 short sentences for the supplied incident subtype. Describe a concrete object and observable signs; preserve the incident subtype exactly. Do not merely repeat its title or claim that circumstances are unknown.')
        try:
            generated,meta=complete(GEOGRAPHY_PROMPT+instruction+' Do not add an address, casualties, responders or rescue actions. Return JSON with one field: description.',prompt,schema,tokens=220,temperature=.2)
        except Exception:
            if not seed:m.fail('Для этого типа нет готового сценария. Опишите конкретные обстоятельства происшествия и повторите создание.',422)
            raise
        if any(not isinstance(generated.get(k),str) or not generated[k].strip() for k in keys):m.fail('Модель вернула неполный черновик. Повторите.',502)
        facts['description']=clean_story(generated['description'])
        if len(facts['description'])<12 or not scene_matches(data.incident_type,data.traits,facts['description']) or re.search(r'\b(?:район|округ)',facts['description'].casefold()):
            if not seed:m.fail('Не удалось составить конкретные обстоятельства для этого типа. Добавьте описание происшествия.',422)
            facts['description']=seed
    victims=f"Пострадавших людей: {data.victims_count}." if data.victims_state=='yes' else 'Пострадавших людей нет.' if data.victims_state=='no' else 'Наличие пострадавших людей неизвестно.'
    if data.animals:victims+=' Есть пострадавшие животные.'
    if fixed.get('victims_note'):victims+=' '+fixed['victims_note']
    facts.update(victims=victims,victims_state=data.victims_state)
    enrich_facts(facts,data)
    if fixed.get('object'):facts['object']=fixed['object']
    facts.update({key:place[key] for key in ('apartment','entrance','floor') if place.get(key)})
    facts['title']=f"{data.incident_type}: {facts['street']}, дом {facts['house']}"[:200]
    from .learning import automatic_services
    data.services=list(dict.fromkeys(data.services+automatic_services(db,{'incident_type':data.incident_type,'description':facts['description'],'traits':facts['traits'],'victims':data.victims_state,'victims_count':data.victims_count,'object':facts['object'],
        **{key:facts.get(key,'') for key in ('city','region','district','area')}})))
    stars,reason=assess_wizard(data,facts,data.services)
    if data.difficulty_stars:stars=data.difficulty_stars;reason=DIFFICULTY_HINTS[stars]
    facts.update(difficulty_stars=stars,difficulty_reason=reason,difficulty=legacy_level(stars))
    reports=None
    if data.mode=='dds':
        if data.access_source=='service_history' and not any(s!=data.own_service for s in data.services):
            m.fail('Для сведений из истории другой службы добавьте вторую службу.')
        # The scenario defines outcomes before prose: no unconstrained second model call.
        meta['brigade_reports']='scenario'
    ticket=generated_dds(data,facts,meta,reports=reports).model_dump();ticket['difficulty']=facts['difficulty'];task=ticket['tasks'][0]
    classifier=db.scalar(select(Classifier).where(Classifier.title==data.incident_type).limit(1))
    incident_name=data.incident_type.casefold()
    classifier_signs=[tag for tag in (classifier.traits or []) if tag.casefold() not in {incident_name,'дтп','дтп пострадавшие','сход трамвая с рельс'}] if classifier else []
    selected_signs=facts['traits']+classifier_signs
    if data.victims_state=='yes':selected_signs.append('Есть пострадавшие')
    elif data.victims_state=='no':selected_signs.append('Нет пострадавших')
    task['traits']=list(dict.fromkeys(selected_signs))
    task['initial_card'].update(traits=facts['traits'],victims_count=str(data.victims_count) if data.victims_state=='yes' else '')
    from .classifier_routing import resolve
    from .scenario_contract import scenario_fact_snapshot
    task['scenario']['facts'].update(scenario_fact_snapshot(task['initial_card']))
    task['scenario']['routing']=resolve(task['initial_card'])
    if data.mode=='112':
        expected=task['initial_card'].copy()
        task.update(mode='112',scenario={},title=facts['title'],intro=facts['description'],initial_card={},expected_card=expected,
            questions=[{'id':'address','question':'Где это произошло?','answer':f"{facts['city']}, {facts['street']}, дом {facts['house']}"+(f", район {facts['area']}" if facts['area'] else '')+f". {facts['address_note']}"},
                       {'id':'name','question':'Как вас зовут?','answer':facts['caller_name']},
                       {'id':'phone','question':'По какому номеру можно с вами связаться?','answer':facts['phone']},
                       {'id':'access','question':'Как пройти к месту происшествия?','answer':facts['address_note']+('. Подъезд '+facts['entrance'] if facts.get('entrance') else '')+(', этаж '+facts['floor'] if facts.get('floor') else '')+(', домофон '+facts['code'] if facts.get('code') else '')},
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
    apply_difficulty(ticket,facts,stars)
    if data.mode=='dds':
        from .scenario_contract import validate_scenario
        problems=validate_scenario(ticket['tasks'][0])
        if problems:m.fail('Сценарий требует исправления: '+'; '.join(problems),422)
    return TicketData.model_validate(ticket).model_dump(),meta

@router.post('/attempts/{id}/routing-preview')
def routing(id:int,data:dict,u=Depends(m.current),db=Depends(m.getdb)):
    p=db.get(m.Attempt,id)
    if not p or p.student_id!=u.id or p.snapshot['mode']!='112':m.fail('Карточка недоступна',403)
    from .domain import routes
    from .learning import automatic_services
    return {'services':list(dict.fromkeys(routes(p.snapshot,data)+automatic_services(db,data)))}
