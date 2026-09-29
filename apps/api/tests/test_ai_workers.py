import threading
import time
import uuid
from test_flows import app,TestClient,login,post,HEAD
from apps.api.app.ai_workers import Broker
from local_ai.engine import LocalEngine

SCHEMA={'type':'object','properties':{'id':{'type':'string','enum':['yes']}},'required':['id']}


def test_broker_assigns_each_job_to_one_authorized_worker():
    b=Broker(lambda:{'worker_ids':['a','b']},timeout=2)
    b.poll('a',True);b.poll('b',True)
    out=[]
    threads=[threading.Thread(target=lambda:out.append(b.dispatch('system','text',SCHEMA,12,0))) for _ in range(2)]
    for t in threads:t.start()
    jobs={wid:b.poll(wid,True) for wid in ('a','b')}
    assert all(jobs.values()) and jobs['a']['id']!=jobs['b']['id']
    assert all(job['model']=='models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf' for job in jobs.values())
    assert not b.finish('b',jobs['a']['id'],{'id':'yes'},'')
    assert b.poll('unauthorized',True) is None
    for wid,j in jobs.items():assert b.finish(wid,j['id'],{'id':'yes'},'')
    for t in threads:t.join(3)
    assert len(out)==2 and all(r[1]['execution']=='workstation' for r in out)
    assert not b.jobs


def test_offline_invalid_and_late_worker_results_fall_back():
    b=Broker(lambda:{'worker_ids':['a']},timeout=.08)
    assert b.dispatch('s','p',SCHEMA,12,0) is None
    b.poll('a',True)
    out=[]
    t=threading.Thread(target=lambda:out.append(b.dispatch('s','p',SCHEMA,12,0)));t.start()
    job=b.poll('a',True);t.join(1)
    assert out==[None] and not b.finish('a',job['id'],{'id':'yes'},'')
    t=threading.Thread(target=lambda:out.append(b.dispatch('s','p',SCHEMA,12,0)));t.start()
    job=b.poll('a',True)
    assert b.finish('a',job['id'],{'id':'malformed'},'')
    t.join(1);assert out==[None,None]


def test_worker_access_and_user_roles_do_not_depend_on_machine(monkeypatch):
    from local_ai.engine import engine
    settings={'execution':'server','worker_ids':[]}
    original=engine.config
    monkeypatch.setattr(engine,'config',lambda:{**original(),**settings})
    monkeypatch.setattr(engine,'set_settings',lambda **kw:settings.update(kw))
    with TestClient(app) as admin,TestClient(app) as pc:
        login(admin,'admin')
        w=post(pc,'/classroom/register',{'number':'worker-'+uuid.uuid4().hex[:8]}).json()
        pc.headers['X-Workstation']=w['token']
        assert post(pc,'/ai/workers/poll',{'available':True}).status_code==403
        admin.patch('/api/classroom/stations/'+w['id'],json={'approved':True},headers=HEAD)
        for role in ('admin','teacher','student'):
            login(pc,role)
            assert pc.get('/api/me').json()['role']==role
        assert post(pc,'/ai/execution',{'execution':'workstations','worker_ids':[w['id']]}).status_code==403
        assert post(admin,'/ai/execution',{'execution':'workstations','worker_ids':[w['id']]}).status_code==200
        assert post(pc,'/ai/workers/poll',{'available':True}).json()=={'job':None}
        assert pc.get('/api/ai/workers').status_code==403
        admin.patch('/api/classroom/stations/'+w['id'],json={'blocked':True},headers=HEAD)
        assert post(pc,'/ai/workers/poll',{'available':True}).status_code==403


def test_gpu_and_execution_settings_persist(tmp_path,monkeypatch):
    import json
    root=tmp_path/'ai';(root/'runtime/vulkan').mkdir(parents=True)
    (root/'models').mkdir()
    (root/'models/Qwen3-0.6B-Q4_K_M.gguf').touch()
    (root/'models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf').touch()
    (root/'runtime/vulkan/llama-server.exe').touch()
    (root/'config.json').write_text(json.dumps({'model':'models/Qwen3-0.6B-Q4_K_M.gguf','mode':'cpu','threads':6,'context':4096}))
    e=LocalEngine(root,tmp_path/'data')
    monkeypatch.setattr(e,'gpu_devices',lambda:[{'id':'Vulkan0','name':'Test GPU'}])
    e.set_settings(mode='gpu',execution='workstations',worker_ids=['a'])
    assert e.config()['mode']=='gpu' and e.config()['worker_ids']==['a']
    assert e.status()['gpu_available']
    e.set_settings(model='models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf')
    assert e.config()['model']=='models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
    e.set_settings(model='models/Qwen3-0.6B-Q4_K_M.gguf')
    assert e.config()['model']=='models/Qwen3-0.6B-Q4_K_M.gguf'
    with __import__('pytest').raises(ValueError):e.set_settings(model='models/unknown.gguf')


def test_only_admin_can_choose_default_model(monkeypatch):
    from apps.api.app.ai_routes import ai
    selected=[]
    monkeypatch.setattr(ai,'set_settings',lambda **settings:selected.append(settings))
    with TestClient(app) as client:
        login(client,'student')
        payload={'model':'models/Qwen3-0.6B-Q4_K_M.gguf'}
        assert post(client,'/ai/model',payload).status_code==403
        login(client,'admin')
        assert post(client,'/ai/model',payload).status_code==200
        assert selected==[payload]
        assert post(client,'/ai/model',{'model':'models/unknown.gguf'}).status_code==422
