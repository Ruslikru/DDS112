"""Готовое окружение звонка: неизменяемые WAV и состояние занятой линии."""
import hashlib
import json
import re
import threading
import time
from functools import lru_cache
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .db import ROOT, Attempt, SessionLocal

def getdb():
    with SessionLocal() as db:yield db

def current(request:Request,db=Depends(getdb)):
    from . import main
    return main.current(request,db)

router=APIRouter(prefix='/api/call-audio')
FOLDER=ROOT/'content/call_audio/20261019'
_lock=threading.RLock()
_lines={}

@lru_cache(maxsize=1)
def library():
    value=json.loads((FOLDER/'manifest.json').read_text('utf-8'))
    if value.get('format')!='dds-audio-library/v1':raise ValueError('Неизвестная версия библиотеки звуков')
    return value['assets']

@lru_cache(maxsize=100)
def checked_path(key,mtime,size):
    row=library()[key];path=FOLDER/row['file']
    if path.resolve().parent!=FOLDER.resolve() or size!=row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
        raise ValueError('Повреждён файл звукового окружения: '+key)
    return path

def asset(key):
    row=library()[key];path=FOLDER/row['file'];stat=path.stat()
    checked_path(key,stat.st_mtime_ns,stat.st_size)
    return {**row,'url':'/api/call-audio/assets/'+key+'/'+row['sha256']}

def scene(task,contact,event=None):
    """Явное место важнее типа ЧП. Классификация выполняется до звонка."""
    incoming=event is not None
    event=event or {};explicit=(event.get('call_audio') or {}) if incoming else (contact.get('call_audio') or {})
    departure=not incoming and contact.get('kind')=='brigade' and re.search('выезжа|выезд|выех',contact.get('response',''),re.I) and explicit.get('siren')!='off'
    if explicit.get('backgrounds'):
        result={**explicit,'events_after_reply':[dict(e) for e in explicit.get('events_after_reply',[])]}
        if departure and not any(e['id']=='fx_siren_start' for e in result['events_after_reply']):result['events_after_reply'].append({'id':'fx_siren_start','seconds':0,'duration':1})
        return result
    words=str(event.get('text','')).casefold()
    incident=str(task.get('initial_card',{}).get('incident_type') or task.get('category','')).casefold()
    service=task.get('own_service','')
    location=explicit.get('location') or event.get('location') or contact.get('location')
    backgrounds=[];effects=[];ambient=[]
    locations={'office':'bg_dispatch_office','station':'bg_fire_station','vehicle':'bg_vehicle_interior','road':'bg_road_traffic','courtyard':'bg_street_courtyard','corridor':'bg_building_corridor','water':'bg_water_wind','forest':'bg_forest','platform':'bg_station_platform'}
    if location in locations:backgrounds=[locations[location]]
    elif contact.get('kind')=='caller':backgrounds=['bg_street_courtyard']
    elif contact.get('kind')=='service':backgrounds=['bg_dispatch_office']
    elif re.search('пробк|в пути|задерж|едем|машин',words):backgrounds=['bg_vehicle_interior']
    elif event:
        backgrounds=['bg_fire_scene' if re.search('пожар|горени',incident) and not re.search('потуш|устран|заверш|ликвид',words) else 'bg_road_traffic' if 'дтп' in incident else 'bg_street_courtyard']
    else:backgrounds=['bg_fire_station' if '101' in service else 'bg_dispatch_office']
    if explicit.get('siren')=='on':backgrounds.append('bg_siren_distant')
    if explicit.get('horn') is True:ambient=['fx_car_horn']
    if departure or explicit.get('siren')=='departure':effects=[{'id':'fx_siren_start','seconds':0,'duration':1}]
    return {'backgrounds':backgrounds,'ambient_events':ambient,'events_after_reply':effects}

def prepare_task(task):
    for contact in task.get('contacts',[]):
        if contact.get('kind')=='brigade':contact['name']='Старший бригады'
        contact['call_audio']=scene(task,contact)
    for event in task.get('service_events',[]):
        if event.get('kind')!='incoming_call':continue
        contact=next((c for c in task.get('contacts',[]) if c['id']==event.get('contact_id')),{'kind':'brigade'})
        if contact.get('kind')=='brigade':event['who']='Старший бригады'
        event['call_audio']=scene(task,contact,event)
    return task

def ensure_assets(task):
    required={'ring','ringback','hangup'}
    for item in [*task.get('contacts',[]),*task.get('service_events',[])]:
        audio=item.get('call_audio',{})
        required.update(audio.get('backgrounds',[]));required.update(audio.get('ambient_events',[]))
        required.update(x['id'] for x in audio.get('events_after_reply',[]))
    for key in required:asset(key)

def line_busy(attempt_id):
    with _lock:
        value=_lines.get(attempt_id,{})
        return value.get('until',0)>time.monotonic()

def session_active(attempt_id,session):
    with _lock:
        value=_lines.get(attempt_id,{})
        return value.get('active',False) and value.get('session')==session and value.get('until',0)>time.monotonic()

class LineState(BaseModel):
    session:str=Field(min_length=8,max_length=100)
    active:bool

@router.post('/attempts/{attempt_id}/line')
def update_line(attempt_id:int,data:LineState,u=Depends(current),db=Depends(getdb)):
    from . import main as m
    attempt=db.get(Attempt,attempt_id)
    if not attempt or not (attempt.student_id==u.id or u.role in ('teacher','admin') and m.visible(db,u,attempt.student_id)):m.fail('Звонок недоступен',403)
    with _lock:
        old=_lines.get(attempt_id,{})
        if data.active:
            if old.get('active') and old.get('session')!=data.session and old.get('until',0)>time.monotonic():m.fail('На этом рабочем месте уже идёт звонок',409)
            _lines[attempt_id]={'session':data.session,'active':True,'until':time.monotonic()+60}
        elif old.get('session')==data.session:
            _lines[attempt_id]={'session':data.session,'active':False,'until':time.monotonic()+2.5}
    return {'ok':True}

@router.get('/library')
def manifest(u=Depends(current)):
    from . import main as m
    try:return {'format':'dds-audio-library/v1','assets':{key:asset(key) for key in library()}}
    except (OSError,ValueError,KeyError) as error:m.fail('Не удалось подготовить звуки звонка: '+str(error),503)

@router.get('/assets/{key}/{sha}')
def get_asset(key:str,sha:str,u=Depends(current)):
    from . import main as m
    try:
        row=asset(key)
        if sha!=row['sha256']:m.fail('Версия аудио изменилась. Обновите карточку.',409)
        return FileResponse(FOLDER/row['file'],media_type='audio/wav',headers={'Cache-Control':'private, max-age=31536000, immutable','ETag':sha})
    except (OSError,ValueError,KeyError):m.fail('Звук звонка отсутствует или повреждён. Обратитесь к преподавателю.',503)
