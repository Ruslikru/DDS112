import json
import threading
import time
from pathlib import Path
import pytest
from test_flows import app,TestClient,login,post,HEAD
from local_ai.engine import LocalEngine,AIUnavailable
from local_ai.resources import automatic_threads
from local_ai.context import on_device,device_id
from apps.api.app.ai_workers import Broker

SCHEMA={'type':'object','properties':{'text':{'type':'string'}},'required':['text']}

@pytest.mark.parametrize('capacity,expected',[(1,(1,1,1)),(2,(1,1,1)),(4,(2,1,1)),(6,(4,1,1)),(8,(4,2,2)),(10,(6,2,2)),(12,(8,2,2)),(32,(8,2,2))])
def test_automatic_budget(capacity,expected):
    assert tuple(automatic_threads(capacity).values())==expected
    assert sum(expected)<=max(3,capacity)

def test_settings_persist_and_voice_uses_same_device(tmp_path,monkeypatch):
    from local_ai import resources
    from local_ai.voice import VoiceRuntime
    monkeypatch.setattr(resources,'cpu_threads',lambda:12)
    engine=LocalEngine(data=tmp_path/'qwen')
    engine.set_settings(threads_auto=False,threads=6,stt_threads=3,tts_threads=2,stt_device='cpu')
    voice=VoiceRuntime(tmp_path/'voice');voice.llm=engine
    assert voice.settings()['live']['stt_threads']==3
    assert LocalEngine(data=engine.data).config()['threads']==6
    with pytest.raises(ValueError):engine.set_settings(threads_auto=False,threads=10,stt_threads=2,tts_threads=2)
    assert engine.config()['threads']==6
    engine.set_settings(threads_auto=True)
    assert engine.config()['threads']==8 and voice.settings()['live']['stt_threads']==2
    with pytest.raises(ValueError):engine.set_settings(stt_threads=13)

def test_broker_routes_only_to_origin_and_has_no_fallback():
    broker=Broker(lambda:{},timeout=.15)
    broker.poll('other',True)
    with on_device('origin'),pytest.raises(AIUnavailable):broker.dispatch('s','p',SCHEMA,20,0)
    broker.poll('origin',True)
    result=[]
    def run():
        with on_device('origin'):result.append(broker.dispatch('s','p',SCHEMA,20,0))
        assert device_id.get() is None
    thread=threading.Thread(target=run);thread.start()
    deadline=time.monotonic()+1
    while not broker.jobs and time.monotonic()<deadline:time.sleep(.001)
    assert broker.poll('other',True) is None
    job=broker.poll('origin',True)
    assert not broker.finish('other',job['id'],{'text':'ok'},'')
    assert broker.finish('origin',job['id'],{'text':'ok'},'')
    thread.join(1)
    assert result[0][1]['worker_id']=='origin'
    assert broker.dispatch('s','p',SCHEMA,20,0) is None
    with on_device('origin'),pytest.raises(AIUnavailable):broker.dispatch('s','p',SCHEMA,20,0)
    assert not broker.jobs

def test_admin_resource_validation_and_command_delivery():
    import uuid
    with TestClient(app) as admin,TestClient(app) as client:
        login(admin,'admin')
        station=post(client,'/classroom/register',{'number':'resources-'+uuid.uuid4().hex[:8]}).json()
        client.headers['X-Workstation']=station['token']
        admin.patch('/api/classroom/stations/'+station['id'],json={'approved':True},headers=HEAD)
        post(client,'/management/agent/poll',{'metrics':{'cores':8,'ai':{'cpu_threads':8,'gpus':[],'stt_gpu_available':False}}})
        endpoint='/management/devices/'+station['id']+'/ai'
        assert post(admin,endpoint,{'mode':'server'}).status_code==422
        assert post(admin,endpoint,{'mode':'gpu','device':'Vulkan0'}).status_code==400
        assert post(admin,endpoint,{'mode':'cpu','stt_device':'gpu'}).status_code==400
        assert post(admin,endpoint,{'mode':'cpu','threads_auto':False,'threads':8,'stt_threads':2,'tts_threads':2}).status_code==400
        valid={'mode':'cpu','threads_auto':False,'threads':4,'stt_threads':2,'tts_threads':2}
        response=post(admin,endpoint,valid);assert response.status_code==200,response.text
        command=post(client,'/management/agent/poll').json()['commands'][0]
        assert command['payload']['threads']==4 and command['payload']['stt_threads']==2
        post(client,'/management/agent/poll',{'results':[{'id':command['id'],'ok':True}]})
        login(client,'student')
        assert post(client,endpoint,valid).status_code==403
        assert post(admin,'/ai/execution',{'execution':'workstations'}).status_code==410

def test_request_context_targets_authenticated_station(monkeypatch):
    import uuid
    from apps.api.app import ai_routes
    seen=[]
    # Existing status endpoint runs in FastAPI's threadpool: context must propagate.
    monkeypatch.setattr(ai_routes.ai,'status',lambda:seen.append(device_id.get()) or {'available':True})
    with TestClient(app) as admin,TestClient(app) as client:
        login(admin,'admin');login(client,'teacher')
        station=post(client,'/classroom/register',{'number':'context-'+uuid.uuid4().hex[:8]}).json()
        client.headers['X-Workstation']=station['token']
        admin.patch('/api/classroom/stations/'+station['id'],json={'approved':True},headers=HEAD)
        assert client.get('/api/ai/status').status_code==200
        assert seen[-1]==station['id']
        assert admin.get('/api/ai/status').status_code==200 and seen[-1] is None


@pytest.fixture(autouse=True)
def no_model_warmup(monkeypatch):
    from apps.api.app import startup_models
    async def idle():pass
    monkeypatch.setattr(startup_models,'warm_models',idle)
