"""Native Windows application window, with the existing UI embedded in WebView2."""
import ctypes
import logging
import os
import json
from pathlib import Path
import time


def authorize_admin(window,url):
    from urllib.request import Request,urlopen
    try:
        cookies={key:morsel.value for cookie in window.get_cookies() for key,morsel in cookie.items()}
        request=Request(url.rstrip('/')+'/api/me',headers={'Cookie':'; '.join(key+'='+value for key,value in cookies.items())})
        with urlopen(request,timeout=5) as response:return json.load(response).get('role')=='admin'
    except Exception:return False


class VoiceBridge:
    """Shared by the production window and the packaged WebView smoke test."""
    def __init__(self,voice,voice_sync=None,authorize_settings=None):
        self._authorize_settings=authorize_settings
        self._voice=voice;self._voice_sync=voice_sync;self._microphone_until=0
    def voice_capabilities(self):
        return {'protocol':1,'microphone':True,'tts':True,'stt':True}
    def voice_cancel(self):self._voice.stop();return True
    def voice_status(self):return {**self._voice.status(),'sync':self._voice_sync.status if self._voice_sync else {}}
    def voice_settings(self,value):
        if not self._authorize_settings or not self._authorize_settings():raise PermissionError('Настройки голоса доступны только администратору.')
        return self._voice.save({'live':value})
    def voice_transcribe(self,content):return self._voice.transcribe(content)
    def voice_speak(self,text,gender='female'):return self._voice.speak(str(text)[:5000],gender)
    def voice_classify(self,text,questions):return self._voice.classify(str(text)[:500],questions)
    def voice_filler(self,gender='female'):return self._voice.filler(gender)
    def voice_cached(self,key):return self._voice_sync.audio(key) if self._voice_sync else None
    def allow_microphone(self):
        self._microphone_until=time.monotonic()+15
        return True
    def consume_microphone_permission(self):
        allowed=time.monotonic()<self._microphone_until
        self._microphone_until=0
        return allowed


def install_microphone_permission_handler(url,authorize):
    """Keep the consent UI in the application; never persist a blanket permission."""
    from webview.platforms.edgechromium import EdgeChrome
    from Microsoft.Web.WebView2.Core import CoreWebView2PermissionKind,CoreWebView2PermissionState
    from urllib.parse import urlsplit
    original_ready=EdgeChrome.on_webview_ready
    status={'ready':False}
    def ready_with_permissions(browser,sender,args):
        original_ready(browser,sender,args)
        if not args.IsSuccess:return
        def permission(sender,event):
            if event.PermissionKind==CoreWebView2PermissionKind.Microphone:
                origin=urlsplit(str(event.Uri));expected=urlsplit(url)
                allowed=(origin.scheme,origin.netloc)==(expected.scheme,expected.netloc) and authorize()
                event.State=CoreWebView2PermissionState.Allow if allowed else CoreWebView2PermissionState.Deny
                event.SavesInProfile=False
        sender.CoreWebView2.PermissionRequested += permission
        status['ready']=True
    EdgeChrome.on_webview_ready=ready_with_permissions
    return status


