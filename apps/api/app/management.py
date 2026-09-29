"""Administrator-only device actions; native agents authenticate with station secrets."""
import hashlib
import json
import secrets
import threading
import time
from typing import Literal
from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import main as m
from .db import DATA
from .classroom import station
from .classroom_models import Workstation
from .management_models import DeviceCommand, UpdatePackage, ManagementSetting
from . import backups
from device_runtime.updates import validate_package

router=APIRouter(prefix='/api/management')
state={}
remote={}
previews={}
lock=threading.RLock()

def server_id():return __import__('os').getenv('CLASSROOM_SERVER_STATION_ID') or __import__('os').getenv('DEMO_SERVER_STATION_ID')

def station_label(db,wid):
    if wid==server_id():return 'Сервер'
    row=db.get(Workstation,wid)
    return 'Рабочее место №'+row.number if row and row.number.isdigit() else 'Рабочее место · '+(row.number if row else 'удалено')

def device(db,wid):
    w=db.get(Workstation,wid)
    if not w or w.blocked:m.fail('Рабочее место исключено или не найдено',404)
    return w

def can_manage(db,u,w):
    if u.role=='admin':return True
    if u.role!='teacher':return False
    person=db.get(m.User,w.user_id) if w.user_id else None
    return not person or person.id==u.id or person.role=='student' and m.visible(db,u,person.id)

def allowed_device(db,u,wid):
    m.staff(u);w=device(db,wid)
    if not can_manage(db,u,w):m.fail('Нет доступа к этому рабочему месту',403)
    return w

def enqueue(db,wid,kind,payload=None):
    if time.time()-state.get(wid,{}).get('seen',0)>15:m.fail('Приложение недоступно. Откройте новую версию тренажёра на этом ПК.',409)
    row=DeviceCommand(id=secrets.token_hex(16),station_id=wid,kind=kind,payload=payload or {},created=time.time())
    db.add(row);return row

class AgentReport(BaseModel):
    metrics:dict=Field(default_factory=dict)
    frame:str=Field(default='',max_length=2200000)
    results:list[dict]=Field(default_factory=list,max_length=100)

@router.post('/agent/poll')
def agent_poll(data:AgentReport,request:Request,db=Depends(m.getdb)):
    w=station(request,db,False)
    if not w:m.fail('Рабочее место не найдено',403)
    if w.blocked:return {'revoked':True,'commands':[],'desktop':False,'inputs':[]}
    if len(json.dumps(data.metrics))>50000:m.fail('Слишком большой отчёт')
    if data.frame and not data.frame.startswith('data:image/jpeg;base64,'):m.fail('Ожидается JPEG')
    with lock:
        state[w.id]={'seen':time.time(),'metrics':data.metrics,'frame':data.frame}
        session=remote.get(w.id)
        owner=db.get(m.User,session['owner']) if session else None
        if session and (not owner or not can_manage(db,owner,w)):
            remote.pop(w.id,None);session=None
        watching=bool(session and session['until']>time.time())
        inputs=session['inputs'][:] if watching else []
        watching=watching or previews.get(w.id,0)>time.time()
        if session:session['inputs'].clear()
    w.last_seen=time.time()
    for result in data.results:
        row=db.get(DeviceCommand,str(result.get('id','')))
        if row and row.station_id==w.id and row.status in ('queued','running','prepared'):
            row.status=('prepared' if row.kind=='update' and result.get('status')=='prepared' else 'done') if result.get('ok') else 'failed';row.result=str(result.get('message',''))[:1000]
    commands=[]
    for row in db.scalars(select(DeviceCommand).where(DeviceCommand.station_id==w.id,DeviceCommand.status.in_(['queued','running'])).order_by(DeviceCommand.created)):
        if time.time()-row.created>600:row.status='failed';row.result='Время ожидания истекло';continue
        row.status='running';commands.append({'id':row.id,'kind':row.kind,'payload':row.payload})
    db.commit()
    return {'revoked':False,'commands':commands,'desktop':watching,'control':bool(session and session['until']>time.time()),'inputs':inputs}

