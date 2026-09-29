"""Cross-client authorization, teacher memory, live card handoff and adaptive limits."""
import copy
import time
import uuid
from test_flows import app, TestClient, login, post, command, HEAD, SessionLocal
from sqlalchemy import select
from apps.api.app.db import User, Attempt, Assignment, TicketVersion, Lesson
from apps.api.app.classroom_models import TrainingProfile, ApprovedAnswer

def test_single_pc_demo_admits_registered_students(monkeypatch):
    monkeypatch.setenv('DEMO_CLASSROOM','1')
    monkeypatch.setenv('ENFORCE_WORKSTATIONS','1')
    with TestClient(app) as student:
        station=post(student,'/classroom/register',{'number':'demo-'+uuid.uuid4().hex[:8]}).json()
        student.headers['X-Workstation']=station['token']
        assert not student.get('/api/classroom/admission').json()['approved']
        login(student,'admin')
        assert post(student,'/classroom/demo-number',{'number':'901'}).status_code==200
        assert {'student1','student2','student3','student4','student5'} <= {u['login'] for u in student.get('/api/users').json()}
        assert student.get('/api/classroom/admission').json()['approved']
        post(student,'/logout')
        login(student,'student')
        assert student.get('/api/me').json()['role']=='student'
    with TestClient(app) as restarted:
        restarted.headers['X-Workstation']=station['token']
        assert not restarted.get('/api/classroom/admission').json()['configured']
        assert restarted.post('/api/login',json={'login':'student5','password':'12345678'},headers=HEAD).status_code==403

def test_station_list_includes_server_and_unlogged_workstation(monkeypatch):
    with TestClient(app) as server,TestClient(app) as workstation:
        login(server,'admin')
        server_row=post(server,'/classroom/register',{'number':'server-'+uuid.uuid4().hex[:8]}).json()
        client_row=post(workstation,'/classroom/register',{'number':'client-'+uuid.uuid4().hex[:8]}).json()
        monkeypatch.setenv('CLASSROOM_SERVER_STATION_ID',server_row['id'])
        server.headers['X-Workstation']=server_row['token']
        workstation.headers['X-Workstation']=client_row['token']
        assert post(server,'/classroom/heartbeat',{}).status_code==200
        assert post(workstation,'/classroom/heartbeat',{}).status_code==200
        listed={row['id']:row for row in server.get('/api/classroom/stations').json()}
        assert listed[server_row['id']]['online'] and listed[server_row['id']]['mode']=='server'
        assert listed[client_row['id']]['online'] and listed[client_row['id']]['mode']=='client'
        assert listed[client_row['id']]['user_id'] is None
        login(workstation,'admin')
        assert post(workstation,'/classroom/heartbeat',{}).status_code==200
        assert next(row for row in server.get('/api/classroom/stations').json() if row['id']==client_row['id'])['user_id'] is not None
        post(workstation,'/logout')
        assert post(workstation,'/classroom/heartbeat',{}).status_code==200
        assert next(row for row in server.get('/api/classroom/stations').json() if row['id']==client_row['id'])['user_id'] is None


def test_workstation_admission_and_classroom_permissions():
    with TestClient(app) as teacher,TestClient(app) as student:
        login(teacher,'admin')
        s=post(student,'/classroom/register',{'number':'test-'+uuid.uuid4().hex[:8]}).json()
        t=post(teacher,'/classroom/register',{'number':'test-'+uuid.uuid4().hex[:8]}).json()
        student.headers['X-Workstation']=s['token'];teacher.headers['X-Workstation']=t['token']
        for station in (s,t):assert teacher.patch('/api/classroom/stations/'+station['id'],json={'approved':True},headers=HEAD).status_code==200
        login(student,'student');sid=student.get('/api/me').json()['id']
        assert post(student,'/classroom/presence',{'sharing':True,'page':'/registry'}).status_code==200
        assert post(teacher,'/classroom/presence',{'sharing':True}).status_code==200
        assert post(student,'/classroom/links',{'students':[sid],'mode':'help'}).status_code==403
        assert post(teacher,'/classroom/links',{'students':[sid],'mode':'help'}).status_code==200
        link=post(teacher,'/classroom/presence',{'sharing':True}).json()[0]['id']
        assert post(student,f'/classroom/links/{link}/signal',{'kind':'click','payload':{'x':.3,'y':.2}}).status_code==403
        assert post(teacher,f'/classroom/links/{link}/signal',{'kind':'click','payload':{'x':.3,'y':.2}}).status_code==200
        assert student.get(f'/api/classroom/links/{link}/signals').json()[0]['kind']=='click'
        from apps.api.app.classroom import live
        tid=teacher.get('/api/me').json()['id'];live[tid]['at']=0
        assert post(student,'/classroom/presence',{'sharing':True}).json()==[]
        assert teacher.get(f'/api/classroom/links/{link}/signals').status_code==403
        teacher.patch('/api/classroom/stations/'+s['id'],json={'blocked':True},headers=HEAD)
        assert student.get('/api/registry').status_code==403
        assert teacher.get(f'/api/classroom/links/{link}/signals').status_code==403

