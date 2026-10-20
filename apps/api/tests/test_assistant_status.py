"""Teacher assistant: the state of a ticket and the progress of voicing."""
import pytest
from test_flows import app, TestClient, login, post, SessionLocal

def ask(c,text,page='/tickets',dialog=None,**context):
    r=post(c,'/assistant/interpret',{'text':text,'context':{'page':page,**context},**({'dialog':dialog} if dialog else {})})
    assert r.status_code==200,r.text
    return r.json()

@pytest.fixture
def teacher():
    with TestClient(app) as c:
        login(c,'teacher')
        yield c

def voiced(c):
    from apps.api.app import voice
    return next(v for v in c.get('/api/tickets').json() if v['published'] and not v['archived'] and v['data']['tasks'][0]['mode']=='dds' and voice.keys({'tasks':v['data']['tasks']}))

def test_ticket_status_tells_publication_and_voicing(teacher):
    from apps.api.app import voice
    v=voiced(teacher)
    r=ask(teacher,f'какой статус у билета {v["ticket_id"]}')
    assert r['intent']=='ticket_status' and f'Билет № {v["ticket_id"]}' in r['preview'] and 'опубликован' in r['preview']
    assert 'Озвучен полностью' in r['preview'] and 'Озвучка: озвучка' not in r['preview']
    key=next(iter(voice.keys(v['data'])))
    with SessionLocal() as db:db.get(voice.VoiceJob,key).status='pending';db.commit()
    try:
        r=ask(teacher,f'готова ли озвучка билета {v["ticket_id"]}')
        assert r['intent']=='ticket_status' and 'Озвучка ' in r['preview'] and 'текстом' in r['preview'],r['preview']
        r=ask(teacher,'статус билета',page=f'/tickets/{v["id"]}')
        assert r['intent']=='ticket_status' and f'№ {v["ticket_id"]}' in r['preview']
        r=ask(teacher,'статус билета',page='/',version_id=v['id'])
        assert f'№ {v["ticket_id"]}' in r['preview'],'the ticket the assistant worked with last'
        r=ask(teacher,'статус билета',page='/')
        assert r['missing'] and r['missing'][0]['slot']=='ticket'
        q=ask(teacher,'как идёт озвучка')
        assert q['intent']=='voice_queue' and 'В очереди озвучки' in q['preview'] and f'№ {v["ticket_id"]}' in q['preview']
    finally:
        with SessionLocal() as db:db.get(voice.VoiceJob,key).status='ready';db.commit()

def test_retry_failed_voicing(teacher):
    from apps.api.app import voice
    with SessionLocal() as db:
        spec={'owner':1,'speaker_id':'brigade','gender':'male','settings':voice.runtime.settings()['pre']}
        db.add(voice.VoiceJob(id='status-failed-1',status='failed',error='сбой',data={**spec,'text':'Сбойная реплика'}));db.commit()
    q=ask(teacher,'есть ошибки озвучки?')
    assert q['intent']=='voice_queue' and 'ошибок' in q['preview'] and 'повтори озвучку с ошибками' in q['preview']
    r=ask(teacher,'повтори озвучку с ошибками')
    assert r['intent']=='voice_retry' and r['slots']['count']>=1
    with SessionLocal() as db:assert db.get(voice.VoiceJob,'status-failed-1').status=='pending'
    assert 'Ошибок озвучки нет' in ask(teacher,'перезапусти неудачную озвучку')['preview']
