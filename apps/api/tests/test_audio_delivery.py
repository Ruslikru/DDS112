import base64,copy,hashlib,io,json,threading,wave
from pathlib import Path
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_flows import app,TestClient,SessionLocal
from apps.api.app import voice,management
from apps.api.app.db import Assignment,TicketVersion,Attempt
from apps.api.app.dds_flow import create_attempt
from local_ai.context import on_device
from device_runtime.voice_sync import VoiceSync

def wav():
    target=io.BytesIO()
    with wave.open(target,'wb') as out:
        out.setparams((1,2,24000,0,'NONE','not compressed'));out.writeframes(b'\0\0'*240)
    return target.getvalue()

@pytest.mark.parametrize('preview',[False,True])
def test_missing_speech_blocks_all_attempts(preview):
    with TestClient(app),SessionLocal() as db:
        assignment=db.scalar(select(Assignment))
        task=copy.deepcopy(db.get(TicketVersion,assignment.version_id).data['tasks'][0])
        task['service_events']=[{'kind':'incoming_call','text':'Unprepared report','after':1}]
        with pytest.raises(HTTPException) as error:create_attempt(db,assignment,task,999,preview=preview)
        assert error.value.status_code==409
        assert not db.scalar(select(Attempt).where(Attempt.assignment_id==assignment.id,Attempt.task_index==999))

def test_ready_flag_does_not_hide_missing_or_corrupt_wav(tmp_path,monkeypatch):
    monkeypatch.setattr(voice,'DATA',tmp_path);(tmp_path/'media').mkdir()
    raw=wav();key=hashlib.sha256(raw).hexdigest()
    job=voice.VoiceJob(id='fake',audio_id=key,status='ready',data={})
    assert not voice.recording_ready(job)
    file=tmp_path/'media'/key;file.write_bytes(b'not a wav')
    assert not voice.recording_ready(job)
    file.write_bytes(raw)
    assert voice.recording_ready(job)

def test_native_cache_verifies_audio_before_acknowledging_version(tmp_path,monkeypatch):
    raw=wav();key=hashlib.sha256(raw).hexdigest()
    manifest={'files':[{'sha256':key,'size':len(raw)}],'versions':[{'id':12,'sha256':'revision','audio':[key],'ready':True}]}
    cache=VoiceSync.__new__(VoiceSync);cache.root=tmp_path;cache.stop_event=threading.Event();cache.status={}
    requests=[]
    class Response(io.BytesIO):status=200
    def request(path,headers=None):
        requests.append(path)
        return Response(json.dumps(manifest).encode() if path.endswith('manifest') else raw)
    cache.request=request
    cache.sync()
    assert cache.status['versions']=={'12':'revision'}
    assert base64.b64decode(cache.audio(key).split(',')[1])==raw
    cache.sync()
    assert len([r for r in requests if '/files/' in r])==1
    manifest['versions'][0]['ready']=False
    cache.sync()
    assert cache.status['versions']=={}

def test_launch_waits_for_native_cache_matching_current_version(monkeypatch):
    with TestClient(app),SessionLocal() as db:
        version=db.scalar(select(TicketVersion))
        digest=hashlib.sha256(json.dumps(version.data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        monkeypatch.setitem(management.state,'cache-pc',{'metrics':{'version':'test','voice_sync':{'versions':{}}}})
        with on_device('cache-pc'):
            assert not voice.device_audio_ready(db,version.id)
            management.state['cache-pc']['metrics']['voice_sync']['versions'][str(version.id)]=digest
            assert voice.device_audio_ready(db,version.id)
            management.state['cache-pc']['metrics']['voice_sync']['versions'][str(version.id)]='older revision'
            assert not voice.device_audio_ready(db,version.id)


@pytest.fixture(autouse=True)
def no_model_warmup(monkeypatch):
    from apps.api.app import startup_models
    async def idle():pass
    monkeypatch.setattr(startup_models,'warm_models',idle)
