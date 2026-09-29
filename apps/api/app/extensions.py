"""Teaching sessions, portable reports and scenario reuse. No external services."""
import copy, csv, io, random
from typing import Literal
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from .main import current, getdb, staff, visible, fail, audit, start, results, save_ticket
from .db import *
from .schemas import TicketData
from .domain import assess, text_checks
from .dds_flow import deliver_lesson
from sqlalchemy import select

router=APIRouter(prefix='/api')

class LessonIn(BaseModel):
    title: str = Field(min_length=3,max_length=200)
    students: list[int] = Field(min_length=1,max_length=100)
    versions: list[int] = Field(default_factory=list,max_length=100)
    categories: list[str] = Field(default_factory=list,max_length=100)
    training: bool = True
    random_order: bool = True
    delivery_mode: Literal['sequential','dds_stream','adaptive','sprint','cooperative'] = 'sequential'
    duration_minutes: int = Field(default=30,ge=1,le=240)
    roles: dict[str,str] = Field(default_factory=dict)
    arrival_interval_seconds: int = Field(default=60,ge=5,le=3600)

def lesson_access(db,u,id,lock=False):
    query=select(Lesson).where(Lesson.id==id)
    lesson=db.scalar(query.with_for_update() if lock else query)
    if not lesson: fail('Занятие не найдено',404)
    if u.role=='student':
        if u.id not in lesson.config['students']: fail('Занятие недоступно',403)
    elif u.role!='admin' and lesson.teacher_id!=u.id: fail('Занятие другого преподавателя',403)
    return lesson

@router.get('/lessons')
def lessons(u=Depends(current),db=Depends(getdb)):
    output=[]
    for l in db.scalars(select(Lesson).order_by(Lesson.id.desc())):
        if u.role=='student' and u.id not in l.config['students']: continue
        if u.role=='teacher' and l.teacher_id!=u.id: continue
        members=[]
        for sid in l.config['students']:
            if u.role=='student' and sid!=u.id: continue
            assignments=db.scalars(select(Assignment).where(Assignment.lesson_id==l.id,Assignment.student_id==sid)).all()
            attempts=db.scalars(select(Attempt).where(Attempt.assignment_id.in_([a.id for a in assignments]))).all()
            members.append({'id':sid,'name':db.get(User,sid).name,'total':max(len(attempts),sum(len(db.get(TicketVersion,a.version_id).data['tasks']) for a in assignments)),
                'completed':len({(p.assignment_id,p.task_index) for p in attempts if p.status=='completed'}),
                'attempts':[{'id':p.id,'title':p.snapshot['title'],'status':p.status,'score':p.assessment.get('score') if p.assessment else None} for p in attempts]})
        output.append({'id':l.id,'title':l.title,'status':l.status,'started_at':l.started_at,'ended_at':l.ended_at,'members':members,
                       'categories':l.config.get('categories',[]),'training':l.config['training'],
                       'delivery_mode':l.config.get('delivery_mode','sequential'),'arrival_interval_seconds':l.config.get('arrival_interval_seconds',60)})
    return output

