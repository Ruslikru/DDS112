"""Authorized classroom presence, screen preview and peer signaling over the LAN."""
import hashlib
import os
import secrets
import time
import threading
from collections import defaultdict, deque
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import main as m
from .db import User, LoginSession, Attempt
from .classroom_models import Workstation, ClassroomLink

router=APIRouter(prefix='/api/classroom')
live={}
signals=defaultdict(lambda:deque(maxlen=150))
lock=threading.RLock()

@router.get('/server-setup')
def server_setup():
    from .server_identity import identity,is_ready
    return {**identity(),'ready':is_ready()}

@router.get('/connection')
def connection(request:Request,u=Depends(m.current)):
    m.staff(u)
    import os,socket
    port=8765 if os.getenv('CLASSROOM_SERVER')=='1' else request.url.port or 8000
    try:addresses={info[4][0] for info in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET)}
    except OSError:addresses=set()
    urls=[f'http://{ip}:{port}' for ip in sorted(addresses) if not ip.startswith(('127.','169.254.'))]
    from .server_identity import identity,is_ready
    return {**identity(),'ready':is_ready(),'urls':urls}

def station(request,db,required=True):
    token=request.headers.get('x-workstation','')
    w=db.scalar(select(Workstation).where(Workstation.secret_hash==hashlib.sha256(token.encode()).hexdigest())) if token else None
    demo=os.getenv('DEMO_CLASSROOM')=='1'
    if required and (not w or w.blocked or (demo and w.id!=os.getenv('DEMO_SERVER_STATION_ID') and not w.number.isdigit()) or (not w.approved and not demo)):m.fail('Рабочее место ожидает назначения номера администратором',403)
    return w


@router.post('/heartbeat')
def heartbeat(request:Request,db=Depends(m.getdb)):
    w=station(request,db,False)
    if not w or w.blocked:m.fail('Рабочее место не найдено',403)
    session_token=request.cookies.get('session','')
    session=db.get(LoginSession,hashlib.sha256(session_token.encode()).hexdigest()) if session_token else None
    w.user_id=session.user_id if session and session.expires>time.time() else None
    w.last_seen=time.time()
    db.commit()
    return {'ok':True}

class Register(BaseModel):
    number:str=Field(min_length=1,max_length=40)

@router.post('/register')
def register(data:Register,db=Depends(m.getdb)):
    if db.scalar(select(Workstation).where(Workstation.number==data.number)):m.fail('Номер рабочего места уже занят. Используйте сохранённую настройку или другой номер.')
    if len(db.scalars(select(Workstation).limit(251)).all())>=250:m.fail('Лимит рабочих мест достигнут')
    secret=secrets.token_urlsafe(32);w=Workstation(id=secrets.token_hex(16),number=data.number,secret_hash=hashlib.sha256(secret.encode()).hexdigest(),approved=os.getenv('DEMO_CLASSROOM')=='1')
    db.add(w);db.commit();return {'id':w.id,'token':secret,'number':w.number}

@router.get('/admission')
def admission(request:Request,db=Depends(m.getdb)):
    w=station(request,db,False)
    configured=bool(w and (os.getenv('DEMO_CLASSROOM')!='1' or w.id==os.getenv('DEMO_SERVER_STATION_ID') or w.number.isdigit()))
    return {'registered':bool(w),'approved':bool(w and configured and (w.approved or os.getenv('DEMO_CLASSROOM')=='1') and not w.blocked),'number':w.number if w else '', 'id':w.id if w else '', 'configured':configured}

@router.post('/demo-pending')
def demo_pending(request:Request,db=Depends(m.getdb)):
    if os.getenv('DEMO_CLASSROOM')!='1':m.fail('Доступно только в демонстрации',403)
    w=station(request,db,False)
    if not w or w.id==os.getenv('DEMO_SERVER_STATION_ID'):m.fail('Недоступно',403)
    w.number='Демо слот '+w.id[:12];w.user_id=None;w.approved=False
    from . import management
    with management.lock:management.state.pop(w.id,None)
    db.commit()
    return {'number':w.number}

