"""Version-safe speech jobs. Files are immutable, content addressed and resumable."""
import asyncio
import copy
import hashlib
import json
import shutil
import threading
import time
from fastapi import APIRouter,Depends,Request
from pydantic import BaseModel,Field
from fastapi.responses import FileResponse
from sqlalchemy import Float,String,JSON,Text,select,update
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base,DATA,SessionLocal,TicketVersion,Media
from . import main as m
from .schemas import TicketData
from .caller import caller_gender
from local_ai.voice import VoiceRuntime,PIPER_MODELS
from local_ai.engine import AIUnavailable

runtime=VoiceRuntime(DATA)

def local_speech(operation,args):
    from .ai_workers import broker
    schema={'type':'object','properties':{'audio':{'type':'string','maxLength':15000000},'meta':{'type':'string','maxLength':50000}},'required':['meta'],'additionalProperties':False}
    response=broker.submit({'operation':operation,'args':args,'schema':schema})
    return response[0] if response is not None else None

runtime.remote=local_speech
stopping=threading.Event()
# Lines a teacher is waiting for right now (a publication or an assignment refused for missing sound):
# kept in memory because the refused request rolls its own transaction back.
urgent=set()
urgent_lock=threading.Lock()
router=APIRouter(prefix='/api/voice')

class VoiceJob(Base):
    __tablename__='voice_jobs'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    status:Mapped[str]=mapped_column(String(20),default='pending',index=True)
    data:Mapped[dict]=mapped_column(JSON)
    audio_id:Mapped[str|None]=mapped_column(String(64),nullable=True)
    error:Mapped[str]=mapped_column(Text,default='')
    # When a teacher last asked for these lines; the worker takes the newest request first, so a ticket
    # saved in front of the class is voiced before the backlog of built-in tickets (0 = background order).
    priority:Mapped[float]=mapped_column(Float,default=0,server_default='0',index=True)

def prioritize(db,ids):
    """Moves pending lines to the front of the queue (newest request first)."""
    ids=list(ids)
    if ids:db.execute(update(VoiceJob).where(VoiceJob.id.in_(ids),VoiceJob.status=='pending').values(priority=time.time()))