def run(data, launcher):
    import tkinter as tk
    from tkinter import ttk, messagebox
    import webview
    from desktop_style import decorate, icon_path
    webview.settings['ALLOW_DOWNLOADS'] = True
    from classroom_setup import choose_launch_mode,setup,ClientProxy,enroll
    base_data=data
    resume=os.getenv('RESUME_CLASSROOM_PROFILE')
    from demo_profiles import DEMO_PASSWORD,reserve
    if resume:
        data=Path(resume).resolve()
        config=json.loads((data/'classroom.json').read_text('utf-8'))
        launcher.configure(data)
    else:
        launch_mode=choose_launch_mode()
        if not launch_mode:return
        config={'demo':True} if launch_mode=='demo' else setup(data,force=os.getenv('CONFIGURE_CLASSROOM')=='1')
    import gc
    gc.collect()  # Dispose Tk variables on the UI thread before starting workers.
    if not config:return
    close_handle=lambda h: ctypes.WinDLL('kernel32').CloseHandle(ctypes.c_void_p(h))
    if config.get('demo') and not resume:
        from demo_profiles import DEMO_PASSWORD,reserve
        from lan_discovery import verify
        running=verify('http://127.0.0.1:8765')
        if running and running.get('setup_policy')!='confirm-name-each-start':
            messagebox.showerror('Обновите учебный сервер',
                'На этом ПК уже запущен сервер из прежней сборки. Закройте его и запустите новую версию первым экземпляром.')
            return
        data,config,handle=reserve(data,launcher.single_instance,close_handle,verify)
        launcher.configure(data)
        if config['mode']=='server' and not launcher.initialized(data):
            os.environ['DEMO_PASSWORD']=DEMO_PASSWORD
        exists=False
    else:
        handle, exists = launcher.single_instance(data)
    if exists:
        # Do not open the user's external browser on second launch.
        hwnd = ctypes.windll.user32.FindWindowW(None, 'Тренажёр 112 / ДДС')
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        else: messagebox.showinfo('Тренажёр 112', 'Приложение уже запускается. Откройте его окно на панели задач.')
        close_handle(handle)
        return
    if getattr(__import__('sys'),'frozen',False) and (data/'active-install.json').exists():
        import subprocess,sys
        active=json.loads((data/'active-install.json').read_text('utf-8'))
        candidate=Path(active.get('exe','')).resolve()
        def version_numbers(value):
            try:return tuple(int(part) for part in str(value).split('.'))
            except ValueError:return ()
        if version_numbers(active.get('version',''))>version_numbers(launcher.VERSION) and candidate.name=='Dispetcher112.exe' and candidate.parent.parent==(data/'updates').resolve() and candidate.is_file() and candidate!=Path(sys.executable).resolve():
            close_handle(handle)
            try:
                subprocess.Popen([str(candidate),'--data-dir',str(base_data),'--resume-profile',str(data)],creationflags=subprocess.CREATE_NO_WINDOW)
                return
            except OSError:
                handle,exists=launcher.single_instance(data)
                if exists:close_handle(handle);return
    (data/'classroom.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    if config['mode']=='server':
        os.environ['CLASSROOM_SERVER']='1'
        os.environ['ENFORCE_WORKSTATIONS']='1'
        os.environ['ENFORCE_SERVER_NAME']='1'
        os.environ['CLASSROOM_NAME']=config.get('name','Учебный класс')
        if config.get('station_id'):os.environ['CLASSROOM_SERVER_STATION_ID']=config['station_id']
        if config.get('demo'):
            os.environ['DEMO_CLASSROOM']='1'
            if config.get('station_id'):os.environ['DEMO_SERVER_STATION_ID']=config['station_id']
    server = launcher.Server(data) if config['mode']=='server' else ClientProxy(config['server'])
    root = tk.Tk()
    frame=decorate(root, 'Запуск тренажёра · 112 / ДДС', 'Подготовка учебного места', '660x490')
    status=tk.StringVar(value='Подготовка приложения…')
    ttk.Label(frame,textvariable=status,wraplength=470).pack(anchor='w',pady=14)
    ready=False
    started=False
    deadline=time.monotonic()+90
    worker=None
    agent=None
    def poll():
        nonlocal ready
        if server.error:
            status.set('Не удалось запустить сервер.'); messagebox.showerror('Ошибка',server.error); root.destroy()
        elif server.ready(): ready=True; root.destroy()
        elif time.monotonic()>deadline:
            messagebox.showerror('Подключение','Сервер не отвечает. Проверьте его доступность в локальной сети. Для выбора другого сервера запустите ярлык настройки подключения.');root.destroy()
        else: root.after(200,poll)
    def begin():
        nonlocal started,deadline
        deadline=time.monotonic()+90
        started=True; server.start(); root.after(200,poll)
    if config['mode']=='server' and not launcher.initialized(data) and not os.environ.get('DEMO_PASSWORD'):
        status.set('Задайте пароль учебных учётных записей: admin, teacher, student, student2.')
        password=tk.StringVar(); confirmation=tk.StringVar()
        for label,var in [('Пароль (8–128 символов)',password),('Повтор пароля',confirmation)]:
            ttk.Label(frame,text=label).pack(anchor='w'); ttk.Entry(frame,textvariable=var,show='*').pack(fill='x')
        def create():
            if not 8<=len(password.get())<=128 or password.get()!=confirmation.get():
                messagebox.showerror('Пароль','Введите одинаковые пароли длиной от 8 до 128 символов.'); return
            os.environ['DEMO_PASSWORD']=password.get(); button.configure(state='disabled'); begin()
        button=ttk.Button(frame,text='Создать базу и открыть',command=create);button.pack(anchor='w',pady=12)
    else: begin()
    try:
        root.mainloop()
        if not ready: return
        if config.get('demo') and config['mode']=='client':
            from lan_discovery import verify
            server_info=verify(config['server'])
            generation=server_info['id'] if server_info else ''
            if config.get('server_generation')!=generation:
                config['station_configured']=False
                config['server_selected']=False
                config['number']='Демо слот '+data.name.rsplit('-',1)[-1]
            config['server_generation']=generation
            (data/'classroom.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
        config=enroll(config,data)
        if config.get('demo') and config['mode']=='client' and not config.get('station_configured'):
            import urllib.request
            request=urllib.request.Request(config['server']+'/api/classroom/demo-pending',b'{}',
                {'Content-Type':'application/json','X-Requested-With':'Training112','X-Workstation':config['token']})
            with urllib.request.urlopen(request,timeout=10) as response:config['number']=json.load(response)['number']
            (data/'classroom.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
        if config['mode']=='server':
            os.environ['CLASSROOM_SERVER_STATION_ID']=config['station_id']
        if config.get('demo') and config['mode']=='server':
            os.environ['DEMO_SERVER_STATION_ID']=config['station_id']
        demo_password_hint=''
        if config.get('demo') and config['mode']=='client':
            demo_password_hint=DEMO_PASSWORD
        if config.get('demo') and config['mode']=='server':
            # Older demo databases may use a password chosen by the user.
            import sqlite3
            from argon2 import PasswordHasher,exceptions
            with sqlite3.connect(data/'dispetcher.db') as db:
                hashes=dict(db.execute("SELECT login,password_hash FROM users WHERE login IN ('admin','teacher')"))
            try:
                if all(PasswordHasher().verify(hashes[login],DEMO_PASSWORD) for login in ('admin','teacher')):
                    demo_password_hint=DEMO_PASSWORD
            except (KeyError,exceptions.VerificationError):
                pass
        if config['mode']=='client':
            from local_ai.worker import Worker
            worker=Worker(config['server'],config['token'],data)
            worker.start()
        from local_ai.voice import VoiceRuntime
        from device_runtime.voice_sync import VoiceSync
        voice=VoiceRuntime(data/"workstation-voice")
        voice_sync=VoiceSync(config,data)
        class DesktopBridge(VoiceBridge):
            def report_ui_error(self,message,stack):
                logging.error("UI error: %s | %s",str(message)[:2000],str(stack)[:4000]);return True
            def save_report(self,name,content):
                import base64
                safe=Path(str(name)).name
                if Path(safe).suffix.lower() not in ('.csv','.xlsx','.pdf') or len(content)>28000000:
                    raise ValueError('Неподдерживаемый отчёт')
                result=window.create_file_dialog(webview.SAVE_DIALOG,save_filename=safe)
                if not result:return False
                target=result if isinstance(result,str) else result[0]
                Path(target).write_bytes(base64.b64decode(content,validate=True))
                return True
            def get_demo_identity(self):
                return {'role':config['mode'] if config.get('demo') else '', 'password':demo_password_hint,
                        'configured':bool(config.get('station_configured'))}
            def choose_backup_folder(self):
                result=window.create_file_dialog(webview.FOLDER_DIALOG)
                return result[0] if result else None
            def save_demo_number(self,number):
                if not config.get('demo') or not str(number).isdigit():return False
                config['number']=str(number)
                config['station_configured']=True
                (data/'classroom.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
                return True
            def save_demo_server(self,url):
                if not config.get('demo') or config['mode']!='client' or url!=config['server']:return False
                config['server_selected']=True
                (data/'classroom.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
                return True
        native_bridge=DesktopBridge(voice,voice_sync,lambda:authorize_admin(window,server.url))
        window=webview.create_window('Тренажёр 112 / ДДС',server.url,width=1366,height=900,
                                     min_size=(1024,680),maximized=True,js_api=native_bridge)
        from device_runtime.agent import Agent
        agent=Agent(config,data,base_data,window,worker,launcher.VERSION)
        identified_once=False
        def identify():
            nonlocal identified_once
            values={'training112:station-token':config['token'],'training112:station-number':config['number'],
                    'training112:station-mode':config['mode'],'training112:demo-role':config['mode'] if config.get('demo') else '',
                    'training112:demo-password-hint':demo_password_hint,
                    'training112:station-configured':str(bool(config.get('station_configured'))).lower(),
                    'training112:server-selected':str(bool(config.get('server_selected'))).lower(),
                    'training112:server-url':config['server']}
            script=''.join('localStorage.setItem('+json.dumps(key)+','+json.dumps(value)+');' for key,value in values.items())
            if identified_once:
                pass
            elif config.get('demo') and config['mode']=='server':
                script+='sessionStorage.setItem("training112:demo-welcome","server");'
            elif config.get('demo') and config['mode']=='client' and not config.get('station_configured'):
                script+='sessionStorage.setItem("training112:demo-welcome","client");'
            else:
                script+='sessionStorage.removeItem("training112:demo-welcome");'
            window.evaluate_js(script+'window.dispatchEvent(new Event("station-ready"));')
            if not identified_once:agent.start()
            identified_once=True
        window.events.loaded += identify
        install_microphone_permission_handler(server.url,native_bridge.consume_microphone_permission)
        webview.start(gui='edgechromium',icon=str(icon_path()),private_mode=bool(config.get('demo')),storage_path=str(data/'webview'))
    finally:
        if agent and agent.thread.is_alive():agent.stop()
        if "voice" in locals():voice.stop()
        if "voice_sync" in locals():voice_sync.stop()
        if worker:worker.stop()
        server.stop()
        if server.thread: server.thread.join(20)
        ctypes.WinDLL('kernel32').CloseHandle(ctypes.c_void_p(handle))
