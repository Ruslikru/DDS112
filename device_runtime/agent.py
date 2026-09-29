"""Windows desktop agent. It accepts only bounded commands issued by the classroom admin."""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from .updates import validate_package


class Metrics:
    def __init__(self,data):
        self.data=data;self.previous=None
        self.gpu_sample=(0,[])
        self.cpu=os.environ.get('PROCESSOR_IDENTIFIER','Процессор')
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:self.cpu=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
        except OSError:pass

    def read(self):
        idle,kernel,user=wintypes.FILETIME(),wintypes.FILETIME(),wintypes.FILETIME()
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel),ctypes.byref(user))
        value=lambda t:(t.dwHighDateTime<<32)+t.dwLowDateTime
        sample=(value(idle),value(kernel)+value(user));cpu=None
        if self.previous:
            total=sample[1]-self.previous[1]
            if total>0:cpu=round(max(0,min(100,100*(1-(sample[0]-self.previous[0])/total))),1)
        self.previous=sample
        class Memory(ctypes.Structure):
            _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page','page_available','virtual','virtual_available','extended')]
        memory=Memory();memory.length=ctypes.sizeof(memory)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
        disk=shutil.disk_usage(self.data)
        if time.monotonic()-self.gpu_sample[0]>5:
            devices=[]
            executable=shutil.which('nvidia-smi')
            if executable:
                try:
                    result=subprocess.run([executable,'--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=2,creationflags=subprocess.CREATE_NO_WINDOW)
                    for line in result.stdout.splitlines():
                        name,load,used,total,temperature=[s.strip() for s in line.split(',')]
                        devices.append({'name':name,'load':float(load),'memory_used_mb':float(used),'memory_total_mb':float(total),'temperature':float(temperature)})
                except (OSError,ValueError,subprocess.TimeoutExpired):pass
            self.gpu_sample=(time.monotonic(),devices)
        return {'cpu_name':self.cpu,'cpu_percent':cpu,'cores':os.cpu_count(),'memory_percent':memory.load,
                'memory_total':memory.total,'memory_available':memory.available,'disk_free':disk.free,'disk_total':disk.total,'gpu_metrics':self.gpu_sample[1]}


class Desktop:
    def __init__(self,window,demo):self.window=window;self.demo=demo;self.rect=(0,0,1,1)

    def devtools(self,method,params):
        from System import Func,Object
        view=self.window.native.browser.webview
        task=view.Invoke(Func[Object](lambda:view.CoreWebView2.CallDevToolsProtocolMethodAsync(method,json.dumps(params))))
        if not task.Wait(5000):raise RuntimeError('Окно не ответило за 5 секунд')
        return json.loads(str(task.Result))

    def capture(self):
        if self.demo:
            size=self.window.evaluate_js('({width:innerWidth,height:innerHeight})')
            self.rect=(0,0,size['width'],size['height'])
            from System import Func,Object
            from System.IO import MemoryStream
            from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
            stream=MemoryStream()
            try:
                view=self.window.native.browser.webview
                task=view.Invoke(Func[Object](lambda:view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Jpeg,stream)))
                # Await completion before disposing the stream owned by the async capture.
                task.GetAwaiter().GetResult()
                return 'data:image/jpeg;base64,'+base64.b64encode(bytes(stream.ToArray())).decode()
            finally:stream.Dispose()
        import clr
        clr.AddReference('System.Drawing');clr.AddReference('System.Windows.Forms')
        from System.Drawing import Bitmap,Graphics,Size
        from System.Drawing.Imaging import ImageFormat
        from System.Windows.Forms import SystemInformation
        from System.IO import MemoryStream
        if self.demo:
            rect=wintypes.RECT();hwnd=int(self.window.native.Handle.ToInt64())
            ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd),ctypes.byref(rect))
            x,y,w,h=rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top
        else:
            area=SystemInformation.VirtualScreen;x,y,w,h=area.X,area.Y,area.Width,area.Height
        if not 0<w<20000 or not 0<h<20000:raise RuntimeError('Окно недоступно для просмотра')
        self.rect=(x,y,w,h)
        bitmap=Bitmap(w,h);graphics=Graphics.FromImage(bitmap);small=None;stream=MemoryStream()
        try:
            if self.demo:
                hdc=graphics.GetHdc()
                try:
                    if not ctypes.windll.user32.PrintWindow(wintypes.HWND(hwnd),wintypes.HDC(int(hdc.ToInt64())),2):raise RuntimeError('Не удалось получить изображение окна')
                finally:graphics.ReleaseHdc(hdc)
            else:graphics.CopyFromScreen(x,y,0,0,Size(w,h))
            small=Bitmap(bitmap,Size(min(w,1280),max(1,int(h*min(w,1280)/w))))
            small.Save(stream,ImageFormat.Jpeg)
            return 'data:image/jpeg;base64,'+base64.b64encode(bytes(stream.ToArray())).decode()
        finally:
            stream.Dispose()
            if small:small.Dispose()
            graphics.Dispose();bitmap.Dispose()

    def input(self,data):
        if time.time()-data.get('at',0)>5:return
        if self.demo:
            kind=data['kind'];x=data.get('x',0)*self.rect[2];y=data.get('y',0)*self.rect[3]
            if kind=='text':self.devtools('Input.insertText',{'text':data['text']})
            elif kind=='scroll':self.devtools('Input.dispatchMouseEvent',{'type':'mouseWheel','x':x,'y':y,'deltaX':0,'deltaY':-data['delta']})
            elif kind in ('click','doubleclick','rightclick'):
                button='right' if kind=='rightclick' else 'left'
                count=2 if kind=='doubleclick' else 1
                for event in ('mousePressed','mouseReleased'):self.devtools('Input.dispatchMouseEvent',{'type':event,'x':x,'y':y,'button':button,'clickCount':count})
            elif kind=='key':
                parts=data['key'].split('+');key=parts[-1]
                modifiers=sum({'Alt':1,'Ctrl':2,'Shift':8}.get(p,0) for p in parts[:-1])
                code={'Enter':13,'Tab':9,'Escape':27,'Backspace':8,'Delete':46,'ArrowLeft':37,'ArrowUp':38,'ArrowRight':39,'ArrowDown':40,'Home':36,'End':35,'PageUp':33,'PageDown':34}.get(key,ord(key.upper()) if len(key)==1 else 0)
                if not code:raise ValueError('Неизвестная клавиша')
                self.devtools('Input.dispatchKeyEvent',{'type':'rawKeyDown','key':key,'windowsVirtualKeyCode':code,'modifiers':modifiers})
                if key=='Enter' and not modifiers:self.devtools('Input.dispatchKeyEvent',{'type':'char','text':'\r','key':'Enter','windowsVirtualKeyCode':13})
                self.devtools('Input.dispatchKeyEvent',{'type':'keyUp','key':key,'windowsVirtualKeyCode':code,'modifiers':modifiers})
            return
        user=ctypes.windll.user32
        if self.demo:user.SetForegroundWindow(wintypes.HWND(int(self.window.native.Handle.ToInt64())))
        kind=data['kind'];x,y,w,h=self.rect
        if kind in ('click','doubleclick','rightclick','scroll'):
            user.SetCursorPos(round(x+data['x']*(w-1)),round(y+data['y']*(h-1)))
            if kind=='scroll':user.mouse_event(0x800,0,0,int(data['delta']),0)
            else:
                down,up=(8,16) if kind=='rightclick' else (2,4)
                for _ in range(2 if kind=='doubleclick' else 1):user.mouse_event(down,0,0,0,0);user.mouse_event(up,0,0,0,0)
        elif kind=='key':
            keys={'Enter':13,'Tab':9,'Escape':27,'Backspace':8,'Delete':46,'ArrowLeft':37,'ArrowUp':38,'ArrowRight':39,'ArrowDown':40,'Home':36,'End':35,'PageUp':33,'PageDown':34}
            value=data['key'];mods=[]
            parts=value.split('+')
            for p in parts[:-1]:
                if p not in ('Ctrl','Alt','Shift'):raise ValueError('Неизвестная клавиша')
                mods.append({'Ctrl':17,'Alt':18,'Shift':16}[p])
            key=keys.get(parts[-1]) or (ord(parts[-1].upper()) if len(parts[-1])==1 and parts[-1].isascii() else None)
            if key is None:raise ValueError('Неизвестная клавиша')
            for vk in mods:user.keybd_event(vk,0,0,0)
            user.keybd_event(key,0,0,0);user.keybd_event(key,0,2,0)
            for vk in reversed(mods):user.keybd_event(vk,0,2,0)
        elif kind=='text':
            class Keyboard(ctypes.Structure):_fields_=[('vk',wintypes.WORD),('scan',wintypes.WORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
            class Mouse(ctypes.Structure):_fields_=[('dx',wintypes.LONG),('dy',wintypes.LONG),('data',wintypes.DWORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
            class Union(ctypes.Union):_fields_=[('ki',Keyboard),('mi',Mouse)]
            class Input(ctypes.Structure):_fields_=[('type',wintypes.DWORD),('value',Union)]
            raw=data['text'].encode('utf-16-le')
            for offset in range(0,len(raw),2):
                code=int.from_bytes(raw[offset:offset+2],'little')
                for flags in (4,6):
                    event=Input(type=1,value=Union(ki=Keyboard(0,code,flags,0,0)))
                    if user.SendInput(1,ctypes.byref(event),ctypes.sizeof(event))!=1:raise RuntimeError('Windows отклонила ввод')


class Agent:
    def __init__(self,config,data,base_data,window,worker,version):
        self.config=config;self.data=data;self.base_data=base_data;self.window=window;self.worker=worker;self.version=version
        from local_ai.engine import engine
        self.engine=worker.engine if worker else engine
        self.closed=threading.Event();self.thread=threading.Thread(target=self.run,daemon=True)
        self.metrics=Metrics(data);self.desktop=Desktop(window,config.get('demo',False))
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));self.done={};self.results=[];self.close_after_ack=False;self.watching=False
        self.receipt=data/'update-result.json'
        if self.receipt.exists():
            result=json.loads(self.receipt.read_text('utf-8'))
            self.results.append({'id':result['id'],'ok':result['version']==version,'message':'Запущена версия '+version})
            if result['version']==version and getattr(sys,'frozen',False):
                (data/'active-install.json').write_text(json.dumps({'exe':sys.executable,'version':version}),'utf-8')

    def request(self,path,body=None):
        req=urllib.request.Request(self.config['server']+'/api/management'+path,
            json.dumps(body).encode() if body is not None else None,
            {'Content-Type':'application/json','X-Requested-With':'Training112','X-Workstation':self.config['token']})
        return self.opener.open(req,timeout=15)

    def start(self):self.thread.start()
    def stop(self):self.closed.set();self.thread.join(20)
    def close(self):self.window.confirm_close=False;self.window.destroy()

    def prepare_update(self,command):
        if not getattr(sys,'frozen',False):raise ValueError('Обновление доступно в собранном EXE')
        payload=command['payload'];pid=payload['package_id']
        root=self.data/'updates';root.mkdir(exist_ok=True)
        package=root/(pid+'.zip')
        with self.request('/packages/'+pid+'/download') as source,package.open('wb') as target:shutil.copyfileobj(source,target)
        with package.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
        if digest!=payload['sha256']:raise ValueError('Контрольная сумма загруженного пакета не совпадает')
        install=root/(pid+'-'+command['id'])
        validate_package(package,install)
        if not (install/'local_ai').exists():shutil.copytree(self.engine.root,install/'local_ai',ignore=shutil.ignore_patterns('data','logs','downloads'))
        self.receipt.write_text(json.dumps({'id':command['id'],'version':payload['version']}),'utf-8')
        launch={'pid':os.getpid(),'exe':str(install/'Dispetcher112.exe'),'data':str(self.base_data),'profile':str(self.data),'old':sys.executable}
        (install/'launch.json').write_text(json.dumps(launch),'utf-8')
        script=install/'launch.ps1'
        script.write_text("$ErrorActionPreference='Stop'\n$c=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'launch.json') -Raw | ConvertFrom-Json\nWait-Process -Id $c.pid -Timeout 90 -ErrorAction SilentlyContinue\nif(Get-Process -Id $c.pid -ErrorAction SilentlyContinue){throw 'Приложение не завершилось'}\n$argsLine='--data-dir \"'+$c.data+'\" --resume-profile \"'+$c.profile+'\"'\ntry { Start-Process -WindowStyle Hidden -FilePath $c.exe -ArgumentList $argsLine } catch { Start-Process -WindowStyle Hidden -FilePath $c.old -ArgumentList $argsLine; $_ | Out-File (Join-Path $PSScriptRoot 'update-error.txt') }\n",'utf-8')
        subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],creationflags=subprocess.CREATE_NO_WINDOW,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.close_after_ack=True
        return {'status':'prepared','message':'Пакет проверен. Приложение перезапускается.'}

    def execute(self,command):
        kind=command['kind'];payload=command['payload']
        if kind=='logout':
            self.window.evaluate_js("void fetch('/api/logout',{method:'POST',headers:{'X-Requested-With':'Training112','X-Workstation':localStorage.getItem('training112:station-token')||''}}).finally(()=>location.reload())")
        elif kind in ('close','remove'):self.close_after_ack=True
        elif kind=='ai':
            if self.worker:self.worker.configure(payload['mode'],payload.get('device',''))
            else:self.engine.set_settings(mode=payload['mode'],device=payload.get('device',''))
        elif kind=='update':return self.prepare_update(command)
        return {'message':'Выполнено'}

    def run(self):
        error='';latency=None;sample_at=0;metrics={};control=False
        while not self.closed.is_set():
            try:
                if time.monotonic()-sample_at>2:
                    metrics=self.metrics.read();ai=self.engine.status();sample_at=time.monotonic()
                ai['compute_mode']='server' if self.worker and not self.worker.enabled else ai['mode']
                metrics.update(version=self.version,ai=ai,network_ms=latency,desktop_error=error,
                    desktop_scope='window' if self.config.get('demo') else 'desktop',database='Доступна' if self.config['mode']=='server' and (self.data/'dispetcher.db').exists() else None)
                frame=''
                if self.watching:
                    try:frame=self.desktop.capture();error=''
                    except Exception as e:error=str(e)[:300]
                sent=self.results[:];started=time.monotonic()
                with self.request('/agent/poll',{'metrics':metrics,'frame':frame,'results':sent}) as response:data=json.load(response)
                latency=round((time.monotonic()-started)*1000)
                self.results=self.results[len(sent):]
                if sent and self.receipt.exists() and any(r.get('status')!='prepared' and r['id']==json.loads(self.receipt.read_text('utf-8'))['id'] for r in sent):self.receipt.unlink()
                if data.get('revoked') or self.close_after_ack and sent:self.close();return
                self.watching=data.get('desktop',False);control=data.get('control',False)
                for entry in data.get('inputs',[]):
                    try:self.desktop.input(entry)
                    except Exception as e:error=str(e)[:300]
                for command in data.get('commands',[]):
                    if command['id'] not in self.done:
                        try:self.done[command['id']]={'id':command['id'],'ok':True,**self.execute(command)}
                        except Exception as e:self.done[command['id']]={'id':command['id'],'ok':False,'message':str(e)[:1000]}
                    self.results.append(self.done[command['id']])
            except Exception:pass
            self.closed.wait(.04 if control else .35 if self.watching else .4)
