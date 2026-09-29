"""Offline Windows launcher. Program files are immutable; state lives in LocalAppData."""
import argparse
import ctypes
import hashlib
import http.cookiejar
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import sys
import threading
import time
import urllib.request

APP_ID = 'Dispetcher112.Desktop'
VERSION = '0.8.20'
RESOURCE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(RESOURCE_ROOT))


def configure(data):
    data.mkdir(parents=True, exist_ok=True)
    (data / 'logs').mkdir(exist_ok=True)
    # Never read the developer .env or inherit a database connection on another PC.
    os.environ['APP_RESOURCE_ROOT'] = str(RESOURCE_ROOT)
    os.environ['LOCAL_AI_DIR'] = str((Path(sys.executable).parent if getattr(sys, 'frozen', False) else RESOURCE_ROOT) / 'local_ai')
    os.environ['DATA_DIR'] = str(data)
    os.environ['DATABASE_URL'] = 'sqlite:///' + (data / 'dispetcher.db').as_posix()
    os.environ['SEED_DEMO'] = 'true'
    stream_logger=logging.getLogger('training112.launcher');stream_logger.setLevel(logging.INFO);stream_logger.propagate=False
    stream_logger.addHandler(RotatingFileHandler(data/'logs'/'launcher.log',maxBytes=5_000_000,backupCount=2,encoding='utf-8'))
    class LogStream:
        def write(self,text):
            stream_logger.disabled=False
            if text.strip(): stream_logger.info(text.rstrip())
            return len(text)
        def flush(self):
            for handler in stream_logger.handlers: handler.flush()
        def isatty(self): return False
        encoding='utf-8'
    log = LogStream()
    if sys.stdout is None: sys.stdout = log
    if sys.stderr is None: sys.stderr = log
    logging.basicConfig(handlers=[RotatingFileHandler(data/'logs'/'server.log',maxBytes=5_000_000,backupCount=3,encoding='utf-8')], level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    return log


def initialized(data):
    file = data / 'dispetcher.db'
    if not file.exists(): return False
    try:
        with sqlite3.connect(file.as_uri() + '?mode=ro', uri=True) as db:
            return db.execute('SELECT count(*) FROM users').fetchone()[0] > 0
    except sqlite3.OperationalError as error:
        if 'no such table' in str(error): return False
        raise


def backup(data):
    source = data / 'dispetcher.db'
    if not source.exists(): return
    folder = data / 'backups' / time.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(folder / 'dispetcher.db') as dst:
        src.backup(dst)
    if (data / 'media').exists(): shutil.copytree(data / 'media', folder / 'media', dirs_exist_ok=True)


def get_json(url):
    with urllib.request.urlopen(url, timeout=1) as response:
        return json.load(response)


class Server:
    def __init__(self, data):
        self.data = data
        self.server = None
        self.error = None
        self.stop_requested = False
        self.discovery = None
        self.thread = None
        self.token = secrets.token_hex(16)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # OS selects a vacant port; keep the bound socket until uvicorn takes it.
        self.sock.bind(('0.0.0.0', 8765) if os.getenv('CLASSROOM_SERVER')=='1' else ('127.0.0.1', 0))
        self.url = 'http://127.0.0.1:' + str(self.sock.getsockname()[1])

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            backup(self.data)
            import uvicorn
            from fastapi.routing import APIRoute
            from apps.api.app.main import app
            def health():
                from apps.api.app.server_identity import identity
                return {'app': APP_ID, 'token': self.token, 'version': VERSION,
                        'setup_policy': 'confirm-name-each-start', **identity()}
            app.router.routes.insert(0, APIRoute('/desktop-health', health, methods=['GET']))
            config = uvicorn.Config(app, host='127.0.0.1', log_config=None, access_log=False,
                                    loop='asyncio', http='h11', ws='none', timeout_graceful_shutdown=10)
            self.server = uvicorn.Server(config)
            self.server.should_exit = self.stop_requested
            if os.getenv('CLASSROOM_SERVER') == '1':
                from lan_discovery import DiscoveryServer
                try:
                    self.discovery = DiscoveryServer(self.sock.getsockname()[1])
                    self.discovery.start()
                except OSError:
                    logging.exception('LAN discovery could not start')
            self.server.run(sockets=[self.sock])
        except BaseException as error:
            self.error = str(error)
            logging.exception('Desktop server failed')
        finally:
            if self.discovery: self.discovery.stop()
            self.sock.close()

    def ready(self):
        try: return get_json(self.url + '/desktop-health').get('token') == self.token
        except Exception: return False

    def stop(self):
        self.stop_requested = True
        if self.server: self.server.should_exit = True


def single_instance(data):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    name = 'Local\\' + APP_ID + '.' + hashlib.sha256(str(data).lower().encode()).hexdigest()[:20]
    handle = kernel.CreateMutexW(None, False, name)
    if not handle: raise ctypes.WinError(ctypes.get_last_error())
    exists = ctypes.get_last_error() == 183
    return handle, exists


def self_test(data):
    """Exercise the packaged runtime on an isolated empty directory."""
    if (data / 'dispetcher.db').exists(): raise RuntimeError('Self-test requires an empty data directory')
    os.environ['DEMO_PASSWORD'] = secrets.token_urlsafe(20)
    server = Server(data)
    server.start()
    report = {'version': VERSION, 'frozen': bool(getattr(sys, 'frozen', False)), 'ok': False}
    try:
        deadline = time.monotonic() + 90
        while not server.ready():
            if server.error: raise RuntimeError(server.error)
            if time.monotonic() > deadline: raise TimeoutError('Startup timeout')
            time.sleep(.2)
        if os.getenv('CLASSROOM_SERVER') == '1':
            from lan_discovery import discover
            detected = discover(timeout=.4, targets=['127.0.0.1'])
            assert any(item['url'] == server.url for item in detected), detected
            report['lan_discovery'] = True
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def request(path, body=None):
            req = urllib.request.Request(server.url + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'Content-Type':'application/json','X-Requested-With':'Training112'})
            with client.open(req, timeout=30) as response: return response.read()
        def request_when_ai_idle(path, body):
            deadline=time.monotonic()+120
            while True:
                try:return request(path,body)
                except urllib.error.HTTPError as error:
                    detail=error.read().decode('utf-8','replace')
                    if error.code!=400 or 'Нейросеть занята' not in detail or time.monotonic()>deadline:
                        raise RuntimeError(f'{path}: HTTP {error.code}: {detail}') from error
                    time.sleep(2)
        person = json.loads(request('/api/login', {'login':'admin','password':os.environ['DEMO_PASSWORD']}))
        assert person['role'] == 'admin'
        tickets = json.loads(request('/api/tickets')); assert len(tickets) >= 6
        tutorials=json.loads(request('/api/tutorials'));assert len(tutorials)==4
        practice=json.loads(request('/api/tickets/'+str(tutorials[0]['version_id'])+'/try',{}));assert practice['state']['preview']
        report['guided_tickets']=4;report['teacher_practice']=True
        dds=next(t for t in tutorials if t['key']=='dds-1')
        call=json.loads(request('/api/tickets/'+str(dds['version_id'])+'/try',{}))
        call=json.loads(request('/api/attempts/'+str(call['id'])+'/command',{'command_id':secrets.token_hex(16),'revision':call['revision'],'type':'contact','payload':{'id':'brigade','text':'Виден дым, пострадавших нет'}}))
        recording=call['state']['messages'][-1]['audio'];assert recording
        assert request('/api/media/'+recording).startswith(b'RIFF')
        report['dds_prerecorded_answer']=True

        assert isinstance(json.loads(request('/api/teacher/students')),list)
        assert request('/api/teacher/report.xlsx').startswith(b'PK')
        assert request('/api/teacher/report.pdf').startswith(b'%PDF-')
        report['teacher_profiles']=True
        report['teacher_reports']=True
        assert b'<html' in request('/')
        system = json.loads(request('/api/system')); assert system['database'] == 'SQLite' and system['classifier_count'] > 1000
        import io,zipfile
        with zipfile.ZipFile(io.BytesIO(request('/api/diagnostics/bundle'))) as bundle:
            assert 'system.json' in bundle.namelist()
            report['diagnostics']=True
        ai_status=json.loads(request('/api/ai/status'))
        report['ai_available']=ai_status['available']
        from local_ai.voice import VoiceRuntime
        voice=VoiceRuntime(data/'voice-selftest')
        try:
            speech_status=json.loads(request('/api/voice/settings'))
            assert speech_status['available'],speech_status
            speech,metrics=voice.synthesize('Проверка связи. Бригада прибыла.',settings={'tts':'silero','tts_device':'cpu'})
            assert speech.read_bytes()[:4]==b'RIFF' and metrics['duration']>0
            import base64
            recognized=voice.transcribe(base64.b64encode(speech.read_bytes()).decode())
            assert recognized['text']
            report['voice']={'tts':metrics,'stt':recognized,'models':speech_status.get('models',{})}
        finally:voice.stop()
        if ai_status['available']:
            from local_ai.engine import engine as local_engine
            from local_ai.worker import Worker
            from apps.api.app.ai_workers import broker
            node=json.loads(request('/api/classroom/register',{'number':'9999'}))
            req=urllib.request.Request(server.url+'/api/classroom/stations/'+node['id'],
                json.dumps({'approved':True}).encode(),{'Content-Type':'application/json','X-Requested-With':'Training112'},method='PATCH')
            with client.open(req,timeout=10) as response:assert response.status==200
            request_when_ai_idle('/api/ai/execution',{'execution':'workstations','worker_ids':[node['id']]})
            worker=Worker(server.url,node['token'],data/'test-worker')
            worker.start()
            try:
                deadline=time.monotonic()+15
                while node['id'] not in broker.workers:
                    if time.monotonic()>deadline:raise TimeoutError('Compute PC registration timeout')
                    time.sleep(.1)
                schema={'type':'object','properties':{'answer':{'type':'string','enum':['ready']}},'required':['answer'],'additionalProperties':False}
                value,meta=local_engine.complete('Return the requested JSON.','Return answer ready.',schema,tokens=32)
                assert value=={'answer':'ready'} and meta.get('execution')=='workstation',meta
                report['ai_workstation']=True
            finally:
                worker.stop()
                request_when_ai_idle('/api/ai/execution',{'execution':'server','worker_ids':[]})
            if os.getenv('SELF_TEST_GPU')=='1':
                try:
                    local_engine.set_mode('gpu')
                    value,meta=local_engine.complete('Return the requested JSON.','Return answer ready.',schema,tokens=32)
                    assert value=={'answer':'ready'} and meta['mode']=='gpu'
                    report['ai_gpu']=True
                finally:local_engine.set_mode('cpu')
        request('/api/logout', {})
        request('/api/login', {'login':'student','password':os.environ['DEMO_PASSWORD']})
        assignments = json.loads(request('/api/assignments'))
        if ai_status['available']:
            source=next(a for a in assignments if 'Задымление' in a['title'])
            call=json.loads(request('/api/assignments/'+str(source['id'])+'/start',{}))
            call=json.loads(request('/api/attempts/'+str(call['id'])+'/command',{'command_id':secrets.token_hex(16),'revision':call['revision'],'type':'accept_call'}))
            call=json.loads(request('/api/ai/attempts/'+str(call['id'])+'/question',{'command_id':secrets.token_hex(16),'revision':call['revision'],'text':'Как я могу к вам обращаться?'}))
            assert 'name' in call['state']['asked']
            report['ai_question']=True
        assignment = next(a for a in assignments if 'взаимодействие с бригадой' in a['title'])
        try:request('/api/assignments/'+str(assignment['id'])+'/start', {})
        except urllib.error.HTTPError as error:
            assert error.code==409
            report['voice_readiness_gate']=True
        attempt = json.loads(request('/api/tutorials/'+str(dds['version_id'])+'/start', {}))
        attempt = json.loads(request('/api/attempts/'+str(attempt['id'])+'/command', {
            'command_id': secrets.token_hex(16), 'revision':attempt['revision'], 'type':'contact',
            'payload':{'id':'brigade','text':'Проверочный ввод: передаю заявку на Учебной, дом 12.'}}))
        assert attempt['state']['messages'][0]['text'].startswith('Проверочный')
        import tkinter as tk
        root=tk.Tk(); root.withdraw(); root.update(); root.destroy()
        import webview
        from native_window import install_microphone_permission_handler,VoiceBridge,authorize_admin
        native_bridge=VoiceBridge(voice,authorize_settings=lambda:authorize_admin(native,server.url))
        permission_handler=install_microphone_permission_handler(server.url,native_bridge.consume_microphone_permission)
        native_result={}
        native=webview.create_window('112 self-test',server.url,hidden=True,js_api=native_bridge)
        def check_native():
            try:
                native_result['title']=native.evaluate_js('document.title')
                voice_done=threading.Event()
                def voice_checked(value):
                    native_result['bridge']=value;voice_done.set()
                native.evaluate_js("""(async()=>{
                  for(let i=0;i<50&&!window.pywebview?.api?.allow_microphone;i++)await new Promise(r=>setTimeout(r,100));
                  const api=window.pywebview.api;
                  let denied=false;try{await api.voice_settings({chat_enabled:true});}catch{denied=true;}
                  await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'Training112'},body:JSON.stringify({login:'admin',password:__PASSWORD__})});
                  const settings=await api.voice_settings({chat_enabled:true});
                  const allowed=await api.allow_microphone();
                  const spoken=await api.voice_speak('Проверка связи. Бригада прибыла.','male');
                  const heard=await api.voice_transcribe(spoken.audio.split(',')[1]);
                  return {denied,settingsSaved:settings.live.chat_enabled,allowed,capabilities:await api.voice_capabilities(),audio:spoken.audio.startsWith('data:audio/wav;base64,'),text:heard.text};
                })()""".replace("__PASSWORD__",json.dumps(os.environ["DEMO_PASSWORD"])),callback=voice_checked)
                if not voice_done.wait(45):raise TimeoutError('Native speech bridge timed out')
                native_result['ready']=native.evaluate_js('document.getElementById("root") !== null')
            finally: native.destroy()
        native.events.loaded += check_native
        webview.start(gui='edgechromium',storage_path=str(data/'webview-test'))
        assert native_result.get('ready'), native_result
        assert permission_handler['ready']
        assert native_result.get('bridge',{}).get('allowed') and native_result['bridge'].get('audio') and native_result['bridge'].get('text'),native_result
        report['native_voice_bridge']=native_result['bridge']
        assert native_result['bridge']['denied'] and native_result['bridge']['settingsSaved']
        voice.stop()
        report['native_permission_handler']=True
        server.stop(); server.thread.join(60)
        assert not server.thread.is_alive(), 'Сервер не завершился перед проверкой повторного запуска.'
        saved_attempt=attempt['id']
        server=Server(data); server.start()
        deadline=time.monotonic()+60
        while not server.ready():
            if server.error: raise RuntimeError(server.error)
            if time.monotonic()>deadline: raise TimeoutError('Restart timeout')
            time.sleep(.2)
        resumed=json.loads(request('/api/attempts/'+str(saved_attempt)))
        assert resumed['state']['messages'][0]['text'].startswith('Проверочный')
        assert any((data/'backups').glob('*/dispetcher.db'))
        report.update(ok=True, tickets=len(tickets), classifier_count=system['classifier_count'], attempt_id=attempt['id'],
                      tkinter=True, webview2=native_result, restart_preserves_data=True, startup_backup=True)
    except Exception as error:
        logging.exception('Packaged self-test failed'); report['error'] = str(error)
    finally:
        server.stop()
        if server.thread: server.thread.join(60)
        report['stopped'] = not server.thread.is_alive()
        (data / 'self-test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] and report['stopped'] else 1


def desktop(data):
    import native_window
    native_window.run(data, sys.modules[__name__])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--configure-classroom',action='store_true')
    parser.add_argument('--resume-profile',type=Path)
    args=parser.parse_args()
    if args.resume_profile:os.environ['RESUME_CLASSROOM_PROFILE']=str(args.resume_profile.resolve())
    data=(args.data_dir or Path(os.environ['LOCALAPPDATA'])/'Dispetcher112').resolve()
    log=configure(data)
    if args.configure_classroom:os.environ['CONFIGURE_CLASSROOM']='1'
    try:
        if args.self_test: return self_test(data)
        desktop(data)
        return 0
    except Exception as error:
        logging.exception('Launcher failed')
        if not args.self_test:
            import tkinter.messagebox
            tkinter.messagebox.showerror('Тренажёр 112', f'Не удалось запустить приложение: {error}\nЖурналы: {data / "logs"}')
        return 1

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