@router.post('/lessons')
def create_lesson(data:LessonIn,u=Depends(current),db=Depends(getdb)):
    staff(u)
    from .voice import readiness,ensure_ready
    for sid in set(data.students):
        s=db.get(User,sid)
        if not s or not s.active or s.role!='student' or not visible(db,u,sid): fail('Ученик недоступен',403)
    if data.delivery_mode in ('adaptive','sprint'):
        latest={}
        for version in db.scalars(select(TicketVersion).join(Ticket).where(TicketVersion.published==True,Ticket.archived==False).order_by(TicketVersion.id.desc())):
            if readiness(version.data,db)['ready']:latest.setdefault(version.ticket_id,version.id)
        data.versions=list(latest.values())
    tasks=[]
    for vid in dict.fromkeys(data.versions):
        v=db.get(TicketVersion,vid)
        if not v or not v.published or db.get(Ticket,v.ticket_id).archived: fail('Билет должен быть опубликован')
        ensure_ready(v.data,db)
        tasks += [{**copy.deepcopy(t),'difficulty_level':(v.data.get('difficulty_stars') or {'Базовый':1,'Средний':3,'Сложный':5}.get(v.data.get('difficulty'),1))} for t in v.data['tasks'] if not data.categories or t['category'] in data.categories]
    if data.delivery_mode in ('adaptive','sprint') and len(tasks)>100:tasks=random.SystemRandom().sample(tasks,100)
    if not tasks or len(tasks)>100: fail('Выберите от 1 до 100 заданий')
    if data.delivery_mode=='cooperative':
        roles={str(s):data.roles.get(str(s),'112') for s in data.students}
        from .classroom_models import ServiceDefinition
        available=set(db.scalars(select(ServiceDefinition.name).where(ServiceDefinition.active==True)))
        if any(role!='112' and role not in available for role in roles.values()):fail('Неизвестная служба ДДС')
        if not any(r=='112' for r in roles.values()) or not any(r!='112' for r in roles.values()):fail('Назначьте хотя бы одного оператора 112 и одного диспетчера ДДС')
        if not any(t['mode']=='112' for t in tasks):fail('Для совместного занятия нужен билет 112')
        data.roles=roles
    if data.delivery_mode=='dds_stream' and any(t['mode']!='dds' for t in tasks): fail('Для потока ДДС выберите только задания ДДС')
    l=Lesson(teacher_id=u.id,title=data.title,config=data.model_dump()); db.add(l); db.flush()
    # A private, immutable version per learner fixes the randomized order for resuming.
    for sid in dict.fromkeys(data.students):
        ordered=copy.deepcopy(tasks)
        if data.delivery_mode=='cooperative':
            ordered=[t for t in ordered if t['mode']=='112'] if data.roles.get(str(sid),'112')=='112' else []
        if data.random_order: random.SystemRandom().shuffle(ordered)
        t=Ticket(title=data.title,created_by=u.id,archived=True); db.add(t); db.flush()
        v=TicketVersion(ticket_id=t.id,number=1,published=True,data={'title':data.title,'description':'Снимок занятия','difficulty':'Средний','tasks':ordered}); db.add(v); db.flush()
        db.add(Assignment(lesson_id=l.id,version_id=v.id,student_id=sid,teacher_id=u.id,title=data.title,start_mode='teacher',released=False,training=data.training))
    audit(db,u,'lesson_created',l.id,{'students':data.students,'versions':data.versions}); db.commit()
    return {'id':l.id}

@router.post('/lessons/{id}/start')
def start_lesson(id:int,u=Depends(current),db=Depends(getdb)):
    staff(u); l=lesson_access(db,u,id,True)
    if l.status=='ended': fail('Завершённое занятие нельзя запустить повторно')
    if l.status=='prepared':
        l.status='active'; l.started_at=now()
        for a in db.scalars(select(Assignment).where(Assignment.lesson_id==id)): a.released=True
        deliver_lesson(db,l)
        audit(db,u,'lesson_started',id); db.commit()
    return {'ok':True}

@router.post('/lessons/{id}/stop')
def stop_lesson(id:int,u=Depends(current),db=Depends(getdb)):
    staff(u); l=lesson_access(db,u,id,True)
    if l.status!='ended':
        deliver_lesson(db,l)
        l.status='ended'; l.ended_at=now()
        ids=list(db.scalars(select(Assignment.id).where(Assignment.lesson_id==id)))
        for p in db.scalars(select(Attempt).where(Attempt.assignment_id.in_(ids),Attempt.status.notin_(['completed','aborted'])).with_for_update()):
            p.status='completed'; p.submitted_at=now(); p.state={**p.state,'stopped_by_teacher':True}; p.revision+=1; p.assessment=assess(p)
            db.add(AttemptEvent(attempt_id=p.id,actor_id=u.id,kind='teacher_stop',data={'lesson_id':id}))
        audit(db,u,'lesson_stopped',id); db.commit()
    return {'ok':True}

@router.post('/lessons/{id}/next')
def next_task(id:int,u=Depends(current),db=Depends(getdb)):
    l=lesson_access(db,u,id,True)
    if u.role!='student': fail('Задания выполняет ученик',403)
    if l.status!='active': fail('Занятие не активно')
    if l.config.get('delivery_mode')=='adaptive':
        deliver_lesson(db,l);db.commit()
        if l.status!='active':return {'finished':True}
        active=db.scalar(select(Attempt).join(Assignment).where(Assignment.lesson_id==id,Attempt.student_id==u.id,Attempt.status.notin_(['completed','aborted'])))
        if active:
            from .main import attempt_view
            return attempt_view(active,u)
    if l.config.get('delivery_mode') in ('dds_stream','adaptive','sprint','cooperative'):
        return {'queue':True,'lesson_id':l.id}
    for a in db.scalars(select(Assignment).where(Assignment.lesson_id==id,Assignment.student_id==u.id).order_by(Assignment.id)):
        attempts=db.scalars(select(Attempt).where(Attempt.assignment_id==a.id)).all()
        active=next((p for p in attempts if p.status not in ['completed','aborted']),None)
        if active: return start(a.id,{'task_index':active.task_index},u,db)
        completed={p.task_index for p in attempts if p.status in ['completed','aborted']}
        for index in range(len(db.get(TicketVersion,a.version_id).data['tasks'])):
            if index not in completed: return start(a.id,{'task_index':index},u,db)
    return {'finished':True}


