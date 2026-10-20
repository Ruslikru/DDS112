"""Native PC polls its selected classroom; never opens an inference port on the LAN."""
import base64
import json
import threading
import urllib.request
from .engine import LocalEngine


class Worker:
    def __init__(self, server, token, data):
        self.server=server.rstrip('/')
        self.token=token
        self.engine=LocalEngine(data=data/'worker-ai')
        self.voice=None
        self.enabled=True
        self.closed=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path, body):
        req=urllib.request.Request(self.server+'/api/ai/workers'+path,json.dumps(body,ensure_ascii=False).encode('utf-8'),
            {'Content-Type':'application/json','X-Requested-With':'Training112','X-Workstation':self.token})
        with self.opener.open(req,timeout=8) as r:return json.load(r)

    def start(self):self.thread.start()

    def configure(self,mode,device='',**resources):
        self.engine.set_settings(mode=mode,device=device,**resources)
        self.enabled=True

    def run(self):
        while not self.closed.is_set():
            try:
                status=self.engine.status()
                job=self.request('/poll',{'available':self.enabled and status['available'],'mode':status['mode']}).get('job')
                if job:
                    try:
                        operation=job.get('operation')
                        if operation:
                            if not self.voice:raise RuntimeError('Голосовая модель запускается')
                            args=job['args']
                            if operation=='synthesize':
                                path,meta=self.voice.synthesize(str(args['text'])[:5000],args.get('gender','male'),args.get('group','live'),args.get('settings'))
                                value={'audio':base64.b64encode(path.read_bytes()).decode(),'meta':json.dumps(meta)}
                            elif operation=='transcribe':value={'meta':json.dumps(self.voice.transcribe(args['content']),ensure_ascii=False)}
                            else:raise ValueError('Неизвестная операция модели')
                        else:
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
