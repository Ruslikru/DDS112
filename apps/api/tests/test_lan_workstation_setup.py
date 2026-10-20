import hashlib,json,sys,time,uuid
from pathlib import Path
import pytest
from sqlalchemy import select,func
from test_flows import app,TestClient,SessionLocal,login,post,HEAD
from apps.api.app.classroom_models import Workstation
from apps.api.app.management_models import ManagementSetting
from apps.api.app.desktop_enrollment import enroll_server

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'packaging'))
from device_connection import load_connection,save_connection,recovery_connection

@pytest.fixture(autouse=True)
def no_warmup(monkeypatch):
    from apps.api.app import startup_models
    async def idle():pass
    monkeypatch.setattr(startup_models,'warm_models',idle)


def test_server_enrollment_never_consumes_a_workstation_number():
    with TestClient(app),SessionLocal() as db:
        old_number=next(str(n) for n in range(850,999) if not db.scalar(select(Workstation).where(Workstation.number==str(n))))
        secret='server-'+uuid.uuid4().hex
        row=Workstation(id=uuid.uuid4().hex,number=old_number,secret_hash=hashlib.sha256(secret.encode()).hexdigest(),approved=True)
        db.add(row);db.commit();wid=row.id
        count=db.scalar(select(func.count()).select_from(Workstation))
    config=enroll_server({'mode':'server','number':old_number,'station_id':wid,'token':secret})
    assert config['station_id']==wid and config['token']==secret and not config['number'].isdigit()
    restored=enroll_server({**config,'token':'expired-token'})
    assert restored['station_id']==wid and restored['token']!='expired-token'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Workstation))==count
        assert not db.scalar(select(Workstation).where(Workstation.number==old_number))


def test_admin_enrollment_is_atomic_and_allows_student_after_restart(monkeypatch):
    monkeypatch.setenv('ENFORCE_SERVER_NAME','1');monkeypatch.setenv('ENFORCE_WORKSTATIONS','1')
    with TestClient(app) as admin,TestClient(app) as pc:
        login(admin,'admin')
        post(admin,'/management/server-name',{'name':'LAN проверка'})
        assert post(pc,'/classroom/workstation-setup',{'number':'801'}).status_code==401
        login(pc,'teacher')
        assert post(pc,'/classroom/workstation-setup',{'number':'801'}).status_code==403
        number=next(str(n) for n in range(700,800) if all(w['number']!=str(n) for w in admin.get('/api/classroom/stations').json()))
        first=post(admin,'/classroom/workstation-setup',{'number':number});assert first.status_code==200,first.text
        station=first.json()
        duplicate=post(admin,'/classroom/workstation-setup',{'number':number})
        assert duplicate.status_code==409 and 'уже занят' in duplicate.json()['detail']
        updated=post(admin,'/classroom/workstation-setup',{'number':number,'station_token':station['token']})
        assert updated.json()['id']==station['id'] and updated.json()['token']==station['token']
        assert post(admin,'/classroom/workstation-setup',{'number':'ПК 1'}).status_code==422
        post(pc,'/logout');pc.headers['X-Workstation']=station['token']
        from apps.api.app.server_identity import reset_activation
        reset_activation()
        admission=pc.get('/api/classroom/admission').json()
        assert admission['configured'] and admission['approved']
        login(pc,'student')
        assert pc.get('/api/me').json()['role']=='student'
        post(pc,'/logout');reset_activation();login(pc,'student')
        assert pc.get('/api/me').json()['role']=='student'


def test_recovery_keeps_the_saved_connection_until_admin_saves(tmp_path):
    original={'mode':'client','server':'http://192.168.1.10:8765','number':'12','token':'valid','station_id':'id','setup_complete':True}
    save_connection(tmp_path,original)
    fallback=recovery_connection(load_connection(tmp_path),'Номер уже занят')
    assert not fallback['setup_complete'] and fallback['saved_connection']['token']=='valid'
    assert json.loads((tmp_path/'classroom.json').read_text())==original
    assert load_connection(tmp_path)['token']=='valid'


def test_network_address_is_lan_address_not_loopback(monkeypatch):
    monkeypatch.setenv('CLASSROOM_SERVER','1')
    monkeypatch.setattr('device_runtime.network.lan_addresses',lambda:['192.168.1.14'])
    with TestClient(app) as admin:
        login(admin,'admin')
        result=admin.get('/api/classroom/connection').json()
        assert result['urls']==['http://192.168.1.14:8765']


def test_physical_wifi_is_preferred_to_vpn_and_loopback(monkeypatch):
    from device_runtime import network
    monkeypatch.setattr(network,'_cache',(0,[]))
    monkeypatch.setattr(network,'windows_adapters',lambda:[
        {'ip':'192.168.1.10','physical':True,'gateway':True},
        {'ip':'10.8.0.2','physical':False,'gateway':True},
        {'ip':'172.24.64.1','physical':False,'gateway':False}])
    monkeypatch.setattr(network.socket,'getaddrinfo',lambda *a:[(None,None,None,None,('127.0.0.1',0)),(None,None,None,None,('169.254.1.2',0))])
    addresses=network.lan_addresses()
    assert addresses[0]=='192.168.1.10'
    assert not any(ip.startswith(('127.','169.254.')) for ip in addresses)