@router.get('/devices')
def devices(request:Request,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    own=station(request,db,False)
    rows=[]
    with lock:
        for w in db.scalars(select(Workstation).where(Workstation.blocked==False)):
            if not can_manage(db,u,w):continue
            if __import__('os').getenv('DEMO_CLASSROOM')=='1' and w.id!=server_id() and not w.number.isdigit():continue
            info=state.get(w.id,{})
            agent_online=time.time()-info.get('seen',0)<15
            if time.time()-w.last_seen>=15 and not agent_online:continue
            user=db.get(m.User,w.user_id) if w.user_id else None
            rows.append({'id':w.id,'number':w.number,'mode':'server' if w.id==server_id() else 'client',
                'current':bool(own and own.id==w.id),'name':user.name if user else 'Не вошёл','user_id':w.user_id,'online':True,'agent_online':agent_online,
                'metrics':info.get('metrics',{}) if agent_online and u.role=='admin' else {},'seen':info.get('seen')})
    return sorted(rows,key=lambda r:(r['mode']!='server',r['number']))

@router.get('/previews')
def preview_frames(u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    frames={}
    with lock:
        for w in db.scalars(select(Workstation).where(Workstation.blocked==False)):
            if not can_manage(db,u,w):continue
            if __import__('os').getenv('DEMO_CLASSROOM')=='1' and w.id!=server_id() and not w.number.isdigit():continue
            info=state.get(w.id,{})
            if time.time()-info.get('seen',0)>=15:continue
            previews[w.id]=time.time()+8
            frames[w.id]=info.get('frame','')
        for wid in list(previews):
            if previews[wid]<time.time():previews.pop(wid,None)
    return frames

class Action(BaseModel):
    kind:Literal['logout','close','remove']

@router.post('/devices/{wid}/action')
def action(wid:str,data:Action,u=Depends(m.current),db=Depends(m.getdb)):
    w=allowed_device(db,u,wid)
    if u.role!='admin' and data.kind!='logout':m.fail('Команда доступна только администратору',403)
    if data.kind=='remove' and wid==server_id():m.fail('Учебный сервер нельзя исключить из собственного контура')
    row=enqueue(db,wid,data.kind)
    if data.kind=='remove':
        w.blocked=True;w.approved=False;w.user_id=None
        row.status='done';row.result='Доступ устройства к контуру отозван'
    m.audit(db,u,'device_'+data.kind,wid);db.commit();return {'id':row.id}

class AIConfig(BaseModel):
    mode:Literal['cpu','gpu','server']
    device:str=Field(default='',max_length=100)

@router.post('/devices/{wid}/ai')
def ai_config(wid:str,data:AIConfig,u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u);device(db,wid)
    if wid==server_id() and data.mode=='server':m.fail('На сервере выберите CPU или GPU')
    gpus=state.get(wid,{}).get('metrics',{}).get('ai',{}).get('gpus',[])
    if data.mode=='gpu' and data.device not in [gpu['id'] for gpu in gpus]:m.fail('Выбранная видеокарта недоступна')
    row=enqueue(db,wid,'ai',data.model_dump())
    if wid!=server_id():
        from local_ai.engine import engine
        config=engine.config();ids=[x for x in config['worker_ids'] if x!=wid]
        if data.mode!='server':ids.append(wid)
        try:engine.set_settings(execution='workstations' if ids else 'server',worker_ids=ids)
        except Exception as e:m.fail(str(e),409)
    m.audit(db,u,'device_ai_settings',wid,data.model_dump());db.commit();return {'id':row.id}

@router.post('/devices/{wid}/desktop')
def desktop_start(wid:str,request:Request,u=Depends(m.current),db=Depends(m.getdb)):
    allowed_device(db,u,wid)
    own=station(request,db,False)
    if own and own.id==wid:m.fail("Это текущее рабочее место",409)
    if time.time()-state.get(wid,{}).get('seen',0)>15:m.fail('Настольное приложение недоступно',409)
    with lock:
        previous=remote.get(wid)
        if previous and previous['until']>time.time() and previous['owner']!=u.id:m.fail('Рабочий стол уже открыт другим администратором',409)
        token=secrets.token_hex(24);remote[wid]={'token':token,'owner':u.id,'until':time.time()+15,'inputs':[]}
    m.audit(db,u,'remote_desktop_open',wid);db.commit();return {'token':token}

def desktop_session(wid,token,u):
    session=remote.get(wid)
    if not session or session['token']!=token or session['owner']!=u.id or session['until']<time.time():m.fail('Сеанс управления завершён',403)
    return session

@router.get('/devices/{wid}/desktop/{token}')
def desktop_frame(wid:str,token:str,u=Depends(m.current),db=Depends(m.getdb)):
    allowed_device(db,u,wid)
    with lock:
        session=desktop_session(wid,token,u);session['until']=time.time()+15
        info=state.get(wid,{})
        return {'frame':info.get('frame',''),'online':time.time()-info.get('seen',0)<15,'metrics':info.get('metrics',{})}

class DesktopInput(BaseModel):
    kind:Literal['click','doubleclick','rightclick','scroll','key','text']
    x:float=Field(default=0,ge=0,le=1)
    y:float=Field(default=0,ge=0,le=1)
    delta:int=Field(default=0,ge=-600,le=600)
    key:str=Field(default='',max_length=40)
    text:str=Field(default='',max_length=1000)

@router.post('/devices/{wid}/desktop/{token}/input')
def desktop_input(wid:str,token:str,data:DesktopInput,u=Depends(m.current),db=Depends(m.getdb)):
    allowed_device(db,u,wid)
    with lock:
        session=desktop_session(wid,token,u)
        if len(session['inputs'])>=50:m.fail('Подождите выполнения предыдущего ввода',429)
        session['inputs'].append({**data.model_dump(),'at':time.time()})
    return {'ok':True}

@router.delete('/devices/{wid}/desktop/{token}')
def desktop_stop(wid:str,token:str,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    with lock:
        desktop_session(wid,token,u);remote.pop(wid,None)
        if wid in state:state[wid]['frame']=''
    m.audit(db,u,'remote_desktop_close',wid);db.commit();return {'ok':True}

class BackupIn(BaseModel):
    enabled:bool=True
    interval_hours:int=Field(default=24,ge=1,le=720)
    folder:str=Field(min_length=1,max_length=1000)

@router.get('/backup')
def backup_settings(u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u);return {**backups.settings(db),'running':backups.lock.locked()}

@router.post('/backup')
def backup_save(data:BackupIn,u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u)
    try:backups.validate_folder(data.folder)
    except ValueError as e:m.fail(str(e))
    row=db.get(ManagementSetting,'backup')
    if not row:row=ManagementSetting(key='backup',value={});db.add(row)
    row.value={**row.value,**data.model_dump()};m.audit(db,u,'backup_settings');db.commit();return backups.settings(db)

@router.post('/backup/run')
async def backup_run(u=Depends(m.current)):
    m.admin(u)
    import asyncio
    if backups.lock.locked():m.fail('Копирование уже выполняется',409)
    return await asyncio.to_thread(backups.perform)

@router.get('/commands')
def commands(u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u)
    for row in db.scalars(select(DeviceCommand).where(DeviceCommand.status.in_(['queued','running','prepared']),DeviceCommand.created<time.time()-600)):
        row.status='failed';row.result='Устройство не подтвердило выполнение за 10 минут'
    db.commit()
    return [{'id':r.id,'station_id':r.station_id,'station_name':station_label(db,r.station_id),'kind':r.kind,'status':r.status,'result':r.result,'created':r.created} for r in db.scalars(select(DeviceCommand).order_by(DeviceCommand.created.desc()).limit(100))]

@router.get('/packages')
def packages(u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u);return [{'id':p.id,'version':p.version,'size':p.size,'created':p.created} for p in db.scalars(select(UpdatePackage).order_by(UpdatePackage.created.desc()))]

@router.post('/packages')
async def upload_package(file:UploadFile,u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u);folder=DATA/'updates';folder.mkdir(exist_ok=True)
    pid=secrets.token_hex(16);path=folder/(pid+'.zip');size=0;digest=hashlib.sha256()
    try:
        with path.open('wb') as target:
            while block:=await file.read(4*1024**2):
                size+=len(block)
                if size>2*1024**3:raise ValueError('Пакет больше 2 ГБ')
                target.write(block);digest.update(block)
        import asyncio
        manifest=await asyncio.to_thread(validate_package,path)
    except Exception as e:
        path.unlink(missing_ok=True);m.fail(str(e))
    p=UpdatePackage(id=pid,version=manifest['version'],size=size,sha256=digest.hexdigest(),created=time.time());db.add(p)
    m.audit(db,u,'update_uploaded',pid,{'version':p.version});db.commit();return {'id':pid,'version':p.version}

class UpdateIn(BaseModel):
    package_id:str
    stations:list[str]=Field(min_length=1,max_length=250)

@router.post('/updates')
def update_devices(data:UpdateIn,u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u);p=db.get(UpdatePackage,data.package_id)
    if not p:m.fail('Выберите пакет обновления')
    ids=list(dict.fromkeys(data.stations))
    if server_id() in ids and len(ids)>1:m.fail('Сначала обновите рабочие места, затем сервер отдельным действием')
    if server_id() in ids and db.scalar(select(DeviceCommand.id).where(DeviceCommand.kind=='update',DeviceCommand.station_id!=server_id(),DeviceCommand.status.in_(['queued','running','prepared']),DeviceCommand.created>time.time()-600).limit(1)):
        m.fail('Дождитесь завершения обновления рабочих мест',409)
    for wid in ids:device(db,wid)
    queued=[enqueue(db,wid,'update',{'package_id':p.id,'sha256':p.sha256,'version':p.version}).id for wid in ids]
    m.audit(db,u,'update_dispatched',p.id,{'stations':ids});db.commit();return {'ids':queued}

@router.get('/packages/{pid}/download')
def download(pid:str,request:Request,db=Depends(m.getdb)):
    w=station(request,db,False)
    if not w or w.blocked:m.fail('Нет доступа',403)
    allowed=any(c.payload.get('package_id')==pid for c in db.scalars(select(DeviceCommand).where(DeviceCommand.station_id==w.id,DeviceCommand.kind=='update',DeviceCommand.status=='running')))
    if not allowed:m.fail('Обновление не назначено этому ПК',403)
    p=db.get(UpdatePackage,pid)
    if not p:m.fail('Пакет не найден',404)
    return FileResponse(DATA/'updates'/(p.id+'.zip'),filename='update.zip')


class ServerName(BaseModel):
    name:str=Field(min_length=1,max_length=100)

@router.post('/server-name')
def rename_server(data:ServerName,u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u)
    name=data.name.strip()
    if not name:m.fail('Введите название сервера')
    row=db.get(ManagementSetting,'server_identity')
    if not row:row=ManagementSetting(key='server_identity',value={});db.add(row)
    row.value={'name':name};m.audit(db,u,'server_renamed',name);db.commit()
    from .server_identity import activate
    activate()
    return {'name':name,'named':True}
