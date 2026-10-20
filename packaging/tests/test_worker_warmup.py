import threading
import time
from types import SimpleNamespace

from local_ai.worker import Worker


class FakeEngine:
    def __init__(self, **kwargs):
        self.process=None
        self.lock=threading.Lock()
        self.calls=[]
        self.cfg={'model':'qwen','mode':'cpu','device':'','threads':4}

    def config(self):return dict(self.cfg)
    def complete(self,*args,**kwargs):
        self.calls.append(kwargs)
        self.process=SimpleNamespace(pid=17,poll=lambda:None)
        return {'ready':True},{}
    def stop(self):self.process=None


class FakeSpeech:
    def __init__(self):
        self.process=None
        self.calls=0
        self.cfg={'stt_device':'cpu','stt_threads':2,'tts_threads':2}
    def settings(self):return {'live':dict(self.cfg)}
    def warm(self):
        self.calls+=1
        self.process=SimpleNamespace(pid=29,poll=lambda:None)
    def stop(self):self.process=None


def worker(tmp_path,monkeypatch):
    monkeypatch.setattr('local_ai.worker.LocalEngine',FakeEngine)
    return Worker('http://localhost:8765','private-token',tmp_path)


def test_real_warm_calls_and_invalidation(tmp_path,monkeypatch):
    pc=worker(tmp_path,monkeypatch);pc.voice=FakeSpeech()
    signatures=pc.model_signatures()
    for key,target in [('cards',pc.engine),('speech',pc.voice)]:
        assert pc.model_state(key)=='cold'
        pc.warm_model(key,target,signatures[key])
        assert pc.model_state(key)=='ready'
    assert pc.engine.calls==[{'tokens':16,'priority':20}]
    assert pc.voice.calls==1
    pc.engine.cfg['threads']=6
    pc.voice.cfg['stt_device']='gpu'
    assert pc.model_state('cards')==pc.model_state('speech')=='cold'
    pc.voice.cfg['stt_device']='cpu'
    pc.voice.process=SimpleNamespace(pid=30,poll=lambda:None)
    assert pc.model_state('speech')=='cold'


def test_failure_never_reports_ready_and_retries_are_delayed(tmp_path,monkeypatch):
    pc=worker(tmp_path,monkeypatch)
    def fail(*args,**kwargs):raise RuntimeError('missing model')
    pc.engine.complete=fail
    pc.warm_model('cards',pc.engine,pc.model_signatures()['cards'])
    assert pc.model_state('cards')=='error'
    assert pc.warm_rows['cards']['retry_at']>time.monotonic()+29


def test_supervisor_waits_for_voice_without_blocking_poll_thread(tmp_path,monkeypatch):
    pc=worker(tmp_path,monkeypatch)
    poll_alive=threading.Event()
    def poll():
        poll_alive.set();pc.closed.wait(5)
    pc.thread=threading.Thread(target=poll,daemon=True)
    pc.start()
    try:
        assert poll_alive.wait(1)
        deadline=time.monotonic()+1
        while pc.model_state('cards')!='ready' and time.monotonic()<deadline:time.sleep(.01)
        assert pc.model_state('cards')=='ready'
        pc.voice=FakeSpeech()
        deadline=time.monotonic()+3
        while pc.model_state('speech')!='ready' and time.monotonic()<deadline:time.sleep(.01)
        assert pc.model_state('speech')=='ready'
        assert pc.thread.is_alive()
    finally:pc.stop()
    assert not pc.warm_thread.is_alive() and not pc.thread.is_alive()


def test_shutdown_during_warmup_does_not_leave_process_running(tmp_path,monkeypatch):
    pc=worker(tmp_path,monkeypatch)
    signature=pc.model_signatures()['cards']
    complete=pc.engine.complete
    def close_then_complete(*args,**kwargs):
        pc.closed.set()
        return complete(*args,**kwargs)
    pc.engine.complete=close_then_complete
    pc.warm_model('cards',pc.engine,signature)
    assert pc.engine.process is None
    assert pc.model_state('cards')!='ready'