@router.get('/lessons/{id}/queue')
def queue(id:int,student_id:int|None=None,u=Depends(current),db=Depends(getdb)):
    l=lesson_access(db,u,id,True)
    sid=u.id if u.role=='student' else student_id
    if sid not in l.config['students']: fail('Ученик недоступен',403)
    if l.config.get('delivery_mode') not in ('dds_stream','adaptive','sprint','cooperative'): fail('Это занятие проходит последовательно')
    cards=[];total=0
    for a in db.scalars(select(Assignment).where(Assignment.lesson_id==l.id,Assignment.student_id==sid)):
        total+=len(db.get(TicketVersion,a.version_id).data['tasks'])
        for p in db.scalars(select(Attempt).where(Attempt.assignment_id==a.id).order_by(Attempt.task_index)):
            elapsed=max(0,int((datetime.fromisoformat(p.submitted_at or now())-datetime.fromisoformat(p.started_at)).total_seconds()))
            ack=p.state.get('ack_seconds')
            hist=p.state.get('services',{}).get(p.snapshot['own_service'],[])
            cards.append({**journal_fields(p),'id':p.id,'title':p.snapshot['title'],'incident_type':p.card.get('incident_type',''),
                          'address':', '.join(str(p.card.get(k,'')) for k in ['street','house'] if p.card.get(k)),
                          'status':p.status,'service_status':hist[-1]['status'] if hist else '',
                          'delivered_at':p.started_at,'elapsed_seconds':elapsed,'ack_seconds':ack,
                          'norm_seconds':p.snapshot['limit_seconds'],
                          'overdue':(ack if ack is not None else elapsed)>p.snapshot['limit_seconds'],
                          'incoming_calls':len(p.state.get('incoming_calls',[]))})
    return {'lesson_id':l.id,'title':l.title,'status':l.status,'total':max(total,len(cards)),'delivered':len(cards),'cards':cards,
            'arrival_interval_seconds':l.config.get('arrival_interval_seconds',60)}

