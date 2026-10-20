"""Conversation lifecycle regression tests; use test_flows' isolated database."""
import copy
import json
import uuid
import wave
from pathlib import Path
import pytest
from test_flows import app,TestClient,login,post,command,SessionLocal
from apps.api.app import ai_routes,voice,call_audio
from apps.api.app.db import Attempt,ScheduledEvent
from local_ai.dds_dialogue import closing,reply,accepted_response


@pytest.mark.parametrize('text,end',[
    ('До свидания!',True),('досвиданья',True),('Ну позвоните, как приедете',True),
    ('Пока стойте на месте',False),('Не вешайте трубку',False),('Вы уже приехали?',False),
    ('Пока не прощаемся',False),('Когда позвоните?',False),('да',False)])
def test_closing_is_explicit(text,end):
    assert bool(closing(text)) is end


def test_repeat_dispatch_does_not_close_incoming():
    contact={'id':'b','name':'Старший','response':'Приняли, выезжаем.'}
    state={'messages':[{'contact_id':'b','direction':'incoming','who':'Старший','text':'Стоим в пробке.'}]}
    out=reply('Выезжайте скорее',{},contact,state,[{'id':'dispatch','question':'Выезд','answer':contact['response']}],
              lambda *a,**k:({'id':'dispatch','text':'Пока стоим в пробке.'},{'model':'fixture'}))
    assert not out['call_end'] and out['question_id']=='unknown'

@pytest.mark.parametrize('text,end',[
    ('Заявку приняли, выезжаем.',True),('Информацию получили. Машина направлена.',True),
    ('Не можем принять. Уточните адрес.',False),('Повторите, вас не слышно.',False)])
def test_only_confirmed_acceptance_ends_call(text,end):
    assert accepted_response(text) is end


def start(c):
    login(c,'student')
    t=next(t for t in c.get('/api/tutorials').json() if t['key']=='dds-1')
    p=post(c,f"/tutorials/{t['version_id']}/start").json()
    with SessionLocal() as db:
        row=db.get(Attempt,p['id']);state=copy.deepcopy(row.state)
        state['guided']=False;state['text_only']=False;state.pop('mini_started',None)
        row.state=state;row.status='active';db.commit()
    return c.get('/api/attempts/'+str(p['id'])).json()


def send(c,p,text,**extra):
    return post(c,f'/ai/attempts/{p["id"]}/contact',{'contact_id':p['task']['contacts'][0]['id'],
        'text':text,'revision':p['revision'],'command_id':str(uuid.uuid4()),**extra})


def test_multiturn_dispatch_goodbye_and_speech_authorization(monkeypatch,tmp_path):
    calls=[]
    def infer(*a,**k):
        calls.append(json.loads(a[1]));return {'id':'unknown','text':'Пока стоим, объезд закрыт.'},{'model':'test','seconds':.1}
    monkeypatch.setattr(ai_routes,'dialogue_complete',infer)
    def synth(text,gender='male',**kwargs):
        p=tmp_path/(uuid.uuid4().hex+'.wav')
        with wave.open(str(p),'wb') as w:w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(b'\0\0'*100)
        return p,{'seconds':.01,'voice':kwargs['settings']['tts']}
    monkeypatch.setattr(voice.runtime,'synthesize',synth)
    with TestClient(app) as c:
        p=start(c)
        r=send(c,p,'Примите заявку, выезжайте');assert r.status_code==200,r.text
        p=r.json();answer=p['state']['messages'][-1]
        assert answer['call_end'] and answer['audio'] and not calls
        assert c.get('/api/media/'+answer['audio']).status_code==200
        # A new incoming report replaces the initial departure context.
        with SessionLocal() as db:
            row=db.get(Attempt,p['id']);state=copy.deepcopy(row.state)
            state['messages'].append({'who':'Старший','text':'Стоим в пробке, объезд перекрыт.',
                                      'contact_id':p['task']['contacts'][0]['id'],'direction':'incoming'})
            row.state=state;db.commit()
        for text in ('Включите сирену','А через двор?','да'):
            r=send(c,p,text);assert r.status_code==200,r.text;p=r.json()
            assert not p['state']['messages'][-1]['call_end']
        assert 'пробке' in calls[0]['current_report'] and len(calls[-1]['history'])<=2
        r=send(c,p,'Позвоните как приедете');assert r.status_code==200,r.text
        p=r.json();assert p['state']['messages'][-1]['call_end']
        assert len(calls)==3
        # Raw client commands cannot inject an answer, intent, audio, or call outcome.
        forged=post(c,f'/attempts/{p["id"]}/command',{'type':'contact','revision':p['revision'],
            'command_id':str(uuid.uuid4()),'payload':{'id':p['task']['contacts'][0]['id'],'text':'Вопрос','question_id':'unknown','answer':'Прибыли'}})
        assert forged.status_code==403
        command(c,p,'abort')


def test_cancelled_session_never_commits_answer(monkeypatch):
    with TestClient(app) as c:
        p=start(c);sid='cancelled-test-session'
        path=f'/call-audio/attempts/{p["id"]}/line'
        assert post(c,path,{'session':sid,'active':True}).status_code==200
        def infer(*a,**k):
            post(c,path,{'session':sid,'active':False})
            return {'id':'unknown','text':'Пока стоим.'},{'model':'test'}
        monkeypatch.setattr(ai_routes,'dialogue_complete',infer)
        # Keep this test independent of actual synthesis.
        with SessionLocal() as db:
            row=db.get(Attempt,p['id']);row.state={**row.state,'text_only':True};db.commit()
        r=send(c,p,'Можно объехать?',session=sid)
        assert r.status_code==409,r.text
        latest=c.get('/api/attempts/'+str(p['id'])).json()
        assert latest['revision']==p['revision'] and latest['state']['messages']==p['state']['messages']
        command(c,latest,'abort')


def test_thread_settings_validation_and_roles():
    with TestClient(app) as c:
        login(c,'admin')
        r=post(c,'/voice/dialogue-settings',{'dialogue_threads':4,'stt_threads':2,'tts_threads':2})
        assert r.status_code==200 and r.json()['dialogue_threads']==4
        for bad in (0,17,True,2.5):assert post(c,'/voice/dialogue-settings',{'stt_threads':bad}).status_code==400
        login(c,'student')
        assert post(c,'/voice/dialogue-settings',{'dialogue_threads':8}).status_code==403
