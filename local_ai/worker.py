"""Native PC polls its selected classroom; never opens an inference port on the LAN."""
import json
import threading
import urllib.request
from .engine import LocalEngine


class Worker:
    def __init__(self, server, token, data):
        self.server=server.rstrip('/')
        self.token=token
        self.engine=LocalEngine(data=data/'worker-ai')
        policy=self.engine.data/'worker-policy.json'
        self.enabled=not policy.exists() or json.loads(policy.read_text('utf-8')).get('mode')!='server'
        self.closed=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path, body):
        req=urllib.request.Request(self.server+'/api/ai/workers'+path,json.dumps(body,ensure_ascii=False).encode('utf-8'),
            {'Content-Type':'application/json','X-Requested-With':'Training112','X-Workstation':self.token})
        with self.opener.open(req,timeout=8) as r:return json.load(r)

    def start(self):self.thread.start()

    def configure(self,mode,device=''):
        if mode!='server':self.engine.set_settings(mode=mode,device=device)
        else:self.engine.stop()
        self.enabled=mode!='server'
        self.engine.data.mkdir(parents=True,exist_ok=True)
        (self.engine.data/'worker-policy.json').write_text(json.dumps({'mode':mode}),'utf-8')

    def run(self):
        while not self.closed.is_set():
            try:
                status=self.engine.status()
                job=self.request('/poll',{'available':self.enabled and status['available'],'mode':status['mode']}).get('job')
                if job:
                    try:
                        if job.get('model') and self.engine.config()['model']!=job['model']:
                            self.engine.set_settings(model=job['model'])
                        value,_=self.engine.complete(job['system'],job['prompt'],job['schema'],job['tokens'],job['temperature'])
                        result={'value':value}
                    except Exception as e:result={'error':str(e)[:500]}
                    self.request('/'+job['id']+'/result',result)
            except Exception:
                # A server can restart or revoke admission at any moment.
                if self.closed.wait(2):break
            self.closed.wait(.6)

    def stop(self):
        self.closed.set()
        self.engine.stop()
        self.thread.join(10)
