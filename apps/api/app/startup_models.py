"""Warm persistent inference workers and supervise readiness without blocking the UI."""
import asyncio
import os
import time
import threading
from .diagnostics import event

_lock=threading.Lock()
_rows={}
_cpu=None

class CpuMeter:
    def __init__(self,read=None):self.read=read or self.windows_times;self.previous=None
    @staticmethod
    def windows_times():
        if os.name!='nt':return None
        import ctypes
        idle,kernel,user=(ctypes.c_ulonglong() for _ in range(3))
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel),ctypes.byref(user)):return None
        return idle.value,kernel.value+user.value
    def sample(self):
        value=self.read()
        if value is None:return None
        old=self.previous;self.previous=value
        if old is None or value[1]<=old[1]:return None
        return round(max(0,min(100,100*(1-(value[0]-old[0])/(value[1]-old[1])))),1)

def workers():
    from local_ai.engine import engine
    from .voice import runtime
    return engine,runtime

def alive(worker):return worker.process is not None and worker.process.poll() is None

def signatures(items):
    cards,speech=items;cfg=speech.settings()['live'];text=cards.config()
    return {'cards':(text['model'],text['mode'],text['threads']),
            'speech':(cfg['stt_threads'],cfg['tts_threads'],cfg['stt_device'])}

def ready(key,worker,signature):
    row=_rows.get(key,{})
    return alive(worker) and row.get('state')=='ready' and row.get('pid')==worker.process.pid and row.get('signature')==signature

def status():
    items=workers();sigs=signatures(items);cfg=items[1].settings()['live'];result={}
    with _lock:
        for key,worker in zip(('cards','speech'),items):
            row=_rows.get(key,{})
            state='ready' if ready(key,worker,sigs[key]) else ('warming' if row.get('state')=='warming' else 'error' if row.get('state')=='error' else 'cold')
            if key=='cards':
                result[key]={'state':state,'threads':sigs[key][-1],'mode':sigs[key][1],'model':sigs[key][0]}
            else:
                # GigaAM and Piper share a process; its warm-up exercises both models.
                result['stt']={'state':state,'threads':cfg['stt_threads'],'mode':cfg['stt_device'],'model':'GigaAM v3'}
                result['tts']={'state':state,'threads':cfg['tts_threads'],'mode':'cpu','model':'Piper'}
        return {'models':result,'cpu_percent':_cpu,'cpu_scope':'machine','sample_seconds':2}

async def warm_models():
    global _cpu
    items=workers();meter=CpuMeter();meter.sample()
    schema={'type':'object','properties':{'ready':{'type':'boolean','enum':[True]}},'required':['ready'],'additionalProperties':False}
    async def warm(key,worker,signature):
        with _lock:_rows[key]={'state':'warming','signature':signature}
        try:
            if key=='speech':await asyncio.to_thread(worker.warm)
            else:await asyncio.to_thread(worker.complete,'Return JSON only.','Return ready=true.',schema,tokens=16)
            with _lock:_rows[key]={'state':'ready','signature':signature,'pid':worker.process.pid}
            event('model_warm_ready',model=key)
        except Exception as error:
            with _lock:_rows[key]={'state':'error','signature':signature,'retry_at':time.monotonic()+30}
            event('model_warm_failed',model=key,error=str(error))
    tasks={}
    try:
        while True:
            sigs=signatures(items)
            for key,worker in zip(('cards','speech'),items):
                if key in tasks and not tasks[key].done():continue
                with _lock:needs=not ready(key,worker,sigs[key]) and time.monotonic()>=_rows.get(key,{}).get('retry_at',0)
                # Do not steal the worker from an in-flight conversation.
                busy=worker.lock.locked() if key!='speech' else False
                if needs and not busy:tasks[key]=asyncio.create_task(warm(key,worker,sigs[key]))
            with _lock:_cpu=meter.sample()
            await asyncio.sleep(2)
    finally:
        for task in tasks.values():task.cancel()
        await asyncio.gather(*tasks.values(),return_exceptions=True)
