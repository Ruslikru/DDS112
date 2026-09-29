"""Persistent DDS arrivals. Timers start at delivery, not when a card is opened."""
import copy
import time
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import Assignment, Attempt, AttemptEvent, Lesson, ScheduledEvent, TicketVersion, now
from .domain import EMPTY_CARD


def create_attempt(db, assignment, task, index, delivered_at=None, flow='sequential', preview=False):
    from .voice import ensure_ready,attach_audio
    if not preview:ensure_ready({"tasks":[task]},db)
    task=attach_audio(task,db)
    # Give simulated callers distinct numbers; preserve any authored number.
    if task.get('phone') in (None,'','+7 (000) 000-00-01'):
        import hashlib
        digits=str(int(hashlib.sha256(f"{assignment.id}:{index}".encode()).hexdigest()[:8],16)%10000000).zfill(7)
        task['phone']=f'+7 (900) {digits[:3]}-{digits[3:5]}-{digits[5:]}'
        if task.get('initial_card',{}).get('phone')=='+7 (000) 000-00-01':task['initial_card']['phone']=task['phone']
    stamp=delivered_at or now()
    dds=task['mode']=='dds'
    if dds:
        limits=[float(c['expected']) for c in task.get('criteria',[]) if c['kind']=='time']
        if limits: task['limit_seconds']=min(limits)
    from .caller import caller_gender
    state={'voice_gender':caller_gender(task),'asked':[],'dialogue':[],'services':{},'messages':[],'incoming_calls':[],
           'call':'none' if dds else 'ringing','registered':dds,'training':assignment.training,
           'lesson_id':assignment.lesson_id,'flow':flow,'paused_seconds':0,
           'brigade_pacing':'timed' if assignment.lesson_id and db.get(Lesson,assignment.lesson_id).config.get('delivery_mode') in ('sprint','dds_stream','cooperative') else 'sequential'}
    if task.get('onboarding'):state.update(teacher_assisted=True,guided=True)
    if not dds:
        from .classroom_models import Workstation
        station=db.scalar(select(Workstation).where(Workstation.user_id==assignment.student_id,Workstation.approved==True,Workstation.blocked==False).order_by(Workstation.last_seen.desc()))
        state.update(operator_id=assignment.student_id,arm_number=station.number if station else '')
    if dds:
        for service in dict.fromkeys([task['own_service']]+task.get('services',[])):
            state['services'][service]=[{'status':'Получена службой','at':stamp,'comment':''}]
    p=Attempt(assignment_id=assignment.id,student_id=assignment.student_id,task_index=index,
              delivery_key=f'{assignment.id}:{index}' if flow=='dds_stream' else None,
              snapshot=copy.deepcopy(task),status='active' if dds else 'ringing',started_at=stamp,
              card={**EMPTY_CARD,**task['initial_card'],'phone':task['initial_card'].get('phone') or task['phone']},state=state)
    db.add(p);db.flush()
    for event in task.get('service_events',[]):
        if not event.get('trigger_contact'):
            db.add(ScheduledEvent(attempt_id=p.id,due=datetime.fromisoformat(stamp).timestamp()+(2 if state['brigade_pacing']=='sequential' and event.get('kind')=='incoming_call' and not event.get('respect_delay') else float(event.get('after',event.get('after_seconds',10)))),data=event))
    db.add(AttemptEvent(attempt_id=p.id,kind='card_delivered',data={'flow':flow,'delivered_at':stamp}))
    return p


def deliver_lesson(db, lesson, timestamp=None):
    if lesson.status!='active': return
    if lesson.config.get('delivery_mode') in ('sequential','adaptive','sprint','cooperative'):
        from .classroom_flow import adaptive_delivery
        adaptive_delivery(db,lesson,time.time() if timestamp is None else timestamp)
        return
    if lesson.config.get('delivery_mode')!='dds_stream':return
    stamp=time.time() if timestamp is None else timestamp
    base=datetime.fromisoformat(lesson.started_at).timestamp()
    interval=lesson.config.get('arrival_interval_seconds',60)
    for a in db.scalars(select(Assignment).where(Assignment.lesson_id==lesson.id).order_by(Assignment.id).with_for_update()):
        existing=set(db.scalars(select(Attempt.task_index).where(Attempt.assignment_id==a.id)))
        tasks=db.get(TicketVersion,a.version_id).data['tasks']
        for index,task in enumerate(tasks):
            due=base+index*interval
            if due>stamp: break
            if index not in existing:
                try:
                    with db.begin_nested():
                        create_attempt(db,a,task,index,datetime.fromtimestamp(due,timezone.utc).isoformat(),'dds_stream')
                except IntegrityError:
                    if not db.scalar(select(Attempt.id).where(Attempt.delivery_key==f'{a.id}:{index}')): raise


def deliver_due(db):
    for lesson in db.scalars(select(Lesson).where(Lesson.status=='active').order_by(Lesson.id).with_for_update()):
        deliver_lesson(db,lesson)
    db.commit()
