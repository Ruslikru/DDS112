import hashlib
import json
import time
import uuid
import zipfile
from pathlib import Path
import pytest
from test_flows import app,TestClient,login,post,HEAD,SessionLocal
from apps.api.app import management
from apps.api.app.learning import automatic_services
from device_runtime.updates import validate_package

def register(c):
    row=post(c,'/classroom/register',{'number':'mgmt-'+uuid.uuid4().hex[:8]}).json()
    c.headers['X-Workstation']=row['token']
    assert post(c,'/management/agent/poll',{'metrics':{'cpu_percent':13,'ai':{'gpus':[]}}}).status_code==200
    return row

def test_device_commands_authorization_and_results(monkeypatch):
    with TestClient(app) as admin,TestClient(app) as agent,TestClient(app) as other:
        login(admin,'admin');row=register(agent);another=register(other)
        assert agent.get('/api/management/devices').status_code==401
        login(other,'teacher')
        assert post(other,f'/management/devices/{row["id"]}/action',{'kind':'close'}).status_code==403
        assert next(d for d in admin.get('/api/management/devices').json() if d['id']==row['id'])['name']=='Не вошёл'
        cmd=post(admin,f'/management/devices/{row["id"]}/action',{'kind':'logout'}).json()
        assert post(other,'/management/agent/poll',{'results':[{'id':cmd['id'],'ok':True}]}).status_code==200
        poll=post(agent,'/management/agent/poll').json()
        assert poll['commands'][0]['id']==cmd['id']
        post(agent,'/management/agent/poll',{'results':[{'id':cmd['id'],'ok':True}]})
        assert next(c for c in admin.get('/api/management/commands').json() if c['id']==cmd['id'])['status']=='done'
        monkeypatch.setenv('CLASSROOM_SERVER_STATION_ID',another['id'])
        assert post(admin,f'/management/devices/{another["id"]}/action',{'kind':'remove'}).status_code==400
        assert post(admin,f'/management/devices/{row["id"]}/action',{'kind':'remove'}).status_code==200
        assert post(agent,'/management/agent/poll').json()['revoked']
        assert post(agent,'/classroom/heartbeat').status_code==403

def test_remote_desktop_lease_and_gpu_validation(monkeypatch):
    with TestClient(app) as admin,TestClient(app) as agent:
        login(admin,'admin');row=register(agent);prefix=f'/management/devices/{row["id"]}'
        assert post(admin,prefix+'/ai',{'mode':'gpu','device':'Vulkan99'}).status_code==400
        monkeypatch.setenv('CLASSROOM_SERVER_STATION_ID',row['id'])
        assert post(admin,prefix+'/ai',{'mode':'server'}).status_code==400
        token=post(admin,prefix+'/desktop').json()['token'];path=prefix+'/desktop/'+token
        assert post(admin,path+'/input',{'kind':'click','x':.5,'y':.4}).status_code==200
        p=post(agent,'/management/agent/poll',{'frame':'data:image/jpeg;base64,dGVzdA=='}).json()
        assert p['desktop'] and p['inputs'][0]['kind']=='click'
        assert admin.get('/api'+path).json()['frame']
        assert post(agent,'/management/agent/poll').json()['inputs']==[]
        management.remote[row['id']]['until']=time.time()-1
        assert not post(agent,'/management/agent/poll').json()['desktop']
        assert post(admin,path+'/input',{'kind':'key','key':'Enter'}).status_code==403

def test_backup_and_service_rules(tmp_path):
    with TestClient(app) as admin:
        login(admin,'admin')
        assert admin.get('/api/management/backup').json()['interval_hours']==24
        assert post(admin,'/management/backup',{'folder':'relative'}).status_code==400
        assert post(admin,'/management/backup',{'folder':str(tmp_path),'interval_hours':24,'enabled':True}).status_code==200
        result=post(admin,'/management/backup/run').json();assert not result['error']
        from pathlib import Path
        folder=Path(result['last_folder']);manifest=json.loads((folder/'manifest.json').read_text('utf-8'))
        assert hashlib.sha256((folder/'database.sqlite').read_bytes()).hexdigest()==manifest['files']['database.sqlite']
        name='Test service '+uuid.uuid4().hex
        assert post(admin,'/learning/services',{'name':name,'tags':['газ'],'questions':['Есть запах?'],'rules':[{'field':'description','operator':'contains','value':'газ'},{'field':'victims','operator':'equals','value':'yes'}]}).status_code==200
        with SessionLocal() as db:
            assert name in automatic_services(db,{'description':'Запах ГАЗА','victims':'yes'})
            assert name not in automatic_services(db,{'description':'Запах газа','victims':'no'})
        post(admin,'/learning/services',{'name':name,'active':False})
        saved=next(s for s in admin.get('/api/learning/services').json() if s['name']==name)
        assert saved['questions']==['Есть запах?']

