"""Adaptive arrivals and live handoff between students; no generated claims about real routing."""
import copy
import time
import random
from datetime import datetime
from types import SimpleNamespace
from sqlalchemy import select
from .db import Assignment, Attempt, Ticket, TicketVersion, Lesson, AttemptEvent, now
from .dds_flow import create_attempt
from .learning import summary
from .dds_scenarios import generated_dds

QUEUE_MODES=('dds_stream','adaptive','sprint','cooperative')

def adaptive_delivery(db,lesson,stamp):
    mode=lesson.config.get('delivery_mode')
    end=datetime.fromisoformat(lesson.started_at).timestamp()+lesson.config.get('duration_minutes',30)*60
    if stamp>=end:
        from .domain import assess
        lesson.status='ended';lesson.ended_at=now()
        ids=list(db.scalars(select(Assignment.id).where(Assignment.lesson_id==lesson.id)))
        for p in db.scalars(select(Attempt).where(Attempt.assignment_id.in_(ids),Attempt.status.notin_(['completed','aborted']))):
            p.status='completed';p.submitted_at=now();p.state={**p.state,'stopped_by_teacher':True};p.assessment=assess(p);p.revision+=1
        return
    if mode not in ('adaptive','sprint','cooperative'):return
    for a in db.scalars(select(Assignment).where(Assignment.lesson_id==lesson.id).with_for_update()):
        if mode=='cooperative' and lesson.config.get('roles',{}).get(str(a.student_id),'112')!='112':continue
        info=summary(db,a.student_id)
        if not info['intro_complete']:continue
        tasks=db.get(TicketVersion,a.version_id).data['tasks']
        ps=list(db.scalars(select(Attempt).where(Attempt.assignment_id==a.id)))
        active=sum(p.status not in ('completed','aborted') for p in ps)
        cap=1 if mode=='adaptive' or info['level']<=1 else min(3,info['level'])
        interval=0 if mode=='adaptive' else max(15,90-info['level']*15)
        last=max((datetime.fromisoformat(p.started_at).timestamp() for p in ps),default=0)
        if active>=cap or stamp-last<interval or not tasks:continue
        done={p.task_index for p in ps}
        remaining=[i for i in range(len(tasks)) if i not in done]
        target=info.get('recommended_stars',1)
        pool=remaining or list(range(len(tasks)))
        suitable=[i for i in pool if tasks[i].get('difficulty_level',1)<=target]
        if not suitable:suitable=[i for i in range(len(tasks)) if tasks[i].get('difficulty_level',1)<=target]
        index=random.choice(suitable) if suitable else min(pool,key=lambda i:tasks[i].get('difficulty_level',1),default=None)
        if index is not None:
            delivery_index=index if index in remaining else max(done,default=-1)+1
            create_attempt(db,a,tasks[index],delivery_index,flow='dds_stream')

def relay_card(db,source,selected):
    assignment=db.get(Assignment,source.assignment_id)
    lesson=db.get(Lesson,assignment.lesson_id) if assignment.lesson_id else None
    if not lesson or lesson.config.get('delivery_mode')!='cooperative':return set()
    routed=set()
    for sid,service in lesson.config.get('roles',{}).items():
        if service=='112' or service not in selected:continue
        key=f'relay:{source.id}:{sid}:{service}'
        if db.scalar(select(Attempt.id).where(Attempt.delivery_key==key)):
            routed.add(service);continue
        target=db.scalar(select(Assignment).where(Assignment.lesson_id==lesson.id,Assignment.student_id==int(sid)))
        if not target:continue
        card=copy.deepcopy(source.card)
        config=SimpleNamespace(own_service=service,services=selected,district=card.get('area',''),incident_type=card.get('incident_type',''),affiliation='Учебная служба')
        facts={'title':source.snapshot['title'],'city':card.get('city',''),'street':card.get('street',''),
               'house':card.get('house',''),'caller_name':card.get('name') or 'Имя не указано',
               'description':card.get('description',''),'victims':str(card.get('victims','unknown')),'victims_state':card.get('victims','unknown')}
        task=generated_dds(config,facts,{'model':'Совместное занятие'}).model_dump()['tasks'][0]
        task.update(initial_card=card,source=f'Карточка ученика 112 #{source.id}',origin='student')
        task['initial_card']['phone']=card.get('phone','')
        p=create_attempt(db,target,task,source.id,flow='cooperative')
        p.delivery_key=key;p.state={**p.state,'source_attempt_id':source.id}
        routed.add(service)
    return routed

def relay_status(db,target):
    source_id=target.state.get('source_attempt_id')
    if not source_id:return
    source=db.scalar(select(Attempt).where(Attempt.id==source_id).with_for_update())
    if not source:return
    state=copy.deepcopy(source.state);service=target.snapshot['own_service']
    state.setdefault('services',{})[service]=copy.deepcopy(target.state['services'][service])
    source.state=state;source.revision+=1
    db.add(AttemptEvent(attempt_id=source.id,kind='student_dds_status',actor_id=target.student_id,data={'source':target.id,'service':service}))
