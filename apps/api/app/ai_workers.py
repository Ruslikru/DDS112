"""Class-scoped inference jobs: only explicitly authorized native PCs can claim them."""
import secrets
import threading
import time
from pathlib import Path
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from local_ai.engine import engine, DEFAULT_MODEL
from . import main as m
from .classroom import station
from .classroom_models import Workstation


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
            if wid not in self.config()['worker_ids'] or not available:
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
            if wid not in self.config()['worker_ids']:return False
            # Current app schemas are objects of bounded strings/enums. Reject anything else.
            schema=job['payload']['schema']
            props=schema.get('properties',{})
            valid=isinstance(value,dict) and set(schema.get('required',[]))<=set(value) and set(value)<=set(props)
            if valid:
                for key,text in value.items():
                    rule=props[key]
                    if not isinstance(text,str) or len(text)>rule.get('maxLength',12000) or ('enum' in rule and text not in rule['enum']):
                        valid=False;break
            job['value']=value if valid and not error else None
            job['event'].set()
            return True

    def dispatch(self, system, prompt, schema, tokens, temperature):
        started=time.monotonic()
        with self.lock:
            busy={j['worker'] for j in self.jobs.values()}
            allowed=self.config()['worker_ids']
            wid=next((wid for wid,w in self.workers.items() if wid in allowed and wid not in busy and w['available'] and started-w['seen']<5),None)
            if wid is None:return None
            jid=secrets.token_hex(20)
            job={'id':jid,'worker':wid,'event':threading.Event(),'sent':False,'value':None,
                 'payload':{'system':system,'prompt':prompt,'schema':schema,'tokens':tokens,'temperature':temperature,
                            'model':self.config().get('model',DEFAULT_MODEL)}}
            self.jobs[jid]=job
        try:
            if not job['event'].wait(self.timeout) or job['value'] is None:
                return None
            return job['value'],{'model':Path(job['payload']['model']).stem,'mode':self.workers.get(wid,{}).get('mode','cpu'),'execution':'workstation',
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
    value:dict[str,str]=Field(default_factory=dict,max_length=30)
    error:str=Field(default='',max_length=500)

@router.post('/poll')
def poll(data:Poll,request:Request,db=Depends(m.getdb)):
    w=station(request,db)
    return {'job':broker.poll(w.id,data.available,data.mode)}

@router.post('/{jid}/result')
def result(jid:str,data:Result,request:Request,db=Depends(m.getdb)):
    w=station(request,db)
    if sum(len(x) for x in data.value.values())>50000:m.fail('Слишком большой ответ')
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
