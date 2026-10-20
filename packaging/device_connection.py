"""Persistent desktop connection, configured only by an authenticated administrator."""
import http.cookiejar
import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

INITIAL_PASSWORD='12345678'


def load_connection(data,force=False):
    file=data/'classroom.json'
    previous=json.loads(file.read_text('utf-8')) if file.exists() else {}
    if previous.get('mode') in ('server','client') and not previous.get('demo'):
        if previous.get('setup_complete') is not True:
            message='Найдена настройка старой версии. Администратор должен подтвердить роль этого компьютера.' if 'setup_complete' not in previous else 'Настройка этого компьютера ещё не завершена. Войдите администратором и выберите его роль.'
            return recovery_connection(previous,message)
        config={**previous,'network_mode':previous.get('network_mode','lan'),
                'setup_complete':True}
        config['station_configured']=config['mode']=='server' or bool(config.get('token') and re.fullmatch(r'[1-9][0-9]{0,2}',str(config.get('number',''))))
        config['server_selected']=bool(config.get('server'))
        if force:config['edit_connection']=True
        return config
    return {'mode':'server','network_mode':'setup','setup_complete':False,'number':'Сервер',
            'server':'http://127.0.0.1:8765','name':'Учебный класс','station_configured':False}


def save_connection(data,config):
    data.mkdir(parents=True,exist_ok=True)
    file=data/'classroom.json';temporary=data/'classroom.json.tmp'
    temporary.write_text(json.dumps({k:v for k,v in config.items() if k!='edit_connection'},ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(file)


def request_json(opener,url,body=None,cookie=''):
    headers={'X-Requested-With':'Training112'}
    if body is not None:headers['Content-Type']='application/json'
    if cookie:headers['Cookie']=cookie
    request=urllib.request.Request(url,json.dumps(body).encode() if body is not None else None,headers)
    try:
        with opener.open(request,timeout=12) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        try:message=json.loads(error.read()).get('detail','Ошибка подключения')
        except (ValueError,AttributeError):message='Ошибка подключения: '+str(error.code)
        raise ValueError(message) from error
    except OSError as error:raise ValueError('Сервер недоступен. Проверьте адрес и подключение к локальной сети.') from error


def connect_workstation(data,previous,url,number,password='',cookie=''):
    from lan_discovery import verify
    parts=urlsplit(str(url).strip())
    if parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password or parts.path not in ('','/') or parts.query or parts.fragment:
        raise ValueError('Укажите адрес учебного сервера, например http://192.168.1.10:8765')
    url=str(url).strip().rstrip('/')
    number=str(number).strip()
    if not re.fullmatch(r'[1-9][0-9]{0,2}',number):raise ValueError('Номер рабочего места должен быть от 1 до 999')
    identity=verify(url)
    if not identity:raise ValueError('Учебный сервер по этому адресу не найден')
    same_server=url==str(previous.get('server','')).rstrip('/') and previous.get('mode')=='client'
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
    if not same_server or not cookie:
        if not password:raise ValueError('Введите пароль администратора выбранного учебного сервера')
        request_json(opener,url+'/api/login',{'login':'admin','password':password})
        cookie=''
    station=request_json(opener,url+'/api/classroom/workstation-setup',{'number':number,'station_token':previous.get('token','') if same_server else ''},cookie)
    config={'mode':'client','network_mode':'lan','setup_complete':True,'station_configured':True,'server_selected':True,
            'server':url,'number':station['number'],'token':station['token'],'station_id':station['id'],'name':identity['name']}
    save_connection(data,config)
    return config


def server_connection(data,previous,role,name):
    if role not in ('server','local'):raise ValueError('Выберите сервер или рабочее место')
    name=str(name).strip()
    if not name or len(name)>100:raise ValueError('Укажите название учебного сервера')
    config={**{k:previous[k] for k in ('token','station_id') if previous.get('mode')=='server' and k in previous},
            'mode':'server','network_mode':'lan' if role=='server' else 'local','setup_complete':True,
            'station_configured':True,'server_selected':True,'number':'Сервер','server':'http://127.0.0.1:8765','name':name,'apply_server_name':True}
    save_connection(data,config)
    return config


def recovery_connection(previous,message):
    return {'mode':'server','network_mode':'setup','setup_complete':False,'station_configured':False,
            'number':'Сервер','server':'http://127.0.0.1:8765','name':'Настройка подключения',
            'recovery':True,'saved_connection':previous,'connection_error':str(message)}
