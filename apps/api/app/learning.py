"""Progress, attention drills and editable classroom catalogues."""
import os
import copy
import secrets
import statistics
import time
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select
from . import main as m
from .db import Attempt, User, Group, Assignment, TicketVersion
from .classroom_models import TrainingProfile, MiniQuestion, ApprovedAnswer, ServiceDefinition, Workstation

router=APIRouter(prefix='/api/learning')
DEFAULT_SERVICES={
    'Служба 101': ['пожар', 'задымление', 'дым'],
    'Служба 102': ['полиция', 'ДТП', 'правонарушение'],
    'Служба 103': ['скорая помощь', 'травма', 'пострадавшие'],
    'ДДС района': ['вода', 'лифт', 'коммунальная авария'],
}

def profile(db,sid):
    p=db.get(TrainingProfile,sid)
    if not p:p=TrainingProfile(user_id=sid,data={});db.add(p);db.flush()
    return p

def summary(db,sid):
    attempts=db.scalars(select(Attempt).where(Attempt.student_id==sid,Attempt.status=='completed').order_by(Attempt.id.desc()).limit(30)).all()
    assessments=[a.assessment for a in attempts if a.assessment]
    confirmed=[a for a in assessments if not a.get('pending') and not a.get('ai_preliminary') and not a.get('assisted')]
    scores=[a['score'] for a in confirmed if a.get('score') is not None]
    avg=round(statistics.mean(scores)) if scores else None
    p=profile(db,sid);intro=p.data.get('intro_complete',False)
    level=0 if not intro else 1 if len(scores)<3 else 4 if avg>=90 else 3 if avg>=75 else 2 if avg>=50 else 1
    levels={}
    for attempt in attempts:
        grade=attempt.assessment or {}
        if grade.get('score') is None or any(grade.get(k) for k in ('pending','ai_preliminary','assisted')):continue
        assignment=db.get(Assignment,attempt.assignment_id)
        version=db.get(TicketVersion,assignment.version_id)
        difficulty=attempt.snapshot.get('difficulty_level') or version.data.get('difficulty_stars') or {'Базовый':1,'Средний':3,'Сложный':5}.get(version.data.get('difficulty'),1)
        levels.setdefault(difficulty,[]).append(grade['score'])
    mastered=max((k for k,v in levels.items() if len(v)>=3 and statistics.mean(v)>=80),default=0)
    if os.getenv('DEMO_CLASSROOM')=='1' and p.data.get('demo_learning_v1') and len(scores)<3:
        level=max(1,p.data['demo_level']) if intro else 0
        mastered=max(0,p.data['demo_stars']-1)
    level=max(level,min(5,mastered)) if intro else 0
    times=[a['measured_seconds'] for a in confirmed if a.get('measured_seconds') is not None]
    return {'mastered_stars':mastered,'recommended_stars':min(5,mastered+1) if mastered else 1,'level':level,'intro_complete':intro,'score':avg,'completed':len(attempts),'confirmed':len(scores),
        'seconds':round(statistics.mean(times),1) if times else None,
        'text_errors':sum(len(a.get('text_checks',[])) for a in assessments),
        'drills':len(p.data.get('drills',[])),'mini_correct':sum(x['correct'] for x in p.data.get('drills',[]))}

def seed_catalog(db):
    if not db.scalar(select(ServiceDefinition.name).limit(1)):
        db.add_all([ServiceDefinition(name=name,config={'tags':tags,'questions':[],'rules':[]}) for name,tags in DEFAULT_SERVICES.items()])
    owner=db.scalar(select(User).where(User.role=='admin'))
    if owner and not db.scalar(select(MiniQuestion.id).limit(1)):
        for data in [
            {'prompt':'Введите название улицы точно: Добненская','kind':'text','answer':'Добненская','options':[],'level':1},
            {'prompt':'Выберите правильное написание','kind':'choice','answer':'Задымление','options':['Задымление','Задымленее'],'level':1},
            {'prompt':'Примите входящий звонок сочетанием Ctrl + Enter (клавиша тренажёра).','kind':'hotkey','answer':'Ctrl+Enter','options':[],'level':0},
            {'prompt':'Откройте подсказки по клавишам: нажмите Alt.','kind':'hotkey','answer':'Alt','options':[],'level':0}]:
            db.add(MiniQuestion(owner_id=owner.id,data=data))
    db.commit()
    from .catalog_expansion import seed_expansion
    seed_expansion(db)

@router.get('/profile')
def my_profile(u=Depends(m.current),db=Depends(m.getdb)):
    result=summary(db,u.id);db.commit();return result

