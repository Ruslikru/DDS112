"""Background verified, resumable media cache for an enrolled workstation."""
import base64
import hashlib
import json
import threading
import urllib.request
from pathlib import Path

class VoiceSync:
    def __init__(self,config,data):
        self.config=config;self.root=Path(data)/'synced-voice';self.root.mkdir(exist_ok=True)
        self.stop_event=threading.Event();self.status={'ready':0,'total':0,'error':''}
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def request(self,path,headers=None):
        return urllib.request.urlopen(urllib.request.Request(self.config['server']+path,headers={'X-Workstation':self.config['token'],**(headers or {})}),timeout=30)
    def sync(self):
        with self.request('/api/voice/manifest') as response:manifest=json.load(response)
        self.status={'ready':0,'total':len(manifest['files']),'error':''}
        for f in manifest['files']:
            if self.stop_event.is_set():return
            key=f['sha256']
            if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ValueError('Некорректный хеш записи')
            target=self.root/(key+'.wav');part=self.root/(key+'.part')
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==key:self.status['ready']+=1;continue
            offset=part.stat().st_size if part.exists() else 0
            if offset>=f['size']:part.unlink();offset=0
            with self.request('/api/voice/files/'+key,{'Range':f'bytes={offset}-'} if offset else {}) as response:
                with part.open('ab' if offset and response.status==206 else 'wb') as out:
                    while chunk:=response.read(256*1024):
                        out.write(chunk)
                        if self.stop_event.is_set():return
            if part.stat().st_size!=f['size'] or hashlib.sha256(part.read_bytes()).hexdigest()!=key:
                part.unlink();raise ValueError('Не совпала контрольная сумма звука. Повторим загрузку.')
            part.replace(target);self.status['ready']+=1
        temp=self.root/'manifest.tmp';temp.write_text(json.dumps(manifest),encoding='utf-8');temp.replace(self.root/'manifest.json')
    def run(self):
        while not self.stop_event.is_set():
            try:self.sync()
            except Exception as e:self.status['error']=str(e)
            self.stop_event.wait(30)
    def audio(self,key):
        if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):return None
        file=self.root/(key+'.wav')
        if not file.exists():return None
        raw=file.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=key:return None
        return 'data:audio/wav;base64,'+base64.b64encode(raw).decode()
    def stop(self):self.stop_event.set()