def test_user_reset_and_delete_with_backup(tmp_path):
    login_name='lifecycle_'+uuid.uuid4().hex[:8]
    with TestClient(app) as admin, TestClient(app) as learner:
        login(admin,'admin')
        created=post(admin,'/users',{'login':login_name,'name':'Новый ученик','password':'InitialPass112!','role':'student'}).json()
        uid=created['id']
        assert post(admin,'/management/backup',{'folder':str(tmp_path),'interval_hours':24,'enabled':True}).status_code==200
        reset=post(admin,f'/users/{uid}/reset-password').json()
        temporary=reset['temporary_password']
        assert learner.post('/api/login',json={'login':login_name,'password':'InitialPass112!'},headers=HEAD).status_code==401
        logged=learner.post('/api/login',json={'login':login_name,'password':temporary},headers=HEAD)
        assert logged.status_code==200 and logged.json()['must_change_password']
        assert learner.get('/api/assignments').status_code==403
        changed=post(learner,'/change-password',{'password':'NewPrivatePass112!'})
        assert changed.status_code==200 and not changed.json()['must_change_password']
        assert learner.get('/api/assignments').status_code==200
        blocked=admin.patch(f'/api/users/{uid}',json={'active':False},headers=HEAD)
        assert blocked.status_code==200
        assert learner.get('/api/me').status_code==401
        assert admin.patch(f'/api/users/{uid}',json={'active':True},headers=HEAD).status_code==200
        deleted=admin.delete(f'/api/users/{uid}',headers=HEAD)
        assert deleted.status_code==200,deleted.text
        assert login_name not in [person['login'] for person in admin.get('/api/users').json()]
        assert learner.post('/api/login',json={'login':login_name,'password':'NewPrivatePass112!'},headers=HEAD).status_code==401
        import sqlite3
        with sqlite3.connect(Path(deleted.json()['backup'])/'database.sqlite') as snapshot:
            assert snapshot.execute('select login from users where id=?',(uid,)).fetchone()[0]==login_name
        assert post(admin,'/users',{'login':login_name,'name':'Новая запись','password':'AnotherPass112!','role':'student'}).status_code==200

def test_admin_can_change_name_and_login():
    login_name='rename_'+uuid.uuid4().hex[:8]
    with TestClient(app) as admin:
        login(admin,'admin')
        person=post(admin,'/users',{'login':login_name,'name':'Первое имя','password':'PrivatePass112!','role':'student'}).json()
        updated=admin.patch(f'/api/users/{person["id"]}',json={'name':'Новое имя','login':login_name+'_new'},headers=HEAD)
        assert updated.status_code==200 and updated.json()['login']==login_name+'_new'
        assert updated.json()['name']=='Новое имя'
        assert admin.patch(f'/api/users/{person["id"]}',json={'login':'admin'},headers=HEAD).status_code==400
        assert admin.patch(f'/api/users/{person["id"]}',json={'login':'bad login'},headers=HEAD).status_code==400

def test_service_tags_create_associated_ticket(monkeypatch):
    from apps.api.app import scenario_wizard
    monkeypatch.setattr(scenario_wizard,'complete',lambda *args,**kwargs:({'description':'У дома пахнет газом.','difficulty':'Базовый'},{'model':'test'}))
    with TestClient(app) as admin:
        login(admin,'admin')
        name='Газовая '+uuid.uuid4().hex[:6]
        assert post(admin,'/learning/services',{'name':name,'tags':[' утечка газа ','утечка газа'],'questions':[],'rules':[]}).status_code==200
        service=next(s for s in admin.get('/api/learning/services').json() if s['name']==name)
        assert service['tags']==['утечка газа']
        assert post(admin,'/learning/services',{'name':name,'active':True}).status_code==200
        assert next(s for s in admin.get('/api/learning/services').json() if s['name']==name)['tags']==['утечка газа']
        payload={'incident_type':'утечка газа','mode':'dds','victims_state':'no','victims_count':0,'district':'Учебный район','own_service':name,'services':[name],'traits':[]}
        generated=post(admin,'/ai/wizard',payload)
        assert generated.status_code==200,generated.text
        ticket=generated.json()['data']
        assert name in ticket['tasks'][0]['services']
        assert post(admin,'/tickets',ticket).status_code==200
        assert post(admin,'/ai/wizard',{**payload,'own_service':'ДДС района','services':['ДДС района']}).status_code==400

