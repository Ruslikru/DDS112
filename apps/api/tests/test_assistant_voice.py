"""Teacher assistant, voice stage: server-side transcription route and clean-up of recognised speech."""
import base64
import pytest
from test_flows import app, TestClient, login, post
from apps.api.app import voice
from apps.api.app.assistant import clean_speech

def test_transcribe_route_uses_runtime_and_requires_staff(monkeypatch):
    seen=[]
    def fake(content):seen.append(content);return {'text':' Покажи журнал. ','seconds':.2,'model':'tiny'}
    monkeypatch.setattr(voice.runtime,'transcribe',fake)
    audio=base64.b64encode(b'webm-bytes').decode()
    with TestClient(app) as c:
        login(c,'teacher')
        r=post(c,'/voice/transcribe',{'audio':audio});assert r.status_code==200,r.text
        assert r.json()=={'seconds':.2,'model':'tiny','text':'Покажи журнал.'} and seen==[audio]
        assert post(c,'/voice/transcribe',{'audio':''}).status_code==422
        post(c,'/logout');login(c,'student')
        assert post(c,'/voice/transcribe',{'audio':audio}).status_code==403

def test_transcribe_length_limit_and_missing_module(monkeypatch):
    with TestClient(app) as c:
        login(c,'teacher')
        r=post(c,'/voice/transcribe',{'audio':'A'*16000001})
        assert r.status_code==400 and 'слишком длинная' in r.json()['detail']
        monkeypatch.setattr(voice.runtime,'transcribe',lambda content:(_ for _ in ()).throw(RuntimeError('Голосовой модуль не установлен рядом с приложением (local_ai/voice).')))
        r=post(c,'/voice/transcribe',{'audio':'QUJD'})
        assert r.status_code==503 and 'Голосовой модуль не установлен' in r.json()['detail']

def test_empty_recording_is_not_reported_as_outage(monkeypatch):
    """Whisper reports silence as an error string; the teacher gets a hint about holding the button, not a 503."""
    monkeypatch.setattr(voice.runtime,'transcribe',lambda content:(_ for _ in ()).throw(RuntimeError('Речь не распознана. Повторите запись.')))
    with TestClient(app) as c:
        login(c,'teacher')
        r=post(c,'/voice/transcribe',{'audio':'QUJD'})
        assert r.status_code==400 and 'Удерживайте кнопку' in r.json()['detail'] and 'недоступно' not in r.json()['detail']

@pytest.mark.parametrize('spoken,cleaned',[
 ('Покажи журнал.','Покажи журнал'),
 ('Где сидит Кузнецов?','Где сидит Кузнецов'),
 ('Подключениек Кузнецову.','Подключение к Кузнецову'),
 ('Покажина рабочие места!','Покажи на рабочие места'),
 ('  открой   билеты…  ','открой билеты'),
 ('Ученик Кузнецов','Ученик Кузнецов'),
])
def test_recognised_speech_is_cleaned(spoken,cleaned):
    assert clean_speech(spoken)==cleaned

def test_spoken_commands_still_parse():
    with TestClient(app) as c:
        login(c,'teacher')
        r=post(c,'/assistant/interpret',{'text':'Покажи журнал.','context':{'page':'/'}}).json()
        assert r['intent']=='open_page' and r['action']['to']=='/journal'
        r=post(c,'/assistant/interpret',{'text':'Не надо открывать журнал!','context':{'page':'/'}}).json()
        assert r['intent']=='unknown' and r['action'] is None
