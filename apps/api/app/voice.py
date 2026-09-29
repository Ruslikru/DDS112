"""Version-safe speech jobs. Files are immutable, content addressed and resumable."""
import asyncio
import copy
import hashlib
import json
import shutil
import threading
from fastapi import APIRouter,Depends,Request
from fastapi.responses import FileResponse
from sqlalchemy import String,JSON,Text,select
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base,DATA,SessionLocal,TicketVersion,Media
from . import main as m
from .schemas import TicketData
from .caller import caller_gender
from local_ai.voice import VoiceRuntime

runtime=VoiceRuntime(DATA)
stopping=threading.Event()
router=APIRouter(prefix='/api/voice')

class VoiceJob(Base):
    __tablename__='voice_jobs'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    status:Mapped[str]=mapped_column(String(20),default='pending',index=True)
    data:Mapped[dict]=mapped_column(JSON)
    audio_id:Mapped[str|None]=mapped_column(String(64),nullable=True)
    error:Mapped[str]=mapped_column(Text,default='')

def prepare(data,db,owner,preserve=False):
    result=copy.deepcopy(data);cfg=runtime.settings()['pre']
    from .caller import enrich_task
    result['tasks']=[enrich_task(t) for t in result['tasks']]
    for task in result['tasks']:
        if preserve:
            old=next((db.get(VoiceJob,line['voice_key']) for c in task.get('contacts',[]) for line in c.get('voice_lines',[]) if line.get('voice_key') and db.get(VoiceJob,line['voice_key'])),None)
            if old:cfg=old.data['settings']
        speakers={c['id']:c.get('voice_gender','male') for c in task.get('contacts',[])}
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
            spec={'speaker_id':speaker,'text':event['text'],'gender':gender,'settings':cfg,'revision':'voice-v1'}
            key=hashlib.sha256(json.dumps(spec,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            event['voice_key']=key
            if not db.get(VoiceJob,key):db.add(VoiceJob(id=key,data={**spec,'owner':owner},status='pending'))
    db.flush()
    return result

def speech_items(task):
    return [*task.get('service_events',[]),*[line for c in task.get('contacts',[]) for line in c.get('voice_lines',[])]]


def keys(data):
    return {e['voice_key'] for t in data.get('tasks',[]) for e in speech_items(t) if e.get('voice_key')}


def readiness(data,db):
    required=keys(data)
    if not required:return {'ready':True,'generated':0,'total':0,'failed':0}
    states={key:status for key,status in db.execute(select(VoiceJob.id,VoiceJob.status).where(VoiceJob.id.in_(required)))}
    generated=sum(states.get(key)=='ready' for key in required)
    failed=sum(states.get(key)=='failed' for key in required)
    return {'ready':generated==len(required),'generated':generated,'total':len(required),'failed':failed}


def attach_audio(data,db):
    result=copy.deepcopy(data)
    for task in result.get('tasks',[result]):
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
        for job in db.scalars(select(VoiceJob).where(VoiceJob.status=='running')):job.status='pending'
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
        for a in db.scalars(select(Attempt).where(Attempt.status.notin_(['completed','aborted']))):a.snapshot=attach_audio(a.snapshot,db)
        db.commit()


def ensure_ready(data,db):
    status=readiness(data,db)
    if not status['ready']:
        label='Ошибка генерации звука. Попросите преподавателя проверить очередь.' if status['failed'] else 'Звук для билета ещё генерируется.'
        m.fail(f"{label} Готово {status['generated']} из {status['total']} записей.",409)

def generate_one():
    with SessionLocal() as db:
        job=db.scalar(select(VoiceJob).where(VoiceJob.status=='pending'))
        if not job:return
        job.status='running';db.commit()
        try:
            path,meta=runtime.synthesize(job.data['text'],job.data['gender'],'pre',job.data['settings'])
            raw=path.read_bytes();audio_id=hashlib.sha256(raw).hexdigest();dest=DATA/'media'/audio_id
            if not dest.exists():shutil.copyfile(path,dest)
            if not db.get(Media,audio_id):db.add(Media(id=audio_id,filename=audio_id+'.wav',mime='audio/wav',size=len(raw),owner_id=job.data['owner']))
            job.audio_id=audio_id;job.data={**job.data,**meta,'size':len(raw),'sha256':audio_id,'mime':'audio/wav'};job.status='ready';job.error=''
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

@router.post('/settings')
def save_settings(data:dict,u=Depends(m.current)):
    m.admin(u)
    try:runtime.save(data)
    except ValueError as e:m.fail(str(e))
    return runtime.status()

@router.post('/prepare')
def prepare_draft(data:TicketData,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u);result=prepare(data.model_dump(),db,u.id);db.commit()
    return {'data':result,'keys':list(keys(result))}

@router.post('/jobs')
def jobs(data:dict,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u)
    ids=data.get('keys',[])[:500]
    return [{'id':j.id,'status':j.status,'error':j.error,'audio_id':j.audio_id,'text':j.data['text'],'speaker_id':j.data['speaker_id'],'duration':j.data.get('duration')} for j in db.scalars(select(VoiceJob).where(VoiceJob.id.in_(ids)))]

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
    for v in db.scalars(select(TicketVersion).where(TicketVersion.published==True)):
        ids=[]
        for key in keys(v.data):
            j=db.get(VoiceJob,key)
            if j and j.status=='ready':
                ids.append(j.audio_id);files[j.audio_id]={'id':j.audio_id,'sha256':j.audio_id,'size':j.data['size']}
        versions.append({'id':v.id,'sha256':hashlib.sha256(json.dumps(v.data,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'audio':ids})
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