@router.post('/intro')
def intro(data:dict,u=Depends(m.current),db=Depends(m.getdb)):
    p=profile(db,u.id); p.data={**p.data,'intro_complete':True};db.commit();return summary(db,u.id)

@router.get('/leaderboard')
def leaderboard(u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u); rows=[]
    for user in db.scalars(select(User).where(User.role=='student',User.active==True)):
        if m.visible(db,u,user.id):
            w=db.scalar(select(Workstation).where(Workstation.user_id==user.id).order_by(Workstation.last_seen.desc()))
            rows.append({'id':user.id,'name':user.name,'group_id':user.group_id,'station':w.number if w else '—',**summary(db,user.id)})
    for row in rows:
        group=[r['score'] for r in rows if r['group_id']==row['group_id'] and r['score'] is not None and r['confirmed']>=3]
        delta=row['score']-statistics.mean(group) if len(group)>=3 and row['score'] is not None and row['confirmed']>=3 else 0
        row['recommendation']='Можно предложить более сложные задания' if delta>=15 else 'Может понадобиться индивидуальная помощь' if delta<=-15 else ''
    db.commit();return sorted(rows,key=lambda r:(r['score'] is not None,r['score'] or 0,r['completed']),reverse=True)

@router.get('/services')
def services(u=Depends(m.current),db=Depends(m.getdb)):
    return [{'name':x.name,'active':x.active,**(x.config or {})} for x in db.scalars(select(ServiceDefinition).order_by(ServiceDefinition.name)) if x.active or u.role=='admin']

class ServiceRule(BaseModel):
    field:Literal['incident_type','traits','victims','description','object','district']
    operator:Literal['equals','contains']='contains'
    value:str=Field(min_length=1,max_length=200)

