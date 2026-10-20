"""Prepare and verify packaged speech for the six starter tickets and introductions."""
import hashlib,json,os,shutil,sys
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
destination=Path(sys.argv[1]).resolve()
destination.mkdir(parents=True,exist_ok=False)
data=destination/'check-data'
builtin=destination/'builtin';builtin.mkdir()
os.environ.update(DATA_DIR=str(data),DATABASE_URL='sqlite:///'+(data/'speech.db').as_posix(),
                  VOICE_AUTO_GENERATE='false',AI_AUTO_REVIEW='false',TRAINING_CATALOG='full',DEMO_PASSWORD='Training112!')
from fastapi.testclient import TestClient
from sqlalchemy import select
from apps.api.app.main import app
from apps.api.app import voice
from apps.api.app.db import SessionLocal,Ticket,TicketVersion,User
from apps.api.app.seed import sample_tasks
from apps.api.app.schemas import TicketData
from apps.api.app.test_catalog import TITLES
from local_ai.voice import VoiceRuntime
from local_ai.engine import LocalEngine

original=ROOT/'local_ai/voice/builtin'
records=json.loads((original/'manifest.json').read_text('utf-8'))
for record in records:
    target=builtin/record['file']
    if not target.exists():shutil.copyfile(original/record['file'],target)

with patch.object(VoiceRuntime,'warm',return_value={}),patch.object(VoiceRuntime,'warm_pre',return_value=None),patch.object(LocalEngine,'start',return_value=None),TestClient(app):
    with SessionLocal() as db:
        owner=db.scalar(select(User).where(User.role=='admin'))
        # Audio compatibility only: these old scenarios are not seeded into the
        # new classroom, but existing installations may still contain them.
        from apps.api.app.communication_examples import seed as legacy_communications
        legacy_communications(db)
        compatibility=set()
        for task in sample_tasks():
            old=TicketData.model_validate({'title':task['title'],'tasks':[task]}).model_dump()
            compatibility.update(voice.keys(voice.prepare(old,db,owner.id)))
        titles={v.data['title'] for v in db.scalars(select(TicketVersion))}
        for task in sample_tasks():
            if task.get('id')=='dds-water':task={**task,'title':TITLES[0]}
            if task['title'] not in TITLES or task['title'] in titles:continue
            payload=TicketData.model_validate({'title':task['title'],'tasks':[task]}).model_dump()
            ticket=Ticket(title=payload['title'],created_by=owner.id);db.add(ticket);db.flush()
            db.add(TicketVersion(ticket_id=ticket.id,number=1,published=True,data=voice.prepare(payload,db,owner.id)))
        db.commit()
        versions=db.scalars(select(TicketVersion)).all()
        from apps.api.app.classroom_models import MiniQuestion
        needed={key for version in versions for key in voice.keys(version.data)}
        needed.update(compatibility)
        needed.update(q.data['voice_key'] for q in db.scalars(select(MiniQuestion)) if q.data.get('voice_key'))
        pending=[job.data for job in db.scalars(select(voice.VoiceJob)) if job.id in needed and job.status!='ready']
        titles=[v.data['title'] for v in versions]
        assert set(TITLES)<=set(titles), 'Both base tickets must be covered'
    print('NEEDED',len(needed),'PENDING',len(pending),'TICKETS',titles,flush=True)
    generated=[];known={(r['text'],r['gender'],r['tts']) for r in records}
    try:
        for index,job in enumerate(pending,1):
            identity=(job['text'],job['gender'],job['settings']['tts'])
            if identity in known:continue
            file,metrics=voice.runtime.synthesize(job['text'],job['gender'],settings=job['settings'])
            raw=file.read_bytes();assert raw.startswith(b'RIFF') and metrics['duration']>0
            digest=hashlib.sha256(raw).hexdigest();target=builtin/(digest+'.wav')
            if not target.exists():shutil.copyfile(file,target)
            record={'text':job['text'],'gender':job['gender'],'tts':job['settings']['tts'],'file':target.name,'duration':metrics['duration']}
            records.append(record);known.add(identity);generated.append(record)
            print('GENERATED',index,'/',len(pending),job['text'][:70],flush=True)
    finally:voice.runtime.stop()
    (builtin/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf-8')
    voice.runtime.bundle=destination
    with SessionLocal() as db:
        voice.restore_builtin(db);db.commit()
        assert all(db.get(voice.VoiceJob,key).status=='ready' for key in needed)
        report={'ready':True,'needed_keys':len(needed),'generated':len(generated),'total_records':len(records),'titles':titles}
    (destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('READY',builtin,flush=True)
