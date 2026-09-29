import copy,time,uuid
from types import SimpleNamespace
from sqlalchemy import select
from test_flows import app,TestClient,login,post,SessionLocal
from apps.api.app import main as m
from apps.api.app.db import Assignment,Attempt,TicketVersion,User,Lesson,now
from apps.api.app.dds_flow import create_attempt
from apps.api.app.classroom_flow import adaptive_delivery


def test_brigade_sequential_waits_for_record_without_timeout(monkeypatch):
 with TestClient(app):
  with SessionLocal() as db:
   source=db.scalar(select(Assignment))
   assignment=Assignment(version_id=source.version_id,student_id=source.student_id,teacher_id=source.teacher_id,title='Проверка порядка докладов',training=True)
   db.add(assignment);db.flush()
   task=next(t for v in db.scalars(select(TicketVersion)) for t in v.data['tasks'] if t['mode']=='dds')
   task=copy.deepcopy(task)
   task['service_events']=[{'kind':'incoming_call','contact_id':'unit1','who':'Бригада','text':str(i),'after':20+i*25} for i in range(3)]
   p=create_attempt(db,assignment,task,987);db.commit()
   stamp=time.time();clock=[stamp+3];monkeypatch.setattr(m.time,'time',lambda:clock[0])
   m.process_events(db);db.refresh(p)
   assert len(p.state['incoming_calls'])==1
   clock[0]+=5;m.process_events(db);db.refresh(p);assert len(p.state['incoming_calls'])==1
   user=db.get(User,assignment.student_id)
   def command(kind,payload):
    return m.apply_command(p.id,SimpleNamespace(type=kind,payload=payload,revision=p.revision,command_id=uuid.uuid4().hex),user,db)
   command('accept_dds_call',{'id':p.state['incoming_calls'][0]['id']})
   command('status',{'status':'Принята','comment':'Доклад внесён в карточку'})
   clock[0]+=1;m.process_events(db);db.refresh(p);assert not p.state['incoming_calls']
   clock[0]+=2;m.process_events(db);db.refresh(p);assert len(p.state['incoming_calls'])==1
   clock[0]+=29;m.process_events(db);db.refresh(p);assert len(p.state['incoming_calls'])==1
   clock[0]+=120;m.process_events(db);db.refresh(p);assert len(p.state['incoming_calls'])==1
   command('accept_dds_call',{'id':p.state['incoming_calls'][0]['id']})
   clock[0]+=120;m.process_events(db);db.refresh(p);assert not p.state['incoming_calls']
   command('status',{'status':'Начало реагирования','comment':'Доклад зарегистрирован'})
   clock[0]+=3;m.process_events(db);db.refresh(p);assert len(p.state['incoming_calls'])==1


def test_timed_brigade_keeps_author_schedule():
 with TestClient(app):
  with SessionLocal() as db:
   source=db.scalar(select(Assignment));task=next(t for v in db.scalars(select(TicketVersion)) for t in v.data['tasks'] if t['mode']=='dds')
   lesson=Lesson(teacher_id=source.teacher_id,title='Спринт',config={'delivery_mode':'sprint'},status='prepared');db.add(lesson);db.flush()
   assignment=Assignment(version_id=source.version_id,student_id=source.student_id,teacher_id=source.teacher_id,lesson_id=lesson.id,title='Спринт');db.add(assignment);db.flush()
   p=create_attempt(db,assignment,task,0)
   assert p.state['brigade_pacing']=='timed'


def test_adaptive_one_card_and_repeats_suitable_pool(monkeypatch):
 with TestClient(app) as c:
  login(c,'teacher');sid=c.get('/api/users').json()[0]['id']
  with SessionLocal() as db:sid=db.scalar(select(User.id).where(User.login=='student'))
  r=post(c,'/lessons',{'title':'Индивидуальная практика','students':[sid],'delivery_mode':'adaptive','versions':[]});assert r.status_code==200,r.text
  from apps.api.app import classroom_flow
  monkeypatch.setattr(classroom_flow,'summary',lambda *_:{'intro_complete':True,'level':5,'recommended_stars':1})
  assert post(c,f'/lessons/{r.json()["id"]}/start').status_code==200
  with SessionLocal() as db:
   lesson=db.get(Lesson,r.json()['id']);assignment=db.scalar(select(Assignment).where(Assignment.lesson_id==lesson.id));stamp=time.time()+120
   adaptive_delivery(db,lesson,stamp);db.flush()
   attempts=list(db.scalars(select(Attempt).where(Attempt.assignment_id==assignment.id)));assert len(attempts)==1
   attempts[0].status='completed';db.flush();adaptive_delivery(db,lesson,stamp+1);db.flush()
   attempts=list(db.scalars(select(Attempt).where(Attempt.assignment_id==assignment.id)));assert len(attempts)==2
   assert all(p.snapshot['difficulty_level']==1 for p in attempts)
   assert all(p.state['brigade_pacing']=='sequential' for p in attempts)


def test_unconfigured_demo_device_is_not_visible(monkeypatch):
 monkeypatch.setenv('DEMO_CLASSROOM','1')
 with TestClient(app) as c:
  login(c,'admin');row=post(c,'/classroom/register',{'number':'Демо слот 999'}).json();c.headers['X-Workstation']=row['token']
  post(c,'/management/agent/poll',{'metrics':{}})
  assert not any(d['id']==row['id'] for d in c.get('/api/management/devices').json())
  assert post(c,'/classroom/demo-number',{'number':'997'}).status_code==200
  assert any(d['id']==row['id'] for d in c.get('/api/management/devices').json())
  assert post(c,'/classroom/demo-pending').status_code==200
  assert not any(d['id']==row['id'] for d in c.get('/api/management/devices').json())
  assert not c.get('/api/classroom/admission').json()['configured']
