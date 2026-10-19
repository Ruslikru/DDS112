"""Teacher assistant: command parsing uses the small assistant model, ticket generation keeps the main one; test catalogue refuses creation."""
import json
import pytest
from test_flows import app, TestClient, login, post
from local_ai.engine import LocalEngine, AssistantEngine, FAST_MODEL, DEFAULT_MODEL

def engine_root(tmp_path,files):
    root=tmp_path/'ai';(root/'runtime/cpu').mkdir(parents=True);(root/'models').mkdir()
    for name in files:(root/'models'/name).touch()
    (root/'runtime/cpu/llama-server.exe').touch()
    (root/'config.json').write_text(json.dumps({'model':DEFAULT_MODEL,'mode':'cpu','threads':6,'context':4096}))
    return root

def test_assistant_model_defaults_to_fast_and_falls_back_when_missing(tmp_path):
    root=engine_root(tmp_path,['Qwen3-0.6B-Q4_K_M.gguf','Qwen3-4B-Instruct-2507-Q4_K_M.gguf'])
    e=LocalEngine(root,tmp_path/'data')
    assert e.config()['assistant_model']==FAST_MODEL and e.status()['assistant_model_id']==FAST_MODEL
    e.set_settings(assistant_model=DEFAULT_MODEL)
    assert e.config()['assistant_model']==DEFAULT_MODEL
    with pytest.raises(ValueError):e.set_settings(assistant_model='models/nope.gguf')
    second=AssistantEngine(e)
    assert second.config()['model']==DEFAULT_MODEL and second.config()['threads']==6
    (root/'models/Qwen3-0.6B-Q4_K_M.gguf').unlink()
    e.set_settings(assistant_model=DEFAULT_MODEL);(tmp_path/'data'/'ai-settings.json').write_text(json.dumps({**e.config(),'assistant_model':FAST_MODEL}))
    assert e.config()['assistant_model']==DEFAULT_MODEL,'a missing assistant model file silently means the main model'

def test_ask_model_goes_to_assistant_engine(monkeypatch):
    from apps.api.app import ai_routes, assistant_tickets, scenario_wizard
    calls=[]
    monkeypatch.setattr(ai_routes.ai,'config',lambda:{'model':DEFAULT_MODEL,'assistant_model':FAST_MODEL})
    monkeypatch.setattr(ai_routes.assistant_ai,'complete',lambda *a,**kw:(calls.append('assistant') or ({'incident':'лифт','victims':'no','victims_count':0,'difficulty':2,'mode':'dds'},{'model':'fast'})))
    monkeypatch.setattr(ai_routes.ai,'complete',lambda *a,**kw:(calls.append('main') or ({'description':'Лифт остановился между этажами. Доступ свободен.'},{'model':'main'})))
    monkeypatch.setattr(scenario_wizard,'complete',lambda *a,**kw:(calls.append('wizard') or ({'description':'Лифт остановился между этажами. Доступ свободен.'},{'model':'main'})))
    with TestClient(app) as c:
        login(c,'teacher')
        r=post(c,'/assistant/interpret',{'text':'создай билет, кабина застряла между этажами','context':{'page':'/'}}).json()
        assert calls==['assistant'] and r['slots']['incident_type']=='лифт'
        # When both settings name the same model there is no second server: the main engine answers.
        monkeypatch.setattr(ai_routes.ai,'config',lambda:{'model':DEFAULT_MODEL,'assistant_model':DEFAULT_MODEL})
        post(c,'/assistant/interpret',{'text':'создай билет, кабина застряла между этажами','context':{'page':'/'}})
        assert calls==['assistant','main']

def test_assistant_model_route_is_admin_only(monkeypatch):
    from apps.api.app import ai_routes
    saved=[]
    monkeypatch.setattr(ai_routes.ai,'set_settings',lambda **kw:saved.append(kw))
    monkeypatch.setattr(ai_routes.assistant_ai,'stop',lambda:saved.append('stopped'))
    with TestClient(app) as c:
        login(c,'teacher')
        assert post(c,'/ai/assistant-model',{'model':FAST_MODEL}).status_code==403
        post(c,'/logout');login(c,'admin')
        assert post(c,'/ai/assistant-model',{'model':FAST_MODEL}).status_code==200
        assert saved==[{'assistant_model':FAST_MODEL},'stopped']

def test_test_catalog_refuses_ticket_creation(monkeypatch):
    from apps.api.app import assistant_tickets
    monkeypatch.setattr(assistant_tickets,'complete',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('no model call expected')))
    with TestClient(app) as c:
        login(c,'teacher')
        monkeypatch.setenv('TRAINING_CATALOG','two-dds')
        r=post(c,'/assistant/interpret',{'text':'создай билет про лифт для ДДС района на 1 звезду без пострадавших','context':{'page':'/'}}).json()
        assert r['intent']=='create_ticket' and 'тестовом каталоге' in r['preview'] and not r['confirm_required'] and not r['confirm_token'] and not r['missing']
        failed=post(c,'/assistant/execute',{'intent':'create_ticket','slots':{},'confirm_token':'1.x'})
        assert failed.status_code in (400,403)
        monkeypatch.setenv('TRAINING_CATALOG','full')
        r=post(c,'/assistant/interpret',{'text':'создай билет про лифт для ДДС района на 1 звезду без пострадавших','context':{'page':'/'}}).json()
        assert r['confirm_required'],'the full catalogue keeps working'
