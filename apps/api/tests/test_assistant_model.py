"""One Qwen 4B handles command extraction, authoring and conversations."""
import json
import pytest
from test_flows import app,TestClient,login,post
from local_ai.engine import LocalEngine,DEFAULT_MODEL


def test_old_settings_migrate_to_one_model_without_adapter(tmp_path):
    root=tmp_path/'ai';(root/'models').mkdir(parents=True)
    (root/DEFAULT_MODEL).touch()
    (root/'config.json').write_text(json.dumps({'model':DEFAULT_MODEL,'assistant_model':'models/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf','mode':'cpu','threads':6,'context':4096}))
    engine=LocalEngine(root,tmp_path/'data')
    assert engine.config()['assistant_model']==DEFAULT_MODEL
    assert engine.status()['assistant_available']
    assert len(engine.status()['models'])==1
    with pytest.raises(ValueError):engine.set_settings(assistant_model='models/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf')
    engine.set_settings(threads=6)
    assert engine.config()['threads']==6


def test_all_text_routes_share_one_engine(monkeypatch):
    from apps.api.app import ai_routes,prompt_ticket,scenario_wizard,assistant_tickets
    from local_ai.voice import VoiceRuntime
    calls=[]
    monkeypatch.setattr(ai_routes.ai,'complete',lambda *a,**kw:(calls.append(a[0]) or ({'incident':'лифт'},{'model':'Qwen4B'})))
    assert ai_routes.get_dialogue_engine() is ai_routes.ai
    for name,call in [('assistant',assistant_tickets.complete),('phone',ai_routes.dialogue_complete),('ticket',prompt_ticket.complete),('wizard',scenario_wizard.complete)]:
        call(name,'test',{})
    assert calls==['assistant','phone','ticket','wizard']


def test_online_command_does_not_use_llm(monkeypatch):
    from apps.api.app import ai_routes
    monkeypatch.setattr(ai_routes.ai,'complete',lambda *a,**kw:pytest.fail('Rules command must not call a model'))
    with TestClient(app) as client:
        login(client,'teacher')
        result=post(client,'/assistant/interpret',{'text':'Кто из студентов сейчас онлайн?','context':{'page':'/'}})
        assert result.status_code==200
        assert result.json()['intent']=='who_online'


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
