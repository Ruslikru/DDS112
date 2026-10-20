import asyncio,threading
import pytest
from test_new_student_guidance import classroom
from test_flows import login,post


def test_three_model_paths_start_together(monkeypatch):
    from local_ai.engine import engine,assistant_engine
    from apps.api.app.voice import runtime
    from apps.api.app.startup_models import warm_models
    barrier=threading.Barrier(3,timeout=3);seen=[]
    def ready(name):
        seen.append(name);barrier.wait()
    monkeypatch.setattr(engine,'start',lambda:ready('cards'))
    monkeypatch.setattr(assistant_engine,'start',lambda:ready('assistant'))
    monkeypatch.setattr(runtime,'warm',lambda:ready('speech'))
    asyncio.run(warm_models())
    assert set(seen)=={'cards','assistant','speech'}
    assert not barrier.broken


def ask(c,text,dialog=None):
    r=post(c,'/assistant/interpret',{'text':text,'context':{'page':'/learning'},**({'dialog':dialog} if dialog else {})})
    assert r.status_code==200,r.text
    return r.json()


def test_question_options_are_generated_and_previewed(classroom,monkeypatch):
    from apps.api.app import assistant
    calls=[]
    def generate(prompt,answer):
        calls.append((prompt,answer));return ['Ctrl + F3','Ctrl + F7']
    monkeypatch.setattr(assistant,'generate_question_options',generate)
    login(classroom,'teacher')
    r=ask(classroom,'Создай минивопрос')
    r=ask(classroom,'Какие клавиши обновляют карточку?',{'intent':r['intent'],'slots':{**r['slots'],'answer_slot':'prompt'}})
    r=ask(classroom,'Ctrl + F5',{'intent':r['intent'],'slots':{**r['slots'],'answer_slot':'answer'}})
    assert r['missing'][0]['slot']=='audio_text'
    assert len(calls)==1 and r['slots']['options']==['Ctrl + F5','Ctrl + F3','Ctrl + F7']
    r=ask(classroom,'без озвучки',{'intent':r['intent'],'slots':{**r['slots'],'answer_slot':'audio_text'}})
    assert r['confirm_required'] and all(v in r['preview'] for v in r['slots']['options'])
    saved=post(classroom,'/assistant/execute',{'intent':r['intent'],'slots':r['slots'],'confirm_token':r['confirm_token']})
    assert saved.status_code==200,saved.text


@pytest.mark.parametrize('phrase',['Заново.','Заново, давай сделаем.','Составить заново'])
def test_restart_clears_question_and_audio(classroom,phrase):
    login(classroom,'teacher')
    r=ask(classroom,phrase,{'intent':'create_question','slots':{'prompt':'Старый вопрос','answer':'Старый ответ','options':['Старый ответ','Ошибка'],'options_answered':True,'audio_text':'старый звук','audio_answered':True}})
    assert r['missing'][0]['slot']=='prompt' and not r['slots']


def test_dictated_wrong_options_are_not_regenerated(classroom,monkeypatch):
    from apps.api.app import assistant
    monkeypatch.setattr(assistant,'generate_question_options',lambda *a:pytest.fail('Explicit options must be kept'))
    login(classroom,'teacher')
    r=ask(classroom,'Создай минивопрос: Какие клавиши обновляют карточку? Правильный ответ: Ctrl + F5. Неправильные ответы: Ctrl + F3; Ctrl + F7.')
    assert r['slots']['prompt']=='Какие клавиши обновляют карточку'
    assert r['slots']['answer']=='Ctrl + F5'
    assert r['slots']['options']==['Ctrl + F5','Ctrl + F3','Ctrl + F7']
    assert r['confirm_required']


def test_first_server_entry_is_admin_only(classroom,monkeypatch):
    from apps.api.app import server_identity
    monkeypatch.setenv('ENFORCE_SERVER_NAME','1');monkeypatch.setenv('DEMO_CLASSROOM','1')
    monkeypatch.setattr(server_identity,'_activated',False)
    assert classroom.get('/api/classroom/server-setup').json()['ready'] is False
    assert post(classroom,'/login',{'login':'teacher','password':'Training112!'}).status_code==403
    assert post(classroom,'/login',{'login':'admin','password':'Training112!'}).status_code==200


def test_whole_question_can_be_dictated_after_start(classroom,monkeypatch):
    from apps.api.app import assistant
    monkeypatch.setattr(assistant,'generate_question_options',lambda *a:pytest.fail('Explicit choices should be kept'))
    login(classroom,'teacher')
    start=ask(classroom,'Создай минивопрос')
    r=ask(classroom,'Какие клавиши обновляют карточку? Правильный ответ Ctrl + F5. Неправильные ответы Ctrl + F3; Ctrl + F7.',{'intent':start['intent'],'slots':{**start['slots'],'answer_slot':'prompt'}})
    assert r['confirm_required']
    assert r['slots']['prompt']=='Какие клавиши обновляют карточку'
    assert r['slots']['answer']=='Ctrl + F5'
    assert r['slots']['options']==['Ctrl + F5','Ctrl + F3','Ctrl + F7']
