"""One bounded local inference worker. No cloud API and no tool execution."""
import atexit
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
import urllib.request
import logging
import re
from logging.handlers import RotatingFileHandler


class AIUnavailable(RuntimeError):
    pass

MODELS = {
    'models/Qwen3-0.6B-Q4_K_M.gguf': 'Qwen3 0.6B · быстрый',
    'models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf': 'Qwen3 4B Instruct · подробнее',
}
DEFAULT_MODEL = 'models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf'


class LocalEngine:
    def __init__(self, root=None, data=None):
        self.root = Path(root or os.getenv('LOCAL_AI_DIR', Path(__file__).parent)).resolve()
        self.data = Path(data or os.getenv('DATA_DIR', self.root / 'data'))
        self.process = None
        self.url = None
        self.key = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.error = ''
        self.on_event = lambda *args, **kwargs: None
        self.log_thread = None
        self.log_handler = None
        self.delegate = None
        self._gpu_cache=(0,[])
        atexit.register(self.stop)

    def config(self):
        file = self.data / 'ai-settings.json'
        config=json.loads((file if file.exists() else self.root / 'config.json').read_text(encoding='utf-8'))
        if config.get('model') not in MODELS:
            config['mode']='cpu'
            config['model']=DEFAULT_MODEL
        config.setdefault('mode','cpu')
        config.setdefault('execution','server')
        config.setdefault('worker_ids',[])
        config.setdefault('device','')
        return config

    def gpu_devices(self):
        if time.monotonic()-self._gpu_cache[0]<60:return self._gpu_cache[1]
        devices=[];executable=self.root/'runtime/vulkan/llama-server.exe'
        if executable.exists():
            try:
                result=subprocess.run([str(executable),'--list-devices'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for match in re.finditer(r'^\s*(Vulkan\d+):\s*(.+)$',result.stdout+'\n'+result.stderr,re.M):
                    devices.append({'id':match[1],'name':match[2].strip()})
            except (OSError,subprocess.TimeoutExpired):pass
        self._gpu_cache=(time.monotonic(),devices)
        return devices

    def status(self):
        c = self.config()
        return {'mode': c['mode'], 'threads': c['threads'], 'model': Path(c['model']).stem,
                'model_id':c['model'], 'models':[{'id':name,'label':label,'available':(self.root/name).is_file()} for name,label in MODELS.items()],
                'available': (self.root / c['model']).is_file() and (self.root/'runtime'/('vulkan' if c['mode']=='gpu' else 'cpu')/'llama-server.exe').is_file(),
                'gpu_available': bool(self.gpu_devices()),'gpus':self.gpu_devices(),'device':c['device'],
                'execution': c['execution'],
                'running': self.process is not None and self.process.poll() is None,
                'busy': self.lock.locked(), 'error': self.error}

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=10)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=5)
        self.process = None
        if self.log_thread: self.log_thread.join(timeout=2)
        if self.log_handler: self.log_handler.close(); self.log_handler=None
        self.on_event('ai_stopped')

    def set_mode(self, mode):
        self.set_settings(mode=mode)

    def set_settings(self, mode=None, execution=None, worker_ids=None, device=None, model=None):
        if mode is not None and mode not in ('cpu','gpu'): raise ValueError('Выберите CPU или GPU')
        if execution is not None and execution not in ('server','workstations'): raise ValueError('Выберите место вычислений')
        if model is not None and model not in MODELS: raise ValueError('Неизвестная модель')
        if model is not None and not (self.root/model).is_file(): raise ValueError('Файл выбранной модели не найден')
        if mode=='gpu' and not (self.root/'runtime/vulkan/llama-server.exe').is_file():
            raise ValueError('В поставке отсутствует компонент GPU Vulkan')
        if mode=='gpu':
            available=self.gpu_devices()
            if not available:raise ValueError('Совместимые видеокарты Vulkan не обнаружены')
            device=device or available[0]['id']
            if device not in [d['id'] for d in available]:raise ValueError('Выбранная видеокарта недоступна')
        if not self.lock.acquire(blocking=False): raise AIUnavailable('Нейросеть занята. Повторите после ответа.')
        try:
            c = self.config()
            if model is not None:c['model']=model
            if mode is not None:c['mode']=mode
            if device is not None:c['device']=device
            if execution is not None:c['execution']=execution
            if worker_ids is not None:c['worker_ids']=list(dict.fromkeys(worker_ids))
            self.data.mkdir(parents=True, exist_ok=True)
            temp = self.data / 'ai-settings.tmp'
            temp.write_text(json.dumps(c, indent=2), encoding='utf-8')
            temp.replace(self.data / 'ai-settings.json')
            self.stop(); self.error = ''
        finally: self.lock.release()

    def start(self):
        if self.process and self.process.poll() is None: return
        c = self.config()
        executable = self.root / 'runtime' / ('cpu' if c['mode'] == 'cpu' else 'vulkan') / 'llama-server.exe'
        model = self.root / c['model']
        if not executable.is_file() or not model.is_file():
            raise AIUnavailable('Локальная модель не установлена. Нужна папка local_ai с моделью и runtime.')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        logs = self.data / 'logs'; logs.mkdir(parents=True, exist_ok=True)
        args = [str(executable), '-m', str(model), '--host', '127.0.0.1', '--port', str(port),
                '-t', str(c['threads']), '-tb', str(c['threads']), '-ngl', '0' if c['mode'] == 'cpu' else '99',
                '-c', str(c['context']), '-np', '1', '--reasoning', 'off', '--api-key', self.key]
        if c['mode']=='gpu' and c['device']:args+=['--device',c['device']]
        logger=logging.getLogger('training112.llama.'+str(id(self)));logger.setLevel(logging.INFO);logger.propagate=False;logger.disabled=False
        for old in logger.handlers[:]: old.close();logger.removeHandler(old)
        self.log_handler=RotatingFileHandler(logs/'local-ai.log',maxBytes=5_000_000,backupCount=2,encoding='utf-8')
        logger.addHandler(self.log_handler)
        self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                        text=True,encoding='utf-8',errors='replace',bufsize=1,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        output=self.process.stdout
        def drain():
            try:
                for line in output: logger.info(line.rstrip())
            finally: output.close()
        self.log_thread=threading.Thread(target=drain,daemon=True);self.log_thread.start()
        self.on_event('ai_starting',mode=c['mode'],threads=c['threads'],model=model.name,pid=self.process.pid)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.process.poll() is not None: break
            try:
                req = urllib.request.Request(self.url + '/health', headers={'Authorization': 'Bearer ' + self.key})
                with urllib.request.urlopen(req, timeout=1) as response:
                    if response.status == 200:
                        self.on_event('ai_ready',mode=c['mode']);return
            except Exception: time.sleep(.15)
        self.stop()
        raise AIUnavailable('Нейросеть не запустилась. Проверьте local-ai.log; для GPU нужен драйвер Vulkan.')

    def complete(self, system, prompt, schema, tokens=128, temperature=0):
        if self.delegate and self.config()['execution']=='workstations':
            result=self.delegate(system,prompt,schema,tokens,temperature)
            if result is not None:return result
        # Fail fast instead of holding an unbounded queue on the minimum CPU.
        if not self.lock.acquire(blocking=False): raise AIUnavailable('Нейросеть занята другим запросом. Повторите через несколько секунд.')
        started = time.monotonic()
        try:
            self.on_event('ai_request_started',max_tokens=tokens)
            self.start()
            ready = time.monotonic()
            body = {'messages': [{'role':'system','content':system}, {'role':'user','content':prompt}],
                    'max_tokens':tokens, 'temperature':temperature,
                    'chat_template_kwargs':{'enable_thinking':False},
                    'response_format':{'type':'json_schema','json_schema':{'name':'response','strict':True,'schema':schema}}}
            req = urllib.request.Request(self.url + '/v1/chat/completions', json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                         {'Content-Type':'application/json','Authorization':'Bearer ' + self.key})
            with urllib.request.urlopen(req, timeout=120) as response: result=json.load(response)
            choice=result['choices'][0]
            if choice.get('finish_reason') != 'stop': raise ValueError('Превышен лимит ответа')
            value=json.loads(choice['message']['content'])
            self.error=''
            timing={'seconds':round(time.monotonic()-started,3),
                    'startup_seconds':round(ready-started,3),
                    'inference_seconds':round(time.monotonic()-ready,3)}
            self.on_event('ai_request_finished',**timing,usage=result.get('usage',{}))
            return value, {'model':Path(self.config()['model']).stem,'mode':self.config()['mode'],
                           **timing,'usage':result.get('usage',{})}
        except AIUnavailable as error:
            self.on_event('ai_request_failed',error=str(error))
            self.error=str(error); raise
        except Exception as error:
            logging.exception('Local text inference failed')
            self.on_event('ai_request_failed',error_type=type(error).__name__,error=str(error))
            self.error='Не удалось получить корректный ответ локальной модели.'
            raise AIUnavailable(self.error) from error
        finally: self.lock.release()


engine = LocalEngine()
