"""First-run classroom selection and a loopback proxy for secure-context client features."""
import json
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

def choose_launch_mode():
    """Ask on every launch whether this is a local demonstration or a LAN class."""
    import tkinter as tk
    from tkinter import ttk
    from desktop_style import decorate

    root = tk.Tk()
    root.minsize(820, 530)
    box = decorate(root, 'Запуск тренажёра · 112 / ДДС', 'Выбор способа запуска', '820x530')
    result = None

    ttk.Label(box, text='Как вы хотите запустить тренажёр?', font=('Segoe UI', 19, 'bold')).pack(anchor='w', pady=(0, 22))

    def select(value):
        nonlocal result
        result = value
        root.destroy()

    ttk.Label(box, text='Для проверки и демонстрации на одном компьютере:').pack(anchor='w', pady=(0, 8))
    ttk.Button(box, text='Запустить на одном ПК', style='Primary.TButton', command=lambda: select('demo')).pack(fill='x', pady=(0, 24))
    ttk.Label(box, text='Для работы на нескольких компьютерах в локальной сети:').pack(anchor='w', pady=(0, 8))
    ttk.Button(box, text='Запуск на нескольких ПК в локальной сети', command=lambda: select('lan')).pack(fill='x')
    root.mainloop()
    return result


def setup(data, force=False):
    import os
    import queue
    import tkinter as tk
    from tkinter import ttk
    from desktop_style import decorate, TEXT, PANEL, BLUE
    from lan_discovery import discover

    file = data / 'classroom.json'
    previous = json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}
    root = tk.Tk()
    root.minsize(760, 720)
    box = decorate(root, 'Настройка учебного места · 112 / ДДС', 'Подключение к учебному классу', '800x740')
    ttk.Label(box, text='Где работает этот компьютер?', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
    ttk.Label(box, text='Выберите роль компьютера. Настройка сохраняется после первого запуска.').pack(anchor='w', pady=(7, 20))
    mode = tk.StringVar(value=previous.get('mode', 'client'))
    number = tk.StringVar(value=previous.get('number', '1'))
    selection = tk.StringVar()
    password = tk.StringVar()
    confirm = tk.StringVar()
    name = tk.StringVar(value=previous.get('name', 'Учебный класс'))
    status = tk.StringVar(value='Ищем учебные серверы в локальной сети…')
    error = tk.StringVar()
    result = None
    found = {}
    responses = queue.Queue()
    searching = False
    choices = ttk.Frame(box)
    choices.pack(fill='x', pady=(0, 16))
    choices.columnconfigure((0, 1), weight=1)
    for i, (value, title) in enumerate([('client', 'Рабочее место'), ('server', 'Учебный сервер')]):
        tk.Radiobutton(choices, text=title, variable=mode, value=value, indicatoron=False,
                       bg='#e6ebee', fg=TEXT, selectcolor='#d4eaf5', activebackground='#d4eaf5',
                       relief='flat', borderwidth=1, padx=18, pady=13, cursor='hand2',
                       font=('Segoe UI', 12, 'bold')).grid(row=0, column=i, sticky='ew', padx=(0, 8) if i == 0 else (8, 0))
    client_box = ttk.Frame(box)
    ttk.Label(client_box, text='Доступный учебный сервер', font=('Segoe UI', 10, 'bold')).pack(anchor='w')
    row = ttk.Frame(client_box)
    row.pack(fill='x', pady=(6, 8))
    servers = ttk.Combobox(row, textvariable=selection, state='readonly')
    servers.pack(side='left', fill='x', expand=True, padx=(0, 10))
    refresh = ttk.Button(row, text='Обновить список')
    refresh.pack(side='right')
    ttk.Label(client_box, textvariable=status, wraplength=650).pack(anchor='w')
    ttk.Label(client_box, text='Устройства должны быть в одной сети. Включите сервер и обновите список.', wraplength=650, foreground='#657c8b').pack(anchor='w', pady=(12, 0))
    number_box = ttk.Frame(box)
    ttk.Label(number_box, text='Номер рабочего места', font=('Segoe UI', 10, 'bold')).pack(anchor='w')
    ttk.Label(number_box, text='Номер должен быть свободен на выбранном сервере.', foreground='#657c8b').pack(anchor='w')
    ttk.Entry(number_box, textvariable=number, width=12).pack(anchor='w', pady=(5, 16))
    server_box = ttk.Frame(box)
    ttk.Label(server_box, text='Этот ПК будет хранить задания и результаты класса.', wraplength=650).pack(anchor='w', pady=(0, 12))
    ttk.Label(server_box, text='После запуска войдите администратором и задайте название сервера.', wraplength=650, foreground='#657c8b').pack(anchor='w', pady=(0, 10))
    new_server = not (data / 'dispetcher.db').exists()
    if new_server:
        fields = ttk.Frame(server_box)
        fields.pack(fill='x')
        for i, (label, variable) in enumerate([('Пароль администратора', password), ('Повтор пароля', confirm)]):
            cell = ttk.Frame(fields)
            cell.pack(side='left', fill='x', expand=True, padx=(0, 16) if i == 0 else 0)
            ttk.Label(cell, text=label, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
            ttk.Entry(cell, textvariable=variable, show='•').pack(fill='x', pady=6)
        ttk.Label(server_box, text='От 8 до 128 символов. Используется для первого входа.', foreground='#657c8b').pack(anchor='w')
    else:
        ttk.Label(server_box, text='Учебная база уже создана. Существующие пароли сохранятся.').pack(anchor='w')
    footer = ttk.Frame(box)
    footer.pack(side='bottom', fill='x', pady=(18, 0))
    ttk.Label(footer, textvariable=error, foreground='#b63f25', wraplength=650).pack(anchor='w', pady=(0, 10))
    button = ttk.Button(footer, text='Подключиться к классу', style='Primary.TButton')
    button.pack(side='right')

    def state_changed(*args):
        error.set('')
        number_box.pack_forget()
        if mode.get() == 'server':
            client_box.pack_forget()
            server_box.pack(fill='x')
            number_box.pack(fill='x')
            button.configure(text='Запустить учебный сервер', state='normal')
        else:
            server_box.pack_forget()
            client_box.pack(fill='x')
            number_box.pack(fill='x')
            button.configure(text='Подключиться к классу', state='normal' if selection.get() in found and not searching else 'disabled')

    def search():
        nonlocal searching
        if searching:
            return
        searching = True
        refresh.configure(state='disabled')
        status.set('Ищем учебные серверы в локальной сети…')
        state_changed()
        def work():
            try:
                responses.put((discover(previous.get('server', '')), None))
            except Exception:
                responses.put(([], 'Не удалось выполнить поиск. Проверьте подключение к локальной сети.'))
        threading.Thread(target=work, daemon=True).start()

    def collect():
        nonlocal searching, found
        try:
            items, issue = responses.get_nowait()
        except queue.Empty:
            root.after(100, collect)
            return
        old = found.get(selection.get(), {}).get('url') or previous.get('server')
        found = {f"{item['name']} · {urlsplit(item['url']).hostname}": item for item in items}
        servers.configure(values=list(found))
        selected = next((label for label, item in found.items() if item['url'] == old), next(iter(found), ''))
        selection.set(selected)
        searching = False
        refresh.configure(state='normal')
        status.set(issue or (f'Найдено серверов: {len(found)}. Выберите свой учебный класс.' if found else 'Серверы не найдены. Обновите список или выберите «Учебный сервер», чтобы создать класс на этом ПК.'))
        state_changed()
        root.after(100, collect)

    def save():
        nonlocal result
        if not number.get().strip() or len(number.get().strip()) > 40:
            error.set('Укажите номер рабочего места: от 1 до 40 символов.')
            return
        if mode.get() == 'client' and selection.get() not in found:
            error.set('Выберите доступный учебный сервер из списка.')
            return
        if mode.get() == 'server' and new_server and (not 8 <= len(password.get()) <= 128 or password.get() != confirm.get()):
            error.set('Введите одинаковые пароли длиной от 8 до 128 символов.')
            return
        url = found[selection.get()]['url'] if mode.get() == 'client' else 'http://127.0.0.1:8765'
        result = {'mode': mode.get(), 'number': number.get().strip(), 'server': url, 'name': name.get().strip()[:100] or 'Учебный класс'}
        if url == previous.get('server') and result['number'] == previous.get('number'):
            result.update({k: previous[k] for k in ('token', 'station_id') if k in previous})
        if mode.get() == 'server' and new_server:
            os.environ['DEMO_PASSWORD'] = password.get()
        root.destroy()

    refresh.configure(command=search)
    button.configure(command=save)
    mode.trace_add('write', state_changed)
    selection.trace_add('write', state_changed)
    def background_focus(event):
        if event.widget.winfo_class() not in ('Entry','TEntry','Text','TCombobox','Spinbox','TSpinbox'):
            root.focus_set()
    root.bind('<Button-1>', background_focus)
    state_changed()
    root.after(100, collect)
    search()
    def cancel_pending(event):
        if event.widget is root:
            for timer in root.tk.call('after', 'info'):
                root.after_cancel(timer)
    root.bind('<Destroy>', cancel_pending)
    root.mainloop()
    return result

class ClientProxy:
    def __init__(self,remote):
        self.remote=remote.rstrip('/');self.error=None
        remote=self.remote
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def proxy(self):
                if self.path.startswith('//'):self.send_error(400);return
                size=int(self.headers.get('Content-Length','0'))
                limit=2*1024**3+1024**2 if self.path=='/api/management/packages' else 25*1024*1024
                if size<0 or size>limit:self.send_error(413);return
                def chunks():
                    remaining=size
                    while remaining:
                        block=self.rfile.read(min(1024**2,remaining))
                        if not block:raise ConnectionError('Incomplete request')
                        remaining-=len(block)
                        yield block
                data=chunks() if size else None
                headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','connection','accept-encoding','content-length')}
                if size:headers['Content-Length']=str(size)
                req=urllib.request.Request(remote+self.path,data=data,headers=headers,method=self.command)
                try:response=urllib.request.urlopen(req,timeout=360)
                except urllib.error.HTTPError as e:response=e
                except Exception:self.send_error(502,'Classroom server unavailable');return
                with response:
                    body=response.read();self.send_response(response.status)
                    for key,value in response.headers.items():
                        if key.lower() not in ('transfer-encoding','connection','content-length','content-encoding'):self.send_header(key,value)
                    self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            do_GET=do_POST=do_PUT=do_PATCH=do_DELETE=proxy
        self.http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.url=f'http://127.0.0.1:{self.http.server_port}'
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
    def start(self):self.thread.start()
    def ready(self):
        try:
            with urllib.request.urlopen(self.remote+'/desktop-health',timeout=2) as r:return r.status==200
        except Exception:
            try:
                with urllib.request.urlopen(self.remote+'/',timeout=2) as r:return r.status==200
            except Exception:return False
    def stop(self):self.http.shutdown();self.http.server_close()

def enroll(config,data):
    if config.get('token'):
        req=urllib.request.Request(config['server']+'/api/classroom/admission',headers={'X-Workstation':config['token']})
        with urllib.request.urlopen(req,timeout=10) as r:
            if json.load(r).get('registered'):return config
        config.pop('token',None);config.pop('station_id',None)
    req=urllib.request.Request(config['server']+'/api/classroom/register',json.dumps({'number':config['number']}).encode(),
        {'Content-Type':'application/json','X-Requested-With':'Training112'})
    with urllib.request.urlopen(req,timeout=10) as r:info=json.load(r)
    config.update(token=info['token'],station_id=info['id']);(data/'classroom.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8');return config