class DemoNumber(BaseModel):
    number:str=Field(pattern=r'^[1-9][0-9]{0,2}$')

@router.post('/demo-number')
def assign_demo_number(data:DemoNumber,request:Request,u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u)
    if os.getenv('DEMO_CLASSROOM')!='1':m.fail('Доступно только при запуске на одном ПК',403)
    w=station(request,db,False)
    if not w:m.fail('Рабочее место не найдено',404)
    other=db.scalar(select(Workstation).where(Workstation.number==data.number,Workstation.id!=w.id))
    if other:m.fail('Этот номер уже занят другим рабочим местом')
    w.number=data.number;w.approved=True;db.commit()
    m.audit(db,u,'demo_station_number',w.id,{'number':data.number});db.commit()
    return {'number':w.number,'id':w.id}

@router.get('/stations')
def stations(u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u);out=[]
    server_id=os.getenv('CLASSROOM_SERVER_STATION_ID') or os.getenv('DEMO_SERVER_STATION_ID')
    with lock:
        for w in db.scalars(select(Workstation).order_by(Workstation.number)):
            if u.role!='admin' and (not w.user_id or not m.visible(db,u,w.user_id)):continue
            if os.getenv('DEMO_CLASSROOM')=='1' and w.id!=server_id and not w.number.isdigit():continue
            user=db.get(User,w.user_id) if w.user_id else None
            state=live.get(w.user_id,{}) if w.user_id else {}
            online=time.time()-w.last_seen<12
            out.append({'id':w.id,'number':w.number,'mode':'server' if w.id==server_id else 'client','approved':w.approved,'blocked':w.blocked,'user_id':w.user_id,
                'role':user.role if user else None,'name':user.name if user else 'Не вошёл','online':online,'page':state.get('page',''),
                'frame':state.get('frame','') if online and state.get('sharing') else '', 'sharing':bool(state.get('sharing'))})
    return out

@router.patch('/stations/{id}')
def change_station(id:str,data:dict,u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u);w=db.get(Workstation,id)
    if not w:m.fail('ПК не найден',404)
    if 'approved' in data:w.approved=bool(data['approved'])
    if 'blocked' in data:w.blocked=bool(data['blocked'])
    if w.blocked and w.user_id:
        for link in db.scalars(select(ClassroomLink).where(ClassroomLink.student_id==w.user_id,ClassroomLink.active==True)):link.active=False
        with lock:live.pop(w.user_id,None)
    m.audit(db,u,'workstation_access',id,{'approved':w.approved,'blocked':w.blocked});db.commit();return {'ok':True}

class Presence(BaseModel):
    page:str=Field(default='',max_length=120)
    sharing:bool=False
    frame:str=Field(default='',max_length=2200000)

@router.post('/presence')
def presence(data:Presence,request:Request,u=Depends(m.current),db=Depends(m.getdb)):
    w=station(request,db)
    w.user_id=u.id;w.last_seen=time.time()
    if data.frame and not data.frame.startswith('data:image/jpeg;base64,'):m.fail('Ожидается JPEG')
    with lock:live[u.id]={'page':data.page,'sharing':data.sharing,'frame':data.frame if data.sharing else '', 'at':time.time()}
    if not data.sharing:
        for link in db.scalars(select(ClassroomLink).where(ClassroomLink.student_id==u.id,ClassroomLink.mode=='help',ClassroomLink.active==True)):link.active=False
    db.commit()
    links=list(db.scalars(select(ClassroomLink).where(ClassroomLink.active==True)))
    output=[]
    with lock:
        for link in links:
            if u.id not in (link.teacher_id,link.student_id):continue
            teacher=live.get(link.teacher_id,{})
            if any(time.time()-live.get(sid,{}).get('at',0)>12 for sid in (link.teacher_id,link.student_id)):
                link.active=False
                signals.pop((link.id,link.teacher_id),None);signals.pop((link.id,link.student_id),None)
                continue
            output.append({'id':link.id,'mode':link.mode,'teacher_id':link.teacher_id,'student_id':link.student_id,
                'teacher':db.get(User,link.teacher_id).name,'frame':teacher.get('frame','') if link.mode=='demo' and time.time()-teacher.get('at',0)<12 else ''})
    db.commit()
    return output

