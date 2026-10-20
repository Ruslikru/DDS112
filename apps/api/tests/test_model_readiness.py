import asyncio
import pytest
import threading
from types import SimpleNamespace
from test_flows import app,TestClient,login
from apps.api.app import startup_models as models
supervise=models.warm_models


@pytest.fixture(autouse=True)
def do_not_start_models_in_api_tests(monkeypatch):
    async def idle():pass
    monkeypatch.setattr(models,'warm_models',idle)
    monkeypatch.setattr(models,'_rows',{})


def test_cpu_measures_interval_not_total_time():
    values=iter([(20,100),(40,200),(40,200),(1000,300)])
    meter=models.CpuMeter(lambda:next(values))
    assert meter.sample() is None
    assert meter.sample()==80
    assert meter.sample() is None
    assert meter.sample()==0


def test_authenticated_student_sees_lightweight_status():
    with TestClient(app) as client:
        assert client.get('/api/voice/call-status').status_code==401
        login(client,'student')
        response=client.get('/api/voice/call-status')
        assert response.status_code==200
        data=response.json()
        assert data['cpu_scope']=='machine'
        assert set(data['models'])=={'cards','stt','tts'}
        assert data['models']['cards']['threads']>=2
        assert data['models']['stt']['threads']==2
        assert data['models']['tts']['state']=='cold'


def test_supervisor_warms_every_worker_and_recovers_after_exit(monkeypatch):
    class Worker:
        def __init__(self):self.process=None;self.lock=threading.Lock();self.calls=0
        def config(self):return {'model':'test','mode':'cpu','threads':4}
        def load(self):
            self.calls+=1;self.process=SimpleNamespace(pid=self.calls,poll=lambda:None)
        def complete(self,*a,**kw):self.load();return {'ready':True},{}
        def warm(self):self.load()
        def settings(self):return {'live':{'dialogue_threads':4,'stt_threads':2,'tts_threads':2,'stt_device':'cpu'}}
    workers=tuple(Worker() for _ in range(2))
    monkeypatch.setattr(models,'workers',lambda:workers)
    monkeypatch.setattr(models,'_rows',{})
    async def run():
        task=asyncio.create_task(supervise())
        try:
            for _ in range(100):
                if all(x.calls for x in workers):break
                await asyncio.sleep(.02)
            assert all(x.calls==1 for x in workers)
            # Allow the completion tasks to publish readiness.
            await asyncio.sleep(.05)
            assert models.status()['models']['tts']['state']=='ready'
            workers[1].process=None
            assert models.status()['models']['stt']['state']=='cold'
            for _ in range(150):
                if workers[1].calls==2:break
                await asyncio.sleep(.02)
            assert workers[1].calls==2
            await asyncio.sleep(.05)
            assert models.status()['models']['stt']['state']=='ready'
        finally:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
    asyncio.run(run())
