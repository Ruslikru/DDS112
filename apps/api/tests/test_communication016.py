from test_flows import app,TestClient,login,post,command,SessionLocal,assignment
from sqlalchemy import select
from local_ai.voice import VoiceRuntime
import pytest

@pytest.mark.parametrize('text',['Повторите, пожалуйста, адрес свой.','Скажите адрес.','Назовите точный адрес.','адрес ваш','Где это произошло?'])
def test_address_is_a_fact_not_a_model_guess(tmp_path,text):
    runtime=VoiceRuntime(tmp_path)
    value=runtime.classify(text,{'questions':[{'id':'address','question':'Адрес?','answer':'Москва, улица Декабристов, дом 28.'},{'id':'details','question':'Что произошло?','answer':'Дым в подъезде.'}]})
    assert value['id']=='address' and 'Декабристов' in value['text']
    assert runtime.llm is None

def test_intro_brigade_calls_back_and_conversation_is_reviewed():
    from apps.api.app.db import ScheduledEvent,Attempt
    from apps.api.app.main import process_events
    with TestClient(app) as c:
        login(c,'student');t=next(t for t in c.get('/api/tutorials').json() if t['key']=='dds-1')
        p=post(c,f"/tutorials/{t['version_id']}/start").json()
        p=command(c,p,'contact',{'id':'brigade','text':'Москва, Декабристов, дом 28. Дым в подъезде. Пострадавших нет.'})
        for stage, statuses in [('arrived',['Принята','Начало реагирования']),('done',['Прибытие','Проведение работ'])]:
            # Even overdue calls must wait for the student's card progress.
            with SessionLocal() as db:
                a=db.get(Attempt,p['id']);a.state={**a.state,'brigade_next_at':0}
                for event in db.scalars(select(ScheduledEvent).where(ScheduledEvent.attempt_id==p['id'],ScheduledEvent.done==False)):event.due=0
                db.commit();process_events(db)
            p=c.get('/api/attempts/'+str(p['id'])).json()
            assert not p['state']['incoming_calls']
            for status in statuses:p=command(c,p,'status',{'status':status,'comment':''})
            with SessionLocal() as db:
                a=db.get(Attempt,p['id']);a.state={**a.state,'brigade_next_at':0}
                event=next(e for e in db.scalars(select(ScheduledEvent).where(ScheduledEvent.attempt_id==p['id'])) if e.data.get('stage')==stage)
                event.due=0;db.commit();process_events(db)
            p=c.get('/api/attempts/'+str(p['id'])).json()
            p=command(c,p,'accept_dds_call',{'id':p['state']['incoming_calls'][0]['id']})
            assert stage in p['state']['received_stages'] and p['state']['messages'][-1]['audio']
        assert p['state']['contact_counts']['brigade']==1
        p=command(c,p,'status',{'status':'Работы завершены','comment':'По докладу бригады'})
        p=command(c,p,'finish')
        rubric=next(q for q in p['assessment']['criteria'] if q['id']=='phone_conversation')
        assert rubric['passed'] is None and 'Декабристов' in rubric['actual']
        login(c,'teacher')
        assert any(a['student_id']==p['student_id'] for a in c.get('/api/assignments').json())
        r=post(c,f"/attempts/{p['id']}/review",{'criteria':{'phone_conversation':True},'reason':'Адрес и обстоятельства переданы верно.'})
        assert r.status_code==200
        assert next(q for q in r.json()['assessment']['criteria'] if q['id']=='phone_conversation')['teacher_reviewed']

def test_audio_mini_question_queue_privacy_and_playback():
    from apps.api.app import voice
    from apps.api.app.learning import profile
    from apps.api.app.classroom_models import MiniQuestion
    with TestClient(app) as c:
        login(c,'admin')
        result=post(c,'/learning/questions',{'prompt':'Напечатайте услышанный адрес','kind':'text','answer':'Декабристов, 28','audio_text':'Декабристов, дом 28','level':0}).json()
        assert result['audio_status']=='pending' and not result['audio_id']
        voice.recover()
        q=next(q for q in c.get('/api/learning/questions').json() if q['id']==result['id'])
        assert q['audio_status']=='ready' and q['audio_id']
        login(c,'student');a=assignment(c,'Задымление');p=post(c,f"/assignments/{a['id']}/start").json()
        with SessionLocal() as db:
            person=profile(db,p['student_id']);question=db.get(MiniQuestion,q['id'])
            person.data={**person.data,'pending_drill':{'id':question.id,'attempt':p['id'],'data':question.data}};db.commit()
        offered=post(c,f"/learning/drill/{p['id']}").json()
        assert offered['audio_id']==q['audio_id']
        assert not {'answer','audio_text','voice_key'} & offered.keys()
        assert c.get('/api/media/'+q['audio_id']).content.startswith(b'RIFF')
        assert post(c,'/learning/drill-answer',{'id':q['id'],'answer':'Декабристов, 28'}).json()['correct']
        command(c,p,'abort')
