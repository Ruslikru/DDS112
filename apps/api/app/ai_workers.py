"""Class-scoped inference jobs: only explicitly authorized native PCs can claim them."""
import secrets
import json
from typing import Any
import threading
import time
from pathlib import Path
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from local_ai.engine import engine, DEFAULT_MODEL
from . import main as m
from .classroom import station
from .classroom_models import Workstation


def valid_result(value,schema,depth=0):
    if depth>12:return False
    if 'enum' in schema and value not in schema['enum']:return False
    kind=schema.get('type')
    if kind=='object':
        if not isinstance(value,dict):return False
        props=schema.get('properties',{})
        if not set(schema.get('required',[]))<=set(value):return False
        if schema.get('additionalProperties',False) is False and not set(value)<=set(props):return False
        return all(valid_result(v,props.get(k,{}),depth+1) for k,v in value.items())
    if kind=='array':return isinstance(value,list) and schema.get('minItems',0)<=len(value)<=schema.get('maxItems',500) and all(valid_result(v,schema.get('items',{}),depth+1) for v in value)
    if kind=='string':return isinstance(value,str) and schema.get('minLength',0)<=len(value)<=schema.get('maxLength',12000)
    if kind=='boolean':return type(value) is bool
    if kind in ('integer','number'):return type(value) in ((int,) if kind=='integer' else (int,float)) and schema.get('minimum',float('-inf'))<=value<=schema.get('maximum',float('inf'))
    if kind=='null':return value is None
    return False


class Broker:
    def __init__(self, config, timeout=135):
        self.config=config
        self.timeout=timeout
        self.lock=threading.RLock()
        self.workers={}
        self.jobs={}

    def poll(self, wid, available, mode='cpu'):
        with self.lock:
            self.workers[wid]={'seen':time.monotonic(),'available':available,'mode':mode}
            if not available:
                return None
            for job in self.jobs.values():
                if job['worker']==wid and not job['sent']:
                    job['sent']=True
                    return {'id':job['id'],**job['payload']}
        return None

    def finish(self, wid, jid, value, error):
        with self.lock:
            job=self.jobs.get(jid)
            if not job or job['worker']!=wid or not job['sent'] or job['event'].is_set():return False
            valid=valid_result(value,job['payload']['schema'])
            job['value']=value if valid and not error else None
            job['event'].set()
            return True

    def dispatch(self, system, prompt, schema, tokens, temperature):
        return self.submit({'system':system,'prompt':prompt,'schema':schema,'tokens':tokens,'temperature':temperature,'model':self.config().get('model',DEFAULT_MODEL)})

    def submit(self,payload):
        from local_ai.context import device_id
        from local_ai.engine import AIUnavailable
        wid=device_id.get()
        if not wid:return None
        started=time.monotonic()
        with self.lock:
            worker=self.workers.get(wid,{})
            busy=any(j['worker']==wid for j in self.jobs.values())
            if not busy and (not worker.get('available') or started-worker.get('seen',0)>8):
                raise AIUnavailable('Локальная модель рабочего места пока недоступна. Запрос сохранён для повторной проверки.')
            jid=secrets.token_hex(20)
            job={'id':jid,'worker':wid,'event':threading.Event(),'sent':False,'value':None,'payload':payload}
            self.jobs[jid]=job
        try:
            if not job['event'].wait(self.timeout) or job['value'] is None:
                raise AIUnavailable('Рабочее место не завершило локальное вычисление')
            return job['value'],{'model':Path(job['payload'].get('model','speech')).stem,'mode':self.workers.get(wid,{}).get('mode','cpu'),'execution':'workstation',
                                  'worker_id':wid,'seconds':round(time.monotonic()-started,3)}
        finally:
            with self.lock:self.jobs.pop(jid,None)

    def stop(self):
        with self.lock:
            for job in self.jobs.values():job['event'].set()
            self.workers.clear()


broker=Broker(engine.config)
router=APIRouter(prefix='/api/ai/workers')

class Poll(BaseModel):
    available:bool=False
    mode:str=Field(default='cpu',pattern='^(cpu|gpu)$')

class Result(BaseModel):
    value:dict[str,Any]=Field(default_factory=dict,max_length=30)
    error:str=Field(default='',max_length=500)

@router.post('/poll')
def poll(data:Poll,request:Request,db=Depends(m.getdb)):
    w=station(request,db)
    return {'job':broker.poll(w.id,data.available,data.mode)}

@router.post('/{jid}/result')
def result(jid:str,data:Result,request:Request,db=Depends(m.getdb)):
    w=station(request,db)
    if len(json.dumps(data.value,ensure_ascii=False))>16000000:m.fail('Слишком большой ответ')
    if not broker.finish(w.id,jid,data.value,data.error):m.fail('Задание больше недоступно',409)
    return {'ok':True}

@router.get('')
def workers(u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u)
    allowed=engine.config()['worker_ids']
    with broker.lock:
        busy={j['worker'] for j in broker.jobs.values()}
        return [{'id':w.id,'number':w.number,'enabled':w.id in allowed,'approved':w.approved and not w.blocked,
                 'online':time.monotonic()-broker.workers.get(w.id,{}).get('seen',-100)<5 or w.id in busy,
                 'available':broker.workers.get(w.id,{}).get('available',False),'busy':w.id in busy}
                for w in db.scalars(m.select(Workstation).order_by(Workstation.number))]