@router.get('/reports.csv')
def report(lesson_id:int|None=None,u=Depends(current),db=Depends(getdb)):
    lesson=lesson_access(db,u,lesson_id) if lesson_id else None
    rows=results(u,db)
    if lesson: rows=[p for p in rows if db.get(Assignment,p['assignment_id']).lesson_id==lesson_id]
    buf=io.StringIO(newline=''); writer=csv.writer(buf,delimiter=';')
    writer.writerow(['Попытка','Ученик','Задание','Режим','Начало','Общая длительность, сек','Измерение','Измеренное время, сек','Норматив, сек','Отклонение, сек','Балл','Ожидает проверки','Критерий','Фактически','Эталон','Зачтено'])
    def safe(value):
        value=str(value if value is not None else '')
        return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value
    for p in rows:
        for c in p['assessment']['criteria']:
            writer.writerow([safe(x) for x in [p['id'],p['student'],p['task']['title'],p['task']['mode'],p['started_at'],p['duration'],p['assessment'].get('measurement',''),p['assessment'].get('measured_seconds'),p['task']['limit_seconds'],p['assessment'].get('deviation_seconds'),p['assessment']['score'],p['assessment']['pending'],c['label'],c['actual'],c['expected'],c['passed']]])
    audit(db,u,'report_exported',lesson_id or '',{'attempts':len(rows)}); db.commit()
    return Response('\ufeff'+buf.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="training-report.csv"'})

@router.post('/text-check')
def check_text(data:dict,u=Depends(current)):
    text=str(data.get('text',''))
    if len(text)>50000: fail('Слишком длинный текст')
    return {'issues':text_checks(text),'method':'Локальные правила оформления. Полная грамматика и смысл проверяются преподавателем.'}

@router.get('/tickets/{id}/export')
def export_ticket(id:int,u=Depends(current),db=Depends(getdb)):
    staff(u); v=db.get(TicketVersion,id)
    if not v: fail('Билет не найден',404)
    import json
    return Response(json.dumps(v.data,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="ticket-{id}.json"'})

@router.post('/attempts/{id}/reuse')
def reuse(id:int,u=Depends(current),db=Depends(getdb)):
    staff(u); p=db.get(Attempt,id)
    if not p or not visible(db,u,p.student_id) or p.status!='completed' or p.snapshot['mode']!='112': fail('Нужна завершённая карточка 112 доступного ученика')
    task=copy.deepcopy(p.snapshot)
    task.update(mode='dds',title='Реагирование по карточке 112',origin='student',initial_card=copy.deepcopy(p.card),
                intro='Получена карточка 112. Подтвердите приём или обоснуйте отказ по принадлежности службы. Организуйте реагирование и ведите статусы.',
                services=list(p.state.get('services',{})),questions=[],service_events=[],contacts=[],
                criteria=[{'id':'decision','kind':'manual','label':'Обоснованное реагирование','weight':30,'expected':'Проверка преподавателя','critical':False,'skill':'Реагирование'}],
                source=f'Учебная карточка попытки #{id}. Требует проверки эталона и настройки бригады.')
    return save_ticket(TicketData(title=f'ДДС · карточка #{id}',tasks=[task]),None,u,db)

class MaterialIn(BaseModel):
    title: str=Field(min_length=3,max_length=200)
    body: str=Field(min_length=10,max_length=100000)
    group_id: int

@router.get('/materials')
def materials(u=Depends(current),db=Depends(getdb)):
    out=[]
    for m in db.scalars(select(Material).order_by(Material.id.desc())):
        group=db.get(Group,m.group_id)
        if u.role=='admin' or u.role=='teacher' and group.teacher_id==u.id or u.role=='student' and u.group_id==m.group_id:
            out.append({'id':m.id,'title':m.title,'body':m.body,'group':group.name,'created_at':m.created_at})
    return out

@router.post('/materials')
def add_material(data:MaterialIn,u=Depends(current),db=Depends(getdb)):
    staff(u); group=db.get(Group,data.group_id)
    if not group or u.role!='admin' and group.teacher_id!=u.id: fail('Группа недоступна',403)
    m=Material(**data.model_dump(),owner_id=u.id);db.add(m);db.flush();audit(db,u,'material_created',m.id);db.commit()
    return {'id':m.id}

@router.get('/registry')
def registry(u=Depends(current),db=Depends(getdb)):
    out=[]
    for p in db.scalars(select(Attempt).order_by(Attempt.id.desc())):
        if not visible(db,u,p.student_id): continue
        out.append({**journal_fields(p),'id':p.id,'student':db.get(User,p.student_id).name,'mode':p.snapshot['mode'],'started_at':p.started_at,'status':p.status,
          'incident_type':p.card.get('incident_type',''),'address':', '.join(str(p.card.get(k,'')) for k in ['city','street','house'] if p.card.get(k)),
          'description':p.card.get('description',''),'services':{k:v[-1]['status'] for k,v in p.state.get('services',{}).items() if v}})
    return out


def journal_fields(p):
    """Only facts already present in the received card; never the answer key."""
    return {'mode':p.snapshot['mode'],'started_at':p.started_at,
            'operator_id':p.state.get('operator_id',p.student_id if p.snapshot['mode']=='112' else ''),'arm_number':p.state.get('arm_number',''),
            'contact_phone':p.card.get('contact_phone',''),
            'caller':p.card.get('name',''),'phone':p.card.get('phone',''),
            'district':p.card.get('district',''),'area':p.card.get('area',''),
            'region':p.card.get('region',''),'address_note':p.card.get('address_note',''),
            'victims':p.card.get('victims','unknown'),'traits':p.card.get('traits',[]),
            'description':p.card.get('description',''),'own_service':p.snapshot.get('own_service',''),
            'services':{k:v[-1]['status'] for k,v in p.state.get('services',{}).items() if v},
            'service_history':p.state.get('services',{}),
            'service_status':next((v[-1]['status'] for k,v in p.state.get('services',{}).items() if v and k==p.snapshot.get('own_service')), ''),
            'incoming_calls':len(p.state.get('incoming_calls',[]))}
