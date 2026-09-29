import copy
import hashlib
import wave
from test_flows import app,TestClient,login,post,HEAD,SessionLocal

def test_version_audio_cache_and_start_gate(monkeypatch,tmp_path):
    from apps.api.app import voice
    from apps.api.app.db import TicketVersion
    calls=[]
    def synthesize(text,*args):
        calls.append(text)
        path=tmp_path/(hashlib.sha256(text.encode()).hexdigest()+'.wav')
        with wave.open(str(path),'wb') as out:
            out.setparams((1,2,24000,0,'NONE','not compressed'));out.writeframes(b'\0\0'*240)
        return path,{'duration':.01,'voice':'test','seconds':0}
    monkeypatch.setattr(voice.runtime,'synthesize',synthesize)
    with TestClient(app) as c:
        login(c,'teacher')
        base=next(v['data'] for v in c.get('/api/tickets').json() if any(t.get('service_events') for t in v['data']['tasks']))
        data=copy.deepcopy(base);data['tasks']=data['tasks'][:1]
        task=data['tasks'][0];task['service_events']=[{'kind':'incoming_call','text':'Первая уникальная реплика для проверки озвучки','contact_id':task['contacts'][0]['id'],'after':1}]
        prepared=post(c,'/voice/prepare',data).json();key=prepared['data']['tasks'][0]['service_events'][0]['voice_key']
        assert post(c,'/voice/jobs',{'keys':[key]}).json()[0]['status']=='pending'
        with SessionLocal() as db:
            import pytest
            from fastapi import HTTPException
            with pytest.raises(HTTPException):voice.ensure_ready(prepared['data'],db)
        # Process this job without loading speech weights in API tests.
        with SessionLocal() as db:
            for j in db.query(voice.VoiceJob).filter(voice.VoiceJob.status=='pending'):j.status='failed'
            db.get(voice.VoiceJob,key).status='pending';db.commit()
        voice.generate_one()
        ready=post(c,'/voice/jobs',{'keys':[key]}).json()[0]
        assert ready['status']=='ready'
        assert c.get('/api/media/'+ready['audio_id']).content[:4]==b'RIFF'
        unchanged=post(c,'/voice/prepare',data).json()
        assert key in unchanged['keys'] and len(calls)==1
        data['tasks'][0]['service_events'][0]['text']='Изменённая реплика'
        changed=post(c,'/voice/prepare',data).json()
        assert key not in changed['keys']
        assert post(c,'/voice/jobs',{'keys':[key]}).json()[0]['status']=='ready'
        assert c.get('/api/voice/manifest').status_code==403

def test_voice_settings_validation(tmp_path):
    import pytest
    from local_ai.voice import VoiceRuntime
    v=VoiceRuntime(tmp_path)
    assert v.settings()['live']['delay']==1.5
    v.save({'live':{'stt':'base','tts_device':'cpu'}})
    assert VoiceRuntime(tmp_path).settings()['live']['stt']=='base'
    with pytest.raises(ValueError):v.save({'live':{'stt':'cloud'}})


def test_queue_restart_preserves_ready_and_requeues_interrupted(monkeypatch,tmp_path):
    from apps.api.app import voice
    from sqlalchemy import select
    with TestClient(app) as c:
        login(c,'teacher')
        with SessionLocal() as db:
            ready=db.scalar(select(voice.VoiceJob).where(voice.VoiceJob.status=='ready'))
            ready_id, audio_id=ready.id,ready.audio_id
            job=voice.VoiceJob(id='restart-check',status='running',data={'text':'Проверка перезапуска','owner':ready.data['owner'],'speaker_id':'brigade','gender':'male','settings':voice.runtime.settings()['pre']})
            db.add(job);db.commit()
        # Invoke production recovery directly (fixture wraps startup only).
        # Simulate the next startup without synthesis to observe pending state.
        monkeypatch.setattr(voice,'generate_one',lambda:None)
        # Production recovery is retained explicitly by the fixture.
        voice.recover_original()
        with SessionLocal() as db:
            assert db.get(voice.VoiceJob,'restart-check').status=='pending'
            assert db.get(voice.VoiceJob,ready_id).audio_id==audio_id
        q=c.get('/api/voice/queue').json()
        assert q['pending']>=1 and q['ready']>=1
