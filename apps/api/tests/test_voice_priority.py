"""Lines of the ticket a teacher is working on are voiced before the background backlog."""
import copy
import hashlib
import uuid
import wave
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_flows import app, TestClient, login, HEAD, SessionLocal

@pytest.fixture
def spoken(monkeypatch,tmp_path):
    from apps.api.app import voice
    calls=[]
    def synthesize(text,*args):
        calls.append(text)
        path=tmp_path/(hashlib.sha256(text.encode()).hexdigest()+'.wav')
        with wave.open(str(path),'wb') as out:
            out.setparams((1,2,24000,0,'NONE','not compressed'));out.writeframes(b'\0\0'*240)
        return path,{'duration':.01,'voice':'test','seconds':0}
    monkeypatch.setattr(voice.runtime,'synthesize',synthesize)
    voice.urgent.clear()
    return calls

def backlog(db,count=3):
    """Pending lines of other tickets, queued earlier and never asked for."""
    from apps.api.app import voice
    spec={'owner':1,'speaker_id':'brigade','gender':'male','settings':voice.runtime.settings()['pre']}
    ids=[f'backlog-{uuid.uuid4().hex[:8]}' for _ in range(count)]
    for i,key in enumerate(ids):db.add(voice.VoiceJob(id=key,status='pending',data={**spec,'text':f'Фоновая реплика {i}'}))
    db.commit()
    return ids

def ticket_with_line(c,text):
    base=next(v['data'] for v in c.get('/api/tickets').json() if any(t.get('service_events') for t in v['data']['tasks']))
    data=copy.deepcopy(base);data['tasks']=data['tasks'][:1];data['title']='Озвучка вне очереди '+text[-8:]
    task=data['tasks'][0];task['service_events']=[{'kind':'incoming_call','text':text,'contact_id':task['contacts'][0]['id'],'after':1}]
    return data

def test_saved_ticket_is_voiced_before_the_backlog(spoken):
    from apps.api.app import voice
    with TestClient(app) as c:
        login(c,'teacher')
        with SessionLocal() as db:old=backlog(db)
        line='Новая реплика бригады '+uuid.uuid4().hex[:8]
        # Saved without the test helper that would voice the whole queue at once.
        saved=c.post('/api/tickets',json=ticket_with_line(c,line),headers=HEAD);assert saved.status_code==200,saved.text
        with SessionLocal() as db:
            version=db.get(voice.TicketVersion,saved.json()['id'])
            mine={key for key in voice.keys(version.data) if db.get(voice.VoiceJob,key).status=='pending'}
            assert mine and all(db.get(voice.VoiceJob,key).priority>0 for key in mine)
            assert all(db.get(voice.VoiceJob,key).priority==0 for key in old)
        voice.generate_one()
        with SessionLocal() as db:
            assert any(db.get(voice.VoiceJob,key).status=='ready' for key in mine)
            assert all(db.get(voice.VoiceJob,key).status=='pending' for key in old),'the backlog waits'
        assert not any(text.startswith('Фоновая реплика') for text in spoken)

def test_refused_publication_moves_the_ticket_first(spoken):
    from apps.api.app import voice
    with TestClient(app) as c:
        login(c,'teacher')
        with SessionLocal() as db:
            old=backlog(db)
            # A ticket prepared in the background (seeded, not saved by a teacher): its lines have no priority.
            data=voice.prepare(ticket_with_line(c,'Реплика ожидающего билета '+uuid.uuid4().hex[:8]),db,1)
            db.commit()
            waiting={key for key in voice.keys(data) if db.get(voice.VoiceJob,key).status=='pending'}
            assert waiting
            # A newer ticket saved by a teacher would normally go first…
            fresh=voice.prepare(ticket_with_line(c,'Реплика свежего билета '+uuid.uuid4().hex[:8]),db,1,soon=True);db.commit()
            fresh={key for key in voice.keys(fresh) if db.get(voice.VoiceJob,key).status=='pending'}-waiting
            assert fresh
            with pytest.raises(HTTPException) as refused:voice.ensure_ready(data,db)
            assert refused.value.status_code==409
        # …but the teacher is waiting for the refused one right now.
        voice.generate_one()
        with SessionLocal() as db:
            assert any(db.get(voice.VoiceJob,key).status=='ready' for key in waiting)
            assert all(db.get(voice.VoiceJob,key).status=='pending' for key in fresh)
            assert all(db.get(voice.VoiceJob,key).status=='pending' for key in old)
        for _ in range(len(waiting)):voice.generate_one()
        with SessionLocal() as db:
            assert all(db.get(voice.VoiceJob,key).status=='ready' for key in waiting)
        assert not voice.urgent & waiting,'served lines leave the urgent list'

def test_background_order_still_drains(spoken):
    from apps.api.app import voice
    with TestClient(app) as c:
        with SessionLocal() as db:
            old=backlog(db,2)
            # Only the backlog is left pending in this check.
            for job in db.scalars(select(voice.VoiceJob).where(voice.VoiceJob.status=='pending',voice.VoiceJob.id.notin_(old))):job.status='failed'
            db.commit()
        voice.generate_one();voice.generate_one()
        with SessionLocal() as db:
            assert all(db.get(voice.VoiceJob,key).status=='ready' for key in old)