def prepare(data,db,owner,preserve=False,soon=False):
    """`soon`: the teacher is authoring this ticket now, its lines jump the background queue."""
    result=copy.deepcopy(data);cfg=runtime.settings()['pre']
    from .caller import enrich_task
    result['tasks']=[enrich_task(t) for t in result['tasks']]
    for task in result['tasks']:
        from .call_audio import prepare_task
        prepare_task(task)
        if preserve:
            old=next((db.get(VoiceJob,line['voice_key']) for c in task.get('contacts',[]) for line in c.get('voice_lines',[]) if line.get('voice_key') and db.get(VoiceJob,line['voice_key'])),None)
            if old:cfg=old.data['settings']
        speakers={c['id']:c.get('voice_gender','male') for c in task.get('contacts',[])}
        voices={c['id']:c.get('voice_tts') for c in task.get('contacts',[])}
        for contact in task.get('contacts',[]):
            contact['voice_lines']=[{'text':text,'spoken':True,'contact_id':contact['id'],'voice_gender':contact.get('voice_gender','male')} for text in dict.fromkeys([contact.get('response',''),*contact.get('updates',[]),*[q['answer'] for q in contact.get('questions',[])]]) if text.strip()]
        for contact in task.get('contacts',[]):
            if not contact.get('name'):continue
            greeting=f"{contact['name']}. Слушаю вас." if contact.get('kind')=='caller' else f"{contact['name']}. {task.get('own_service') or 'Служба реагирования'} на связи. Слушаю вас."
            contact['voice_lines'].append({'text':greeting,'role':'greeting','spoken':True,'contact_id':contact['id'],'voice_gender':contact.get('voice_gender','male')})
        for event in speech_items(task):
            event.pop('voice_key',None);event.pop('audio_id',None)
            if event.get('kind')!='incoming_call' and not event.get('spoken'):continue
            if not str(event.get('text','')).strip():continue
            speaker=event.get('contact_id') or event.get('who','brigade')
            gender=speakers.setdefault(speaker,event.get('voice_gender','male'))
            event['voice_gender']=gender
            spec={'speaker_id':speaker,'text':event['text'],'gender':gender,'settings':{**cfg,**({'tts':voices[speaker]} if voices.get(speaker) else {})},'revision':'voice-v1'}
            key=hashlib.sha256(json.dumps(spec,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            event['voice_key']=key
            if not db.get(VoiceJob,key):
                from local_ai.context import device_id
                db.add(VoiceJob(id=key,data={**spec,'owner':owner,'device_id':device_id.get()},status='pending'))
    db.flush()
    restore_builtin(db)
    if soon:prioritize(db,keys(result))
    return result

def speech_items(task):
    return [*task.get('service_events',[]),*[line for c in task.get('contacts',[]) for line in c.get('voice_lines',[])]]


def keys(data):
    return {e['voice_key'] for t in data.get('tasks',[]) for e in speech_items(t) if e.get('voice_key')}


def pace(db):
    """Seconds one line took lately (median of the last 20 recordings), for a rough waiting time."""
    seconds=sorted(j.data.get('seconds') for j in db.scalars(select(VoiceJob).where(VoiceJob.status=='ready').order_by(VoiceJob.priority.desc()).limit(200)) if isinstance(j.data.get('seconds'),(int,float)))[-20:]
    return seconds[len(seconds)//2] if seconds else None

def waiting_label(lines,db):
    """«около 3 минут» for so many lines at the recent pace; empty when there is no measurement yet."""
    step=pace(db)
    if not step or not lines:return ''
    total=step*lines
    if total<60:return 'меньше минуты'
    minutes=round(total/60)
    return f'около {minutes} мин'

_verified_recordings={}
def recording_ready(job):
    if not job or job.status!='ready' or not job.audio_id:return False
    path=DATA/'media'/job.audio_id
    try:
        stat=path.stat();fingerprint=(stat.st_mtime_ns,stat.st_size)
        if _verified_recordings.get(str(path))==fingerprint:return True
        raw=path.read_bytes()
        valid=raw[:4]==b'RIFF' and raw[8:12]==b'WAVE' and hashlib.sha256(raw).hexdigest()==job.audio_id
        if valid:_verified_recordings[str(path)]=fingerprint
        return valid
    except OSError:return False

def readiness(data,db):
    required=keys(data)
    missing=sum(1 for task in data.get('tasks',[data]) for e in speech_items(task)
                if (e.get('spoken') or e.get('kind')=='incoming_call') and str(e.get('text','')).strip() and not e.get('voice_key'))
    jobs={j.id:j for j in db.scalars(select(VoiceJob).where(VoiceJob.id.in_(required)))}
    generated=sum(recording_ready(jobs.get(key)) for key in required)
    failed=sum(j.status=='failed' or j.status=='ready' and not recording_ready(j) for j in jobs.values())
    total=len(required)+missing
    return {'ready':generated==total,'generated':generated,'total':total,'failed':failed}

def device_audio_ready(db,version_id,student_id=None):
    from local_ai.context import device_id
    from .classroom_models import Workstation
    from .management import state,server_id
    wid=device_id.get()
    if wid is None and student_id is not None:
        w=db.scalar(select(Workstation).where(Workstation.user_id==student_id,Workstation.approved==True,Workstation.blocked==False).order_by(Workstation.last_seen.desc()))
        wid=w.id if w else None
    if not wid or wid==server_id():return True
    metrics=state.get(wid,{}).get('metrics',{})
    # Browser sessions have no native cache; the server still requires valid audio.
    if not metrics.get('version'):return True
    version=db.get(TicketVersion,version_id)
    digest=hashlib.sha256(json.dumps(version.data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return metrics.get('voice_sync',{}).get('versions',{}).get(str(version_id))==digest


def attach_audio(data,db,text_only=False):
    """Call sounds always; recorded lines unless the attempt runs as text (voicing was not complete at its start)."""
    result=copy.deepcopy(data)
    for task in result.get('tasks',[result]):
        from .call_audio import prepare_task
        prepare_task(task)
        if text_only:
            for contact in task.get('contacts',[]):contact['greeting_audio']=None
            continue
        for event in speech_items(task):
            job=db.get(VoiceJob,event.get('voice_key',''))
            if job and job.status=='ready':event['audio_id']=job.audio_id
        for contact in task.get('contacts',[]):
            contact['greeting_audio']=next((line.get('audio_id') for line in contact.get('voice_lines',[]) if line.get('role')=='greeting'),None)
    return result


def response_audio(contact,text,db):
    line=next((line for line in contact.get('voice_lines',[]) if line['text']==text),None)
    job=db.get(VoiceJob,line['voice_key']) if line and line.get('voice_key') else None
    return job.audio_id if job and job.status=='ready' else None


def restore_builtin(db):
    folder=runtime.bundle/'builtin';manifest=folder/'manifest.json'
    if not manifest.exists():return
    records=json.loads(manifest.read_text('utf-8'))
    for job in db.scalars(select(VoiceJob).where(VoiceJob.status.in_(['pending','failed']))):
        item=next((r for r in records if r['text']==job.data['text'] and r['gender']==job.data['gender'] and r['tts']==job.data['settings']['tts']),None)
        # Removed engines already fall back to Piper at inference time. Reuse the
        # equivalent bundled line instead of regenerating an old classroom's queue.
        if not item and job.data['settings']['tts'] not in PIPER_MODELS:
            item=next((r for r in records if r['text']==job.data['text'] and r['gender']==job.data['gender'] and r['tts'] in PIPER_MODELS),None)
        if not item:continue
        path=folder/item['file']
        if not path.is_file():continue
        raw=path.read_bytes();audio_id=hashlib.sha256(raw).hexdigest()
        if path.stem!=audio_id:continue
        target=DATA/'media'/audio_id
        if not target.exists():shutil.copyfile(path,target)
        if not db.get(Media,audio_id):db.add(Media(id=audio_id,filename=audio_id+'.wav',mime='audio/wav',size=len(raw),owner_id=job.data['owner']))
        job.audio_id=audio_id;job.status='ready';job.error='';job.data={**job.data,'size':len(raw),'duration':item['duration'],'sha256':audio_id}
        db.flush()


def recover():
    stopping.clear()
    with SessionLocal() as db:
        for job in db.scalars(select(VoiceJob)):
            if job.status=='running' or job.status=='ready' and not recording_ready(job):job.status='pending'
        # Upgrade saved tickets without changing their authored content or existing recordings.
        from .db import Ticket,Attempt,Assignment
        from .caller import enrich_task, generated_details
        for v in db.scalars(select(TicketVersion)):
            enriched=copy.deepcopy(v.data)
            for task in enriched.get('tasks',[]):
                if task.get('mode')=='112' and not task.get('scenario_details') and str(task.get('source','')).startswith('S2,'):
                    task['scenario_details']=generated_details(task)
            enriched['tasks']=[enrich_task(t) for t in enriched.get('tasks',[])]
            if enriched!=v.data:v.data=enriched
            if any(c.get('response') and not any(x.get('role')=='greeting' for x in c.get('voice_lines',[])) for t in v.data.get('tasks',[]) for c in t.get('contacts',[])):
                prepared=prepare(v.data,db,db.get(Ticket,v.ticket_id).created_by,preserve=True)
                original=copy.deepcopy(v.data)
                for old,new in zip(original['tasks'],prepared['tasks']):
                    for c,n in zip(old.get('contacts',[]),new.get('contacts',[])):c['voice_lines']=n['voice_lines']
                v.data=original
        for a in db.scalars(select(Attempt).where(Attempt.status.notin_(['completed','aborted']))):
            if any(not any(x.get('role')=='greeting' for x in c.get('voice_lines',[])) for c in a.snapshot.get('contacts',[])):
                owner=db.get(Assignment,a.assignment_id).teacher_id
                updated=prepare({'tasks':[a.snapshot]},db,owner,preserve=True)['tasks'][0]
                original=copy.deepcopy(a.snapshot)
                for c,n in zip(original.get('contacts',[]),updated.get('contacts',[])):c['voice_lines']=n['voice_lines']
                a.snapshot=original
        restore_builtin(db)
        for a in db.scalars(select(Attempt).where(Attempt.status.notin_(['completed','aborted']))):
            if readiness({'tasks':[a.snapshot]},db)['ready']:
                a.state={**a.state,'text_only':False}
                a.snapshot=attach_audio(a.snapshot,db)
        db.commit()


def ensure_ready(data,db):
    """A playable ticket always requires every recording, including teacher previews."""
    from .call_audio import prepare_task,ensure_assets
    try:
        for task in data.get('tasks',[data]):
            if task.get('mode')=='dds':ensure_assets(prepare_task(copy.deepcopy(task)))
    except (OSError,ValueError,KeyError):m.fail('Не удалось подготовить звуковое окружение звонка. Проверьте файлы программы.',409)
    status=readiness(data,db)
    if not status['ready']:
        with urgent_lock:urgent.update(keys(data))
        label='Ошибка генерации звука. Попросите преподавателя проверить очередь.' if status['failed'] else 'Звук для билета ещё генерируется.'
        m.fail(f"{label} Готово {status['generated']} из {status['total']} записей.",409)
    return status

def store_live_audio(db,path,owner):
    """Reuse immutable media storage and the application's existing authorization."""
    raw=path.read_bytes();key=hashlib.sha256(raw).hexdigest();dest=DATA/'media'/key
    if not dest.exists():shutil.copyfile(path,dest)
    if not db.get(Media,key):db.add(Media(id=key,filename=key+'.wav',mime='audio/wav',size=len(raw),owner_id=owner))
    return key

def next_job(db):
    """Lines a teacher is waiting for, then the most recently requested ticket, then the background backlog."""
    with urgent_lock:waiting=list(urgent)
    if waiting:
        job=db.scalar(select(VoiceJob).where(VoiceJob.id.in_(waiting),VoiceJob.status=='pending').limit(1))
        if job and job.data.get('retry_after',0)<=time.time():return job
        with urgent_lock:urgent.difference_update(waiting)
    return next((job for job in db.scalars(select(VoiceJob).where(VoiceJob.status=='pending').order_by(VoiceJob.priority.desc())) if job.data.get('retry_after',0)<=time.time()),None)

def generate_one():
    with SessionLocal() as db:
        job=next_job(db)
        if not job:return
        with urgent_lock:urgent.discard(job.id)
        job.status='running';db.commit()
        try:
            from local_ai.context import on_device
            with on_device(job.data.get('device_id')):
                path,meta=runtime.synthesize(job.data['text'],job.data['gender'],'pre',job.data['settings'])
            raw=path.read_bytes();audio_id=hashlib.sha256(raw).hexdigest();dest=DATA/'media'/audio_id
            if not dest.exists():shutil.copyfile(path,dest)
            if not db.get(Media,audio_id):db.add(Media(id=audio_id,filename=audio_id+'.wav',mime='audio/wav',size=len(raw),owner_id=job.data['owner']))
            job.audio_id=audio_id;job.data={**job.data,**meta,'size':len(raw),'sha256':audio_id,'mime':'audio/wav'};job.status='ready';job.error=''
        except AIUnavailable as e:
            job.status='pending';job.error=str(e)[:1000];job.data={**job.data,'retry_after':time.time()+15}
        except Exception as e:job.status='pending' if stopping.is_set() else 'failed';job.error='' if stopping.is_set() else str(e)[:1000]
        db.commit()

async def worker():
    while not stopping.is_set():
        await asyncio.to_thread(generate_one)
        await asyncio.sleep(1)

@router.get('/queue')
def queue(u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    jobs=list(db.scalars(select(VoiceJob)))
    return {'ready':sum(j.status=='ready' for j in jobs),'total':len(jobs),'pending':sum(j.status in ('pending','running') for j in jobs),'failed':[{'id':j.id,'text':j.data['text'],'error':j.error} for j in jobs if j.status=='failed']}

@router.get('/settings')
def settings(u=Depends(m.current)):
    m.staff(u);return runtime.status()

@router.get('/dialogue-settings')
def dialogue_settings(u=Depends(m.current)):
    m.staff(u)
    cfg=runtime.settings()['live']
    from local_ai.engine import engine
    return {'editable':u.role=='admin','dialogue_threads':engine.config()['threads'],**{k:cfg[k] for k in ('stt_threads','tts_threads')}}

@router.get('/call-status')
def call_status(u=Depends(m.current)):
    from local_ai.context import device_id
    from .management import state
    wid=device_id.get()
    if wid:
        device=state.get(wid,{})
        metrics=device.get('metrics',{})
        models=copy.deepcopy(metrics.get('local_models',{}))
        if time.time()-device.get('seen',0)>15:
            for model in models.values():model['state']='cold'
        return {'models':models,'cpu_percent':metrics.get('cpu_percent'),'cpu_scope':'machine'}
    from .startup_models import status
    return status()

@router.post('/dialogue-settings')
def save_dialogue_settings(data:dict,u=Depends(m.current)):
    m.admin(u)
    if set(data)-{'dialogue_threads','stt_threads','tts_threads'}:m.fail('Неизвестная настройка потоков')
    from local_ai.engine import engine,AIUnavailable
    try:
        engine.set_settings(**{('threads' if k=='dialogue_threads' else k):v for k,v in data.items()},threads_auto=False)
    except (ValueError,AIUnavailable) as error:m.fail(str(error))
    return dialogue_settings(u)

@router.post('/settings')
def save_settings(data:dict,u=Depends(m.current)):
    m.admin(u)
    try:runtime.save(data)
    except ValueError as e:m.fail(str(e))
    return runtime.status()

class TranscribeIn(BaseModel):
    audio:str=Field(min_length=1)

@router.post('/transcribe')
def transcribe(data:TranscribeIn,u=Depends(m.current),db=Depends(m.getdb)):
    """Speech to text on the server for the teacher assistant: a browser without the native bridge, same length limit as the bridge."""
    from .assistant import speech_prompt
    # Распознавание команд преподавателя использует локальную GigaAM.
    try:value=runtime.transcribe(data.audio,prompt=speech_prompt(db,u) if u.role in ('teacher','admin') else '',model='gigaam')
    except ValueError as e:m.fail(str(e))
    except Exception as e:
        # An empty recording is the speaker's problem, not an outage: Whisper reports it as an error string.
        if 'не распознана' in str(e):m.fail('Речь не распознана. Удерживайте кнопку, пока говорите, и проверьте, что микрофон включён.')
        if any(part in str(e) for part in ('End of file','Invalid data','В записи нет звука','пустая','слишком короткая')):
            m.fail('Запись не получилась. Удерживайте микрофон, произнесите фразу и отпустите кнопку.')
        import logging
        logging.exception('Microphone transcription failed')
        m.fail('Не удалось распознать запись. Повторите попытку. Если ошибка повторяется, сообщите преподавателю.',503)
    return {**{k:v for k,v in (value or {}).items() if k!='text'},'text':str((value or {}).get('text','')).strip()}

@router.post('/prepare')
def prepare_draft(data:TicketData,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u);result=prepare(data.model_dump(),db,u.id,soon=True);db.commit()
    return {'data':result,'keys':list(keys(result))}

@router.post('/jobs')
def jobs(data:dict,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    ids=data.get('keys',[])[:500]
    return [{'id':j.id,'status':j.status,'error':j.error,'audio_id':j.audio_id,'text':j.data['text'],'speaker_id':j.data['speaker_id'],'duration':j.data.get('duration')} for j in db.scalars(select(VoiceJob).where(VoiceJob.id.in_(ids)))]

@router.post('/jobs/retry-failed')
def retry_failed(u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u);n=db.execute(update(VoiceJob).where(VoiceJob.status=='failed').values(status='pending',error='')).rowcount;db.commit()
    return {'ok':True,'count':n}

@router.post('/jobs/{id}/retry')
def retry(id:str,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u);job=db.get(VoiceJob,id)
    if not job:m.fail('Запись не найдена',404)
    if job.status=='failed':job.status='pending';job.error='';db.commit()
    return {'ok':True}

@router.get('/manifest')
def manifest(request:Request,db=Depends(m.getdb)):
    from .classroom import station
    station(request,db)
    versions=[];files={}
    for v in db.scalars(select(TicketVersion)):
        ids=[]
        for key in keys(v.data):
            j=db.get(VoiceJob,key)
            if recording_ready(j):
                ids.append(j.audio_id);files[j.audio_id]={'id':j.audio_id,'sha256':j.audio_id,'size':j.data['size']}
        versions.append({'id':v.id,'sha256':hashlib.sha256(json.dumps(v.data,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'audio':ids,'ready':readiness(v.data,db)['ready']})
    from .classroom_models import MiniQuestion
    for q in db.scalars(select(MiniQuestion).where(MiniQuestion.active==True)):
        j=db.get(VoiceJob,q.data.get('voice_key',''))
        if j and j.status=='ready':files[j.audio_id]={'id':j.audio_id,'sha256':j.audio_id,'size':j.data['size']}
    return {'versions':versions,'files':list(files.values())}

@router.get('/files/{id}')
def file(id:str,request:Request,db=Depends(m.getdb)):
    allowed=manifest(request,db)
    if id not in {f['id'] for f in allowed['files']}:m.fail('Запись недоступна',403)
    return FileResponse(DATA/'media'/id,media_type='audio/wav',headers={'ETag':'"'+id+'"'})

@router.get('/attempts/{id}/catalog')
def catalog(id:int,u=Depends(m.current),db=Depends(m.getdb)):
    from .caller import caller_questions
    p=db.get(m.Attempt,id)
    if not p or p.student_id!=u.id or p.status!='active' or p.state.get('call')!='connected':m.fail('Сначала примите звонок',403)
    return {'speaker_id':'caller','facts':{**p.snapshot.get('initial_card',{}),**p.snapshot.get('expected_card',{})},'intro':p.snapshot['intro'],'gender':caller_gender(p.snapshot),'questions':[{'id':q['id'],'question':q['question'],'answer':q['answer']} for q in caller_questions(p.snapshot)],'history':p.state.get('dialogue',[])[-24:]}

@router.post('/attempts/{id}/question')
def local_question(id:int,data:dict,u=Depends(m.current),db=Depends(m.getdb)):
    from .schemas import Command
    return m.apply_command(id,Command(command_id=str(data.get('command_id','')),revision=data['revision'],type='ai_question',payload={'id':data.get('id'),'text':str(data.get('text',''))[:500],'voice_reply':str(data.get('reply',''))[:1500],'voice_gender':data.get('gender') if data.get('gender') in ('male','female') else 'female','ai':{'mode':'local-workstation'}}),u,db,_trusted_ai=True)
