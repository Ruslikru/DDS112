"""Teaching meetings and attendance. Assignment is never proof of attendance."""
import time
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import main as m
from .db import User, Group, Lesson, Assignment, now
from .training_session_models import TrainingSession, SessionMember, SessionMiniGroup, StudentPresence

router=APIRouter(prefix='/api')
PRESENCE_GRACE=20


class SessionInput(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    students:list[int]=Field(min_length=1,max_length=100)
    group_ids:list[int]=Field(default_factory=list,max_length=100)


class SessionPatch(BaseModel):
    title:str|None=Field(default=None,min_length=1,max_length=200)
    students:list[int]|None=Field(default=None,min_length=1,max_length=100)
    group_ids:list[int]|None=Field(default=None,max_length=100)


class MiniGroupInput(BaseModel):
    name:str=Field(min_length=1,max_length=160)
    students:list[int]=Field(default_factory=list,max_length=100)


def access(db,u,id,lock=False):
    m.staff(u)
    query=select(TrainingSession).where(TrainingSession.id==id)
    row=db.scalar(query.with_for_update() if lock else query)
    if not row or (u.role!='admin' and row.teacher_id!=u.id):m.fail('Учебная сессия недоступна',403)
    return row


def validate_recipients(db,u,session_id,students):
    session=access(db,u,session_id,True)
    if session.status=='ended':m.fail('Учебная сессия уже завершена')
    members=set(db.scalars(select(SessionMember.student_id).where(SessionMember.session_id==session.id)))
    if not set(students)<=members:m.fail('Добавьте выбранных студентов в состав учебной сессии')
    return session


def mark_member(member,stamp):
    # Locking the membership row serializes concurrent browser tabs/devices.
    previous=member.last_seen
    intervals=[dict(part) for part in (member.intervals or [])]
    if previous is None or stamp-previous>PRESENCE_GRACE or not intervals:
        intervals.append({'start':stamp,'end':stamp})
    else:
        intervals[-1]['end']=max(intervals[-1]['end'],stamp)
    member.intervals=intervals
    if member.first_seen is None:member.first_seen=stamp
    member.last_seen=max(previous or stamp,stamp)


def record_presence(db,user,stamp=None):
    """Called only after an authenticated heartbeat from an admitted workstation."""
    if not user or user.role!='student' or not user.active or user.deleted_at:return
    stamp=time.time() if stamp is None else stamp
    # An update of the workstation is flushed by the caller first (SQLite write lock).
    db.scalar(select(User).where(User.id==user.id).with_for_update())
    clock=db.get(StudentPresence,user.id)
    if clock:clock.last_seen=max(clock.last_seen,stamp)
    else:db.add(StudentPresence(student_id=user.id,last_seen=stamp))
    members=db.scalars(select(SessionMember).join(TrainingSession).where(
        SessionMember.student_id==user.id,TrainingSession.status=='active').with_for_update())
    for member in members:mark_member(member,stamp)


def delivery_allowed(db,lesson,student_id,stamp=None):
    """Legacy lessons retain their flow; new meetings wait for an authenticated arrival."""
    if not lesson.session_id:return True
    session=db.get(TrainingSession,lesson.session_id)
    if not session or session.status!='active':return False
    member=db.scalar(select(SessionMember).where(SessionMember.session_id==session.id,SessionMember.student_id==student_id))
    stamp=time.time() if stamp is None else stamp
    return bool(member and member.last_seen is not None and stamp-member.last_seen<=PRESENCE_GRACE)


def view(db,session,stamp=None):
    stamp=time.time() if stamp is None else stamp
    mini_groups=list(db.scalars(select(SessionMiniGroup).where(SessionMiniGroup.session_id==session.id).order_by(SessionMiniGroup.id)))
    membership={sid:group.id for group in mini_groups for sid in group.students}
    rows=[]
    for member in db.scalars(select(SessionMember).where(SessionMember.session_id==session.id).order_by(SessionMember.name)):
        presence=('present' if member.first_seen is not None else 'absent') if session.status=='ended' else (
            'online' if member.last_seen is not None and stamp-member.last_seen<=PRESENCE_GRACE else 'left' if member.first_seen is not None else 'waiting')
        # Prepared meetings show who is in class, but do not record attendance yet.
        if session.status=='prepared':
            clock=db.get(StudentPresence,member.student_id)
            presence='online' if clock and stamp-clock.last_seen<=PRESENCE_GRACE else 'waiting'
        rows.append({'id':member.student_id,'name':member.name,'group_id':member.group_id,'group_name':member.group_name,
            'presence':presence,'first_seen':datetime.fromtimestamp(member.first_seen,timezone.utc).isoformat() if member.first_seen is not None else None,
            'last_seen':datetime.fromtimestamp(member.last_seen,timezone.utc).isoformat() if member.last_seen is not None else None,
            'intervals':member.intervals,'mini_group_id':membership.get(member.student_id)})
    return {'id':session.id,'title':session.title,'status':session.status,'group_ids':session.group_ids,
        'created_at':session.created_at,'started_at':session.started_at,'ended_at':session.ended_at,
        'students':rows,'mini_groups':[{'id':g.id,'name':g.name,'students':g.students} for g in mini_groups],
        'expected_count':len(rows),'present_count':sum(row['first_seen'] is not None for row in rows)}


def set_members(db,u,session,students,group_ids=None):
    students=list(dict.fromkeys(students))
    current={row.student_id:row for row in db.scalars(select(SessionMember).where(SessionMember.session_id==session.id))}
    # Historical expected rosters are never silently overwritten after the session starts.
    removed=set(current)-set(students)
    if removed and session.status!='prepared':m.fail('После начала состав можно только дополнить')
    if removed:
        assigned=set(db.scalars(select(Assignment.student_id).where(Assignment.session_id==session.id)))
        if removed&assigned:m.fail('У этих студентов уже есть задания сессии')
    validated=[]
    for sid in students:
        student=db.get(User,sid)
        if not student or student.role!='student' or not student.active or student.deleted_at or not m.visible(db,u,sid):m.fail('Студент недоступен',403)
        validated.append(student)
    groups=set(group_ids if group_ids is not None else session.group_ids or [])
    groups.update(student.group_id for student in validated if student.group_id)
    for gid in groups:
        group=db.get(Group,gid)
        if not group or (u.role!='admin' and group.teacher_id!=u.id):m.fail('Группа недоступна',403)
    session.group_ids=sorted(groups)
    # Only draft roster rows may be removed; no attendance/history exists on them.
    for sid in removed:db.delete(current[sid])
    for group in db.scalars(select(SessionMiniGroup).where(SessionMiniGroup.session_id==session.id)):
        group.students=[sid for sid in group.students if sid in students]
    stamp=time.time()
    for student in validated:
        if student.id in current:continue
        group=db.get(Group,student.group_id) if student.group_id else None
        row=SessionMember(session_id=session.id,student_id=student.id,name=student.name,
            group_id=student.group_id,group_name=group.name if group else '',intervals=[])
        db.add(row)
        if session.status=='active':
            clock=db.get(StudentPresence,student.id)
            if clock and stamp-clock.last_seen<=PRESENCE_GRACE:mark_member(row,stamp)
    db.flush()


@router.get('/training-sessions')
def list_sessions(u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    rows=db.scalars(select(TrainingSession).order_by(TrainingSession.id.desc()))
    return [view(db,row) for row in rows if u.role=='admin' or row.teacher_id==u.id]


@router.post('/training-sessions')
def create_session(data:SessionInput,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    if not data.title.strip():m.fail('Укажите название сессии')
    row=TrainingSession(teacher_id=u.id,title=data.title.strip(),group_ids=[],status='prepared')
    db.add(row);db.flush()
    set_members(db,u,row,data.students,data.group_ids)
    m.audit(db,u,'training_session_created',row.id,{'students':data.students});db.commit()
    return view(db,row)


@router.get('/training-sessions/{id}')
def get_session(id:int,u=Depends(m.current),db=Depends(m.getdb)):
    return view(db,access(db,u,id))


@router.patch('/training-sessions/{id}')
def edit_session(id:int,data:SessionPatch,u=Depends(m.current),db=Depends(m.getdb)):
    row=access(db,u,id,True)
    if row.status=='ended':m.fail('Учебная сессия уже завершена')
    if data.title is not None:
        if not data.title.strip():m.fail('Укажите название сессии')
        row.title=data.title.strip()
    if data.students is not None or data.group_ids is not None:
        students=data.students if data.students is not None else list(db.scalars(select(SessionMember.student_id).where(SessionMember.session_id==id)))
        set_members(db,u,row,students,data.group_ids)
    m.audit(db,u,'training_session_changed',id);db.commit()
    return view(db,row)


@router.post('/training-sessions/{id}/start')
def start_session(id:int,u=Depends(m.current),db=Depends(m.getdb)):
    row=access(db,u,id,True)
    if row.status=='ended':m.fail('Завершённую сессию нельзя запустить повторно')
    if row.status=='prepared':
        row.status='active';row.started_at=now();stamp=time.time()
        for member in db.scalars(select(SessionMember).where(SessionMember.session_id==id).with_for_update()):
            clock=db.get(StudentPresence,member.student_id)
            if clock and stamp-clock.last_seen<=PRESENCE_GRACE:mark_member(member,stamp)
        db.flush()
        # Release all prepared modes together, preserving a common clock.
        from .dds_flow import deliver_lesson
        for lesson in db.scalars(select(Lesson).where(Lesson.session_id==id,Lesson.status=='prepared').with_for_update()):
            lesson.status='active';lesson.started_at=row.started_at
            for assignment in db.scalars(select(Assignment).where(Assignment.lesson_id==lesson.id)):assignment.released=True
            deliver_lesson(db,lesson,stamp)
        m.audit(db,u,'training_session_started',id);db.commit()
    return view(db,row)


@router.post('/training-sessions/{id}/stop')
def stop_session(id:int,u=Depends(m.current),db=Depends(m.getdb)):
    row=access(db,u,id,True)
    if row.status!='ended':
        from .extensions import finish_lesson
        row.status='ended';row.ended_at=now()
        for lesson in list(db.scalars(select(Lesson).where(Lesson.session_id==id,Lesson.status!='ended'))):
            finish_lesson(db,lesson,u)
        m.audit(db,u,'training_session_stopped',id);db.commit()
    return view(db,row)


def save_mini_group(db,u,session,data,group=None):
    if session.status=='ended':m.fail('Минигруппы завершённой сессии доступны только для просмотра')
    if not data.name.strip():m.fail('Укажите название минигруппы')
    ids=list(dict.fromkeys(data.students))
    members=set(db.scalars(select(SessionMember.student_id).where(SessionMember.session_id==session.id)))
    if not set(ids)<=members:m.fail('Минигруппа может включать только участников этой сессии')
    for other in db.scalars(select(SessionMiniGroup).where(SessionMiniGroup.session_id==session.id)):
        if group and other.id==group.id:continue
        if other.name.casefold()==data.name.strip().casefold():m.fail('Минигруппа с таким названием уже есть')
        if set(ids)&set(other.students):other.students=[sid for sid in other.students if sid not in ids]
    if group is None:
        group=SessionMiniGroup(session_id=session.id,name=data.name.strip(),students=ids);db.add(group)
    else:group.name=data.name.strip();group.students=ids
    db.flush();m.audit(db,u,'session_mini_group_saved',group.id,{'session_id':session.id});db.commit()
    return view(db,session)


@router.post('/training-sessions/{id}/mini-groups')
def create_mini_group(id:int,data:MiniGroupInput,u=Depends(m.current),db=Depends(m.getdb)):
    return save_mini_group(db,u,access(db,u,id,True),data)


@router.patch('/training-sessions/{id}/mini-groups/{group_id}')
def edit_mini_group(id:int,group_id:int,data:MiniGroupInput,u=Depends(m.current),db=Depends(m.getdb)):
    session=access(db,u,id,True);group=db.get(SessionMiniGroup,group_id)
    if not group or group.session_id!=id:m.fail('Минигруппа не найдена',404)
    return save_mini_group(db,u,session,data,group)


@router.get('/attendance')
def attendance(group_id:int|None=None,date_from:date|None=None,date_to:date|None=None,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    if date_from and date_to and date_from>date_to:m.fail('Начало периода позже окончания')
    if group_id:
        group=db.get(Group,group_id)
        if not group or (u.role!='admin' and group.teacher_id!=u.id):m.fail('Группа недоступна',403)
    def in_range(stamp):
        # UI dates are classroom local dates; storage timestamps remain UTC.
        from zoneinfo import ZoneInfo
        day=datetime.fromisoformat(stamp).astimezone(ZoneInfo('Europe/Moscow')).date()
        return (not date_from or day>=date_from) and (not date_to or day<=date_to)
    output=[]
    for row in db.scalars(select(TrainingSession).order_by(TrainingSession.id.desc())):
        if (u.role!='admin' and row.teacher_id!=u.id) or not in_range(row.started_at or row.created_at):continue
        if group_id and group_id not in row.group_ids:continue
        item=view(db,row)
        if group_id:item['students']=[student for student in item['students'] if student['group_id']==group_id]
        item['expected_count']=len(item['students']);item['present_count']=sum(s['first_seen'] is not None for s in item['students'])
        output.append(item)
    # Never infer past attendance from an assignment or a completed exercise.
    for lesson in db.scalars(select(Lesson).where(Lesson.session_id.is_(None)).order_by(Lesson.id.desc())):
        if (u.role!='admin' and lesson.teacher_id!=u.id) or not in_range(lesson.started_at or lesson.created_at):continue
        students=[]
        for sid in lesson.config.get('students',[]):
            student=db.get(User,sid)
            if not student or (group_id and student.group_id!=group_id):continue
            group=db.get(Group,student.group_id) if student.group_id else None
            students.append({'id':sid,'name':student.name,'group_id':student.group_id,'group_name':group.name if group else '',
                'presence':'unknown','first_seen':None,'last_seen':None,'intervals':[],'mini_group_id':None})
        if not students:continue
        output.append({'id':'legacy-'+str(lesson.id),'legacy':True,'title':lesson.title,'status':lesson.status,
            'created_at':lesson.created_at,'started_at':lesson.started_at,'ended_at':lesson.ended_at,
            'students':students,'mini_groups':[],'group_ids':[],'expected_count':len(students),'present_count':None})
    output.sort(key=lambda item:item['started_at'] or item['created_at'],reverse=True)
    return {'sessions':output}
