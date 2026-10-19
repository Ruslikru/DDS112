import copy
from types import SimpleNamespace
import pytest
from test_flows import app, TestClient, login, post
from apps.api.app import call_audio as audio

def test_scenes_follow_location_and_call_stage():
    task={'own_service':'Служба 101','initial_card':{'incident_type':'Пожар'},'contacts':[{'id':'b','kind':'brigade','name':'Старший учебной бригады'}],
          'service_events':[{'kind':'incoming_call','contact_id':'b','text':'Прибыли к горящему дому'}, {'kind':'incoming_call','contact_id':'b','text':'Попали в пробку, задерживаемся'}]}
    audio.prepare_task(task)
    assert task['contacts'][0]['name']=='Старший бригады'
    assert task['contacts'][0]['call_audio']['backgrounds']==['bg_fire_station']
    assert task['service_events'][0]['call_audio']['backgrounds']==['bg_fire_scene']
    assert task['service_events'][1]['call_audio']['backgrounds']==['bg_vehicle_interior']
    assert audio.scene(task,{'kind':'brigade'}, {'text':'Пожар','location':'office'})['backgrounds']==['bg_dispatch_office']
    assert audio.prepare_task(copy.deepcopy(task))==task
    audio.ensure_assets(task)

def test_all_assets_verified_and_fire_scene_long():
    for key in audio.library():assert audio.asset(key)['bytes']>44
    assert audio.asset('bg_fire_scene')['seconds']>60

def test_busy_lease_and_post_call_gap(monkeypatch):
    now=[100.0];monkeypatch.setattr(audio.time,'monotonic',lambda:now[0])
    db=SimpleNamespace(get=lambda model,id:SimpleNamespace(student_id=20))
    user=SimpleNamespace(id=20,role='student')
    audio.update_line(999001,audio.LineState(session='test-call-1',active=True),user,db)
    assert audio.line_busy(999001)
    with pytest.raises(Exception):audio.update_line(999001,audio.LineState(session='test-call-2',active=True),user,db)
    audio.update_line(999001,audio.LineState(session='test-call-1',active=False),user,db)
    now[0]+=2;assert audio.line_busy(999001)
    now[0]+=1;assert not audio.line_busy(999001)


def test_student_microphone_uses_gigaam(monkeypatch):
    from apps.api.app import voice
    seen={}
    def transcribe(data,**kwargs):
        seen.update(kwargs);return {'text':'???????? ?????????'}
    monkeypatch.setattr(voice.runtime,'transcribe',transcribe)
    with TestClient(app) as client:
        login(client,'student')
        result=post(client,'/voice/transcribe',{'audio':'data:audio/wav;base64,AAAA'})
        assert result.status_code==200,result.text
        assert seen=={'model':'gigaam','prompt':''}


def test_scheduled_incoming_waits_for_current_call_and_gap():
    import time
    from test_flows import SessionLocal
    from apps.api.app import main
    from apps.api.app.db import Attempt,ScheduledEvent
    with TestClient(app) as client:
        login(client,'teacher')
        ticket=client.get('/api/tutorials').json()[0]
        attempt=post(client,f"/tickets/{ticket['version_id']}/try",{'task_index':0}).json()
        attempt_id=attempt['id']
        assert post(client,f'/call-audio/attempts/{attempt_id}/line',{'session':'incoming-test','active':True}).status_code==200
        with SessionLocal() as db:
            event=ScheduledEvent(attempt_id=attempt_id,due=time.time()-1,data={'kind':'incoming_call','contact_id':'brigade','who':'??????? ???????','text':'?? ???????'})
            db.add(event);db.commit();event_id=event.id
            main.process_events(db);db.refresh(event);assert not event.done
        assert post(client,f'/call-audio/attempts/{attempt_id}/line',{'session':'incoming-test','active':False}).status_code==200
        with SessionLocal() as db:
            main.process_events(db);assert not db.get(ScheduledEvent,event_id).done
            audio._lines[attempt_id]['until']=time.monotonic()-1
            main.process_events(db);db.expire_all()
            assert db.get(ScheduledEvent,event_id).done
            assert len(db.get(Attempt,attempt_id).state['incoming_calls'])==1