class LinkIn(BaseModel):
    students:list[int]=Field(min_length=1,max_length=100)
    mode:str=Field(pattern='^(demo|help|audio)$')

@router.post('/links')
def connect(data:LinkIn,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    if data.mode=='help' and len(data.students)!=1:m.fail('Выберите одного ученика')
    for sid in data.students:
        s=db.get(User,sid)
        if not s or s.role!='student' or not m.visible(db,u,sid):m.fail('Ученик недоступен',403)
        with lock:
            state=live.get(sid,{})
            if time.time()-state.get('at',0)>12:m.fail('Ученик не подключён')
            if data.mode=='help' and not state.get('sharing'):m.fail('Ученик должен подключить показ экрана')
    for sid in set(data.students):
        for old in db.scalars(select(ClassroomLink).where(ClassroomLink.student_id==sid,ClassroomLink.active==True)):old.active=False
        db.add(ClassroomLink(id=secrets.token_hex(16),teacher_id=u.id,student_id=sid,mode=data.mode))
    m.audit(db,u,'classroom_connect',detail=data.model_dump());db.commit();return {'ok':True}

def allowed_link(db,u,id):
    link=db.get(ClassroomLink,id)
    if not link or not link.active or u.id not in (link.teacher_id,link.student_id):m.fail('Соединение закрыто',403)
    if not m.visible(db,db.get(User,link.teacher_id),link.student_id):m.fail('Группа недоступна',403)
    for sid in (link.teacher_id,link.student_id):
        with lock:
            state=live.get(sid,{})
            if time.time()-state.get('at',0)>12:m.fail('Участник отключён',409)
    return link

@router.delete('/links/{id}')
def disconnect(id:str,u=Depends(m.current),db=Depends(m.getdb)):
    link=db.get(ClassroomLink,id)
    if not link or u.id not in (link.teacher_id,link.student_id):m.fail('Соединение недоступно',403)
    link.active=False;m.audit(db,u,'classroom_disconnect',id);db.commit();return {'ok':True}

class Signal(BaseModel):
    kind:str=Field(pattern='^(offer|answer|ice|pointer|click|key|text|scroll)$')
    payload:dict

@router.post('/links/{id}/signal')
def send_signal(id:str,data:Signal,u=Depends(m.current),db=Depends(m.getdb)):
    link=allowed_link(db,u,id)
    if len(str(data.payload))>50000:m.fail('Слишком большой пакет')
    if data.kind in ('pointer','click','key','text','scroll'):
        if u.id!=link.teacher_id or data.kind!='pointer' and link.mode!='help':m.fail('Управление недоступно',403)
        if data.kind!='pointer':
            with lock:page=live.get(link.student_id,{}).get('page','')
            if page.startswith('/attempts/') and page.split('/')[-1].isdigit():
                attempt=db.get(Attempt,int(page.split('/')[-1]))
                if attempt and attempt.student_id==link.student_id and attempt.status not in ('completed','aborted'):
                    attempt.state={**attempt.state,'teacher_assisted':True};attempt.revision+=1
            m.audit(db,u,'classroom_help',id,{'action':data.kind});db.commit()
    target=link.student_id if u.id==link.teacher_id else link.teacher_id
    with lock:signals[(id,target)].append({'kind':data.kind,'payload':data.payload})
    return {'ok':True}

@router.get('/links/{id}/signals')
def receive_signals(id:str,u=Depends(m.current),db=Depends(m.getdb)):
    allowed_link(db,u,id)
    with lock:
        result=list(signals[(id,u.id)]);signals[(id,u.id)].clear()
    return result