def test_cooperative_handoff_and_no_duplicate_or_simulated_status():
    with TestClient(app) as c:
        login(c,'teacher');users=c.get('/api/users').json();s1=next(u['id'] for u in users if u['login']=='student');s2=next(u['id'] for u in users if u['login']=='student2')
        versions=c.get('/api/tickets').json();v=next(v for v in versions if v['published'] and v['data']['tasks'][0]['mode']=='112')
        for sid in (s1,s2):
            with SessionLocal() as db:
                p=db.get(TrainingProfile,sid)
                if not p:p=TrainingProfile(user_id=sid,data={});db.add(p)
                p.data={'intro_complete':True};db.commit()
        r=post(c,'/lessons',{'title':'Совместный тест','students':[s1,s2],'versions':[v['id']], 'delivery_mode':'cooperative','roles':{str(s1):'112',str(s2):'ДДС района'}})
        assert r.status_code==200,r.text
        lid=r.json()['id'];assert post(c,f'/lessons/{lid}/start').status_code==200
        login(c,'student');q=c.get(f'/api/lessons/{lid}/queue').json();p=c.get('/api/attempts/'+str(q['cards'][0]['id'])).json()
        p=command(c,p,'accept_call');p=command(c,p,'draft',{'street':'Учебная','house':'12','incident_type':'Учебный пожар','description':'Учебное задымление'})
        p=command(c,p,'notify',{'services':['ДДС района']});source=p['id']
        p=command(c,p,'notify',{'services':['ДДС района']})
        login(c,'student2');q=c.get(f'/api/lessons/{lid}/queue').json();assert len(q['cards'])==1
        incoming=c.get('/api/attempts/'+str(q['cards'][0]['id'])).json()
        assert incoming['card']['street']=='Учебная' and incoming['state']['source_attempt_id']==source
        command(c,incoming,'status',{'status':'Принята','comment':'Принято в работу'})
        login(c,'teacher');p=c.get('/api/attempts/'+str(source)).json()
        assert p['state']['services']['ДДС района'][-1]['status']=='Принята'
        post(c,f'/lessons/{lid}/stop')

def test_memory_is_scoped_and_revocable():
    from apps.api.app.answer_memory import remember, examples
    with SessionLocal() as db:
        student=db.scalar(select(User).where(User.login=='student'));teacher=db.scalar(select(User).where(User.login=='teacher'))
        attempt=db.scalar(select(Attempt).where(Attempt.student_id==student.id))
        assert attempt
        criterion={'id':'scoped','kind':'manual','label':'Проверка этапов','expected':'Доступ, вода перекрыта','actual':'Доступ получен. Воду перекрыли.','field':''}
        remember(db,attempt,criterion,teacher,True);db.commit()
        assert criterion['actual'] in examples(db,attempt,criterion)
        changed={**criterion,'expected':'Утечка устранена'}
        assert not examples(db,attempt,changed)
        remember(db,attempt,criterion,teacher,False);db.commit()
        assert not examples(db,attempt,criterion)

def test_adaptive_capacity_and_duration():
    from apps.api.app.classroom_flow import adaptive_delivery
    with TestClient(app) as c:
        login(c,'teacher');sid=next(u['id'] for u in c.get('/api/users').json() if u['login']=='student2')
        vid=next(v['id'] for v in c.get('/api/tickets').json() if v['published'] and v['data']['tasks'][0]['mode']=='dds')
        lid=post(c,'/lessons',{'title':'Спринт тест','students':[sid],'versions':[vid],'delivery_mode':'sprint','duration_minutes':1}).json()['id']
        post(c,f'/lessons/{lid}/start')
        with SessionLocal() as db:
            l=db.get(Lesson,lid);a=db.scalar(select(Assignment).where(Assignment.lesson_id==lid));v=db.get(TicketVersion,a.version_id)
            v.data={**v.data,'tasks':v.data['tasks']*5};db.commit()
            for i in range(5):adaptive_delivery(db,l,time.time()+20);db.commit()
            assert len(db.scalars(select(Attempt).where(Attempt.assignment_id==a.id)).all())==1
            adaptive_delivery(db,l,time.time()+61);db.commit();assert l.status=='ended'

def test_address_is_exact_not_fuzzy():
    from apps.api.app.writing import address_checks
    issues=address_checks({'street':'Добненская'},{'street':'Дубиненская'})
    assert issues and issues[0]['expected']=='Дубиненская'
    assert not address_checks({'street':'  Дубиненская '},{'street':'дубиненская'})

def test_mini_drill_pauses_timer_and_survives_reload(monkeypatch):
    from apps.api.app import learning
    from apps.api.app.db import ScheduledEvent
    from test_flows import assignment
    monkeypatch.setattr(learning.secrets,'randbelow',lambda n:0)
    with TestClient(app) as c:
        login(c,'student');a=assignment(c,'ДДС: прорыв трубы')
        p=post(c,f'/assignments/{a["id"]}/start').json()
        q=post(c,f'/learning/drill/{p["id"]}').json();assert q and 'answer' not in q
        assert post(c,f'/learning/drill/{p["id"]}').json()==q
        with SessionLocal() as db:
            row=db.get(Attempt,p['id']);row.state={**row.state,'mini_started':time.time()-25};db.commit()
        latest=c.get('/api/attempts/'+str(p['id'])).json()
        assert post(c,f'/attempts/{p["id"]}/command',{'command_id':uuid.uuid4().hex,'revision':latest['revision'],'type':'status','payload':{'status':'Принята'}}).status_code==400
        assert post(c,'/learning/drill-answer',{'id':q['id'],'answer':'неважно'}).status_code==200
        latest=c.get('/api/attempts/'+str(p['id'])).json();assert latest['state']['paused_seconds']>=25
        assert 'mini_started' not in latest['state']
        assert post(c,f'/learning/drill/{p["id"]}').json() is None



def test_model_quote_is_verified_and_bad_quote_is_not_shown():
    from apps.api.app.semantic_review import verified_quote
    assert verified_quote('воду перекрыли.','Воду перекрыли.')==('Воду перекрыли.','')
    quote,warning=verified_quote('Утечку устранили','Воду перекрыли.')
    assert quote=='' and warning