class ServiceIn(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    active:bool=True
    tags:list[str]=Field(default_factory=list,max_length=30)
    questions:list[str]=Field(default_factory=list,max_length=50)
    rules:list[ServiceRule]=Field(default_factory=list,max_length=30)

@router.post('/services')
def service_save(data:ServiceIn,u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u);row=db.get(ServiceDefinition,data.name)
    if not row:row=ServiceDefinition(name=data.name);db.add(row)
    if any(len(x)>500 for x in data.tags+data.questions):m.fail('Тег или вопрос слишком длинный')
    tags=list(dict.fromkeys(tag.strip() for tag in data.tags if tag.strip()))
    row.active=data.active
    changes=data.model_dump(exclude={'name','active'},exclude_unset=True)
    if 'tags' in changes:changes['tags']=tags
    row.config={**(row.config or {}),**changes}
    m.audit(db,u,'service_updated',data.name);db.commit();return {'ok':True}

def automatic_services(db,card):
    from .scenario_facts import semantic_services
    active=list(db.scalars(select(ServiceDefinition).where(ServiceDefinition.active==True)))
    result=semantic_services(active,card)
    for service in active:
        rules=(service.config or {}).get('rules',[])
        def matches(rule):
            values=card.get(rule['field'],'')
            values=values if isinstance(values,list) else [values]
            expected=rule['value'].strip().casefold()
            return any((expected==str(value).strip().casefold() if rule['operator']=='equals' else expected in str(value).casefold()) for value in values)
        if rules and all(matches(rule) for rule in rules):result.append(service.name)
    return list(dict.fromkeys(result))

@router.post('/services/suggest')
def suggest_services(card:dict,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    return {'services':automatic_services(db,card)}

class MiniIn(BaseModel):
    prompt:str=Field(min_length=3,max_length=1000)
    kind:Literal['text','choice','hotkey']='text'
    audio_text:str=Field(default='',max_length=2000)
    voice_gender:Literal['male','female']='female'
    answer:str=Field(min_length=1,max_length=300)
    options:list[str]=Field(default_factory=list,max_length=10)
    level:int=Field(default=1,ge=0,le=4)
    active:bool=True

def question_view(q,db,student=False):
    from .voice import VoiceJob
    data=dict(q.data)
    job=db.get(VoiceJob,data['voice_key']) if data.get('voice_key') else None
    data.update(audio_id=job.audio_id if job and job.status=='ready' else None,audio_status=job.status if job else '',audio_error=job.error if job else '')
    if student:
        for key in ('answer','audio_text','voice_key'):data.pop(key,None)
    return {'id':q.id,**data,'active':q.active}

@router.get('/questions')
def questions(u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u);return [question_view(q,db) for q in db.scalars(select(MiniQuestion))]

@router.post('/questions')
@router.put('/questions/{id}')
def save_question(data:MiniIn,id:int|None=None,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    if data.kind=='choice' and data.answer not in data.options:m.fail('Правильный ответ должен быть среди вариантов')
    row=db.get(MiniQuestion,id) if id else MiniQuestion(owner_id=u.id)
    if not row:m.fail('Вопрос недоступен',404)
    saved=data.model_dump(exclude={'active'})
    if data.audio_text.strip():
        from .voice import prepare
        prepared=prepare({'tasks':[{'contacts':[{'id':'mini','response':data.audio_text,'voice_gender':data.voice_gender}]}]},db,u.id)
        saved['voice_key']=prepared['tasks'][0]['contacts'][0]['voice_lines'][0]['voice_key']
    row.data=saved;row.active=data.active;db.add(row);db.commit();return question_view(row,db)

@router.post('/drill/{attempt_id}')
def drill(attempt_id:int,u=Depends(m.current),db=Depends(m.getdb)):
    a=db.get(Attempt,attempt_id)
    if not a or a.student_id!=u.id:m.fail('Задание недоступно',403)
    if a.status in ('completed','aborted') or a.snapshot.get('onboarding') or a.state.get('preview'):return None
    p=profile(db,u.id);data=copy.deepcopy(p.data); key=str(attempt_id)
    pending=data.get('pending_drill')
    if pending and pending['attempt']==attempt_id:
        return question_view(type('Pending',(),{'id':pending['id'],'data':pending['data'],'active':True})(),db,True)
    if pending:return None
    if key in data.get('drill_offered',[]):return None
    info=summary(db,u.id);data.setdefault('drill_offered',[]).append(key)
    p.data=data;db.commit()
    if info['level']>0 and not (os.getenv('DEMO_CLASSROOM')=='1' and p.data.get('demo_learning_v1')) and secrets.randbelow(4)!=0:return None
    group=db.get(Group,u.group_id) if u.group_id else None
    owners=list(db.scalars(select(User.id).where(User.role=='admin')))+([group.teacher_id] if group else [])
    qs=[q for q in db.scalars(select(MiniQuestion).where(MiniQuestion.active==True,MiniQuestion.owner_id.in_(owners))) if q.data.get('level',1)<=info['level']]
    qs=[q for q in qs if not q.data.get('voice_key') or question_view(q,db).get('audio_id')]
    if not qs:return None
    top=max(q.data.get('level',1) for q in qs)
    qs=[q for q in qs if q.data.get('level',1)==top]
    q=secrets.choice(qs);p.data={**p.data,'pending_drill':{'id':q.id,'attempt':attempt_id,'data':q.data}}
    a.state={**a.state,'mini_started':time.time()};a.revision+=1;db.commit()
    return question_view(q,db,True)

@router.post('/drill-answer')
def drill_answer(data:dict,u=Depends(m.current),db=Depends(m.getdb)):
    p=profile(db,u.id); pending=p.data.get('pending_drill')
    if not pending or pending['id']!=data.get('id'):m.fail('Вопрос уже закрыт')
    correct=str(data.get('answer','')).strip()==pending['data']['answer']
    a=db.get(Attempt,pending['attempt'])
    if a and a.state.get('mini_started'):
        elapsed=max(0,time.time()-a.state['mini_started'])
        state=copy.deepcopy(a.state);state.pop('mini_started');state['paused_seconds']=state.get('paused_seconds',0)+elapsed
        if state.get('brigade_next_at'):state['brigade_next_at']+=elapsed
        a.state=state;a.revision+=1
        from .db import ScheduledEvent
        for event in db.scalars(select(ScheduledEvent).where(ScheduledEvent.attempt_id==a.id,ScheduledEvent.done==False)):event.due+=elapsed
    history=p.data.get('drills',[])+[{'question':pending['id'],'correct':correct,'at':m.now()}]
    p.data={**p.data,'pending_drill':None,'drills':history[-500:]};db.commit()
    return {'correct':correct,'answer':pending['data']['answer']}

@router.get('/examples')
def approved(u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u);return [{'id':x.id,'text':x.text,'criterion':x.criterion,'active':x.active,'attempt_id':x.attempt_id} for x in db.scalars(select(ApprovedAnswer).order_by(ApprovedAnswer.id.desc()).limit(500)) if u.role=='admin' or x.teacher_id==u.id]

@router.delete('/examples/{id}')
def revoke(id:int,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u);x=db.get(ApprovedAnswer,id)
    if not x or u.role!='admin' and x.teacher_id!=u.id:m.fail('Образец недоступен',403)
    x.active=False;m.audit(db,u,'example_revoked',id);db.commit();return {'ok':True}
