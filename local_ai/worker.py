"""Native PC polls its selected classroom; never opens an inference port on the LAN."""
import base64
import json
import threading
import time
import logging
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
        self.warm_thread=threading.Thread(target=self.supervise_models,daemon=True)
        self.warm_rows={}
        self.warm_lock=threading.Lock()
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path, body):
        req=urllib.request.Request(self.server+'/api/ai/workers'+path,json.dumps(body,ensure_ascii=False).encode('utf-8'),
            {'Content-Type':'application/json','X-Requested-With':'Training112','X-Workstation':self.token})
        with self.opener.open(req,timeout=8) as r:return json.load(r)

    def start(self):
        self.thread.start()
        self.warm_thread.start()

    def model_signatures(self):
        cfg=self.engine.config()
        result={'cards':(cfg['model'],cfg['mode'],cfg.get('device',''),cfg['threads'])}
        if self.voice:
            speech=self.voice.settings()['live']
            result['speech']=(speech['stt_device'],speech['stt_threads'],speech['tts_threads'])
        return result

    def model_state(self,key,signature=None):
        signature=signature or self.model_signatures().get(key)
        worker=self.engine if key=='cards' else self.voice
        with self.warm_lock:row=dict(self.warm_rows.get(key,{}))
        process=worker.process if worker else None
        if row.get('signature')!=signature:return 'cold'
        if row.get('state')=='ready':
            return 'ready' if process and process.poll() is None and process.pid==row.get('pid') else 'cold'
        return row.get('state','cold')

    def warm_model(self,key,worker,signature):
        try:
            if self.closed.is_set():return
            if key=='speech':worker.warm()
            else:
                schema={'type':'object','properties':{'ready':{'type':'boolean','enum':[True]}},'required':['ready'],'additionalProperties':False}
                worker.complete('Return JSON only.','Return ready=true.',schema,tokens=16,priority=20)
            process=worker.process
            if not process or process.poll() is not None:raise RuntimeError('Процесс модели остановился при прогреве')
            row={'state':'ready','signature':signature,'pid':process.pid}
        except Exception as error:
            logging.getLogger(__name__).warning('Local model warm-up failed (%s): %s',key,error)
            row={'state':'error','signature':signature,'retry_at':time.monotonic()+30}
        finally:
            if self.closed.is_set():worker.stop()
        if not self.closed.is_set():
            with self.warm_lock:self.warm_rows[key]=row

    def supervise_models(self):
        # Polling and microphone requests stay responsive while weights load.
        tasks={}
        while not self.closed.is_set():
            try:
                for key,signature in self.model_signatures().items():
                    if not self.enabled or (key in tasks and tasks[key].is_alive()):continue
                    with self.warm_lock:row=dict(self.warm_rows.get(key,{}))
                    if self.model_state(key,signature)=='ready':continue
                    if row.get('signature')==signature and time.monotonic()<row.get('retry_at',0):continue
                    worker=self.engine if key=='cards' else self.voice
                    if key=='cards' and worker.lock.locked():continue
                    with self.warm_lock:self.warm_rows[key]={'state':'warming','signature':signature}
                    tasks[key]=threading.Thread(target=self.warm_model,args=(key,worker,signature),daemon=True)
                    tasks[key].start()
            except Exception:
                logging.getLogger(__name__).exception('Local model supervisor failed')
            self.closed.wait(2)
        for task in tasks.values():task.join(1)

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
        if self.warm_thread.is_alive():self.warm_thread.join(3)
        self.engine.stop()
        if self.thread.is_alive():self.thread.join(10)