def package(path,extra=None,bad_hash=False):
    files={'Dispetcher112.exe':b'exe','_internal/test.dll':b'dll'}
    if extra:files[extra]=b'bad'
    manifest={'app':'Dispetcher112.Desktop','version':'0.8.0','files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()}}
    if bad_hash:manifest['files']['Dispetcher112.exe']='0'*64
    with zipfile.ZipFile(path,'w') as z:
        for k,v in files.items():z.writestr(k,v)
        z.writestr('update.json',json.dumps(manifest))

@pytest.mark.parametrize('extra',['../escape.exe','C:/escape.exe','_internal/CON','_internal/a.dll:ads'])
def test_update_rejects_unsafe_paths(tmp_path,extra):
    path=tmp_path/'update.zip';package(path,extra)
    with pytest.raises(ValueError):validate_package(path)

def test_update_package_scope_and_restart_receipt(tmp_path):
    path=tmp_path/'update.zip';package(path,bad_hash=True)
    with pytest.raises(ValueError):validate_package(path)
    package(path);assert validate_package(path)['version']=='0.8.0'
    with TestClient(app) as admin,TestClient(app) as agent,TestClient(app) as other:
        login(admin,'admin');row=register(agent);register(other)
        with path.open('rb') as f:r=admin.post('/api/management/packages',files={'file':('update.zip',f,'application/zip')},headers=HEAD)
        assert r.status_code==200,r.text
        pid=r.json()['id'];url='/api/management/packages/'+pid+'/download'
        assert agent.get(url).status_code==403
        command=post(admin,'/management/updates',{'package_id':pid,'stations':[row['id']]}).json()['ids'][0]
        assert post(agent,'/management/agent/poll').json()['commands'][0]['kind']=='update'
        assert agent.get(url).status_code==200 and other.get(url).status_code==403
        poll=post(agent,'/management/agent/poll',{'results':[{'id':command,'ok':True,'status':'prepared'}]}).json()
        assert not poll['commands']
        assert next(c for c in admin.get('/api/management/commands').json() if c['id']==command)['status']=='prepared'
        post(agent,'/management/agent/poll',{'results':[{'id':command,'ok':True,'message':'Restarted'}]})
        assert next(c for c in admin.get('/api/management/commands').json() if c['id']==command)['status']=='done'

def test_passive_previews_and_current_station(monkeypatch):
    with TestClient(app) as admin,TestClient(app) as agent,TestClient(app) as student:
        login(admin,'admin');row=register(agent);login(student,'student')
        assert student.get('/api/management/previews').status_code==403
        assert not post(agent,'/management/agent/poll').json()['desktop']
        assert admin.get('/api/management/previews').status_code==200
        report=post(agent,'/management/agent/poll',{'frame':'data:image/jpeg;base64,dGVzdA=='}).json()
        assert report['desktop'] and report['inputs']==[]
        assert admin.get('/api/management/previews').json()[row['id']]
        management.previews[row['id']]=time.time()-1
        assert not post(agent,'/management/agent/poll').json()['desktop']
        admin.headers['X-Workstation']=row['token']
        assert next(d for d in admin.get('/api/management/devices').json() if d['id']==row['id'])['current']
        assert post(admin,f'/management/devices/{row["id"]}/desktop').status_code==409

def test_teacher_device_scope_and_remote_revocation():
    from apps.api.app.classroom_models import Workstation
    from apps.api.app import main as m
    from sqlalchemy import select
    with TestClient(app) as teacher,TestClient(app) as agent,TestClient(app) as admin:
        login(teacher,'teacher');login(admin,'admin');row=register(agent);prefix=f'/management/devices/{row["id"]}'
        assert teacher.get('/api/management/previews').status_code==200
        assert next(d for d in teacher.get('/api/management/devices').json() if d['id']==row['id'])['metrics']=={}
        assert post(teacher,prefix+'/action',{'kind':'close'}).status_code==403
        assert post(teacher,prefix+'/action',{'kind':'remove'}).status_code==403
        assert post(teacher,prefix+'/ai',{'mode':'cpu'}).status_code==403
        assert post(teacher,prefix+'/action',{'kind':'logout'}).status_code==200
        token=post(teacher,prefix+'/desktop').json()['token']
        assert post(teacher,prefix+'/desktop/'+token+'/input',{'kind':'key','key':'Tab'}).status_code==200
        assert post(agent,'/management/agent/poll').json()['control']
        with SessionLocal() as db:
            w=db.get(Workstation,row['id']);w.user_id=db.scalar(select(m.User.id).where(m.User.role=='admin'));db.commit()
        assert teacher.get('/api'+prefix+'/desktop/'+token).status_code==403
        assert row['id'] not in teacher.get('/api/management/previews').json()
        poll=post(agent,'/management/agent/poll').json()
        assert not poll['control'] and not poll['inputs']

def test_server_display_name_is_persistent():
    from apps.api.app.server_identity import identity
    with TestClient(app) as admin,TestClient(app) as teacher:
        login(admin,'admin');login(teacher,'teacher')
        assert post(teacher,'/management/server-name',{'name':'Forbidden'}).status_code==403
        assert post(admin,'/management/server-name',{'name':'   '}).status_code==400
        assert post(admin,'/management/server-name',{'name':' Кабинет 204 '}).status_code==200
        assert identity()=={'name':'Кабинет 204','named':True}
        assert teacher.get('/api/classroom/connection').json()['name']=='Кабинет 204'
