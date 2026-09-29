import copy,uuid
from test_flows import app,TestClient,login,post,command,SessionLocal
from apps.api.app.db import Attempt
from apps.api.app import conversation_review as cr,result_report as rr,semantic_review as sr

def begin(c):
 login(c,'student')
 t=next(t for t in c.get('/api/tutorials').json() if t['key']=='dds-1')
 return post(c,f"/tutorials/{t['version_id']}/start").json()

def test_live_review_reuse_invalidation_and_confirmation(monkeypatch):
 with TestClient(app) as c:
  p=begin(c)
  p=command(c,p,'contact',{'id':'brigade','text':'Москва, Декабристов, дом 28. Дым.'})
  calls=[]
  def semantic(*args,**kwargs):
   calls.append(args[1]);return {'verdict':'partial','reason':'Сведения уточняются.','evidence':'Дым.'},{'model':'test'}
  monkeypatch.setattr(sr.ai,'complete',semantic)
  cr.generate(p['id'])
  with SessionLocal() as db:
   a=db.get(Attempt,p['id']);assert a.status=='active' and a.state['conversation_review']['evaluation']['verdict']=='partial'
   grade=rr.prepared(a).assessment;assert next(x for x in grade['criteria'] if x['id']=='phone_conversation')['credit']==.5
  # New spoken information must invalidate the earlier verdict.
  p=command(c,p,'contact',{'id':'brigade','text':'Пострадавших нет.'})
  with SessionLocal() as db:
   grade=rr.prepared(db.get(Attempt,p['id'])).assessment
   assert next(x for x in grade['criteria'] if x['id']=='phone_conversation')['passed'] is None
  cr.generate(p['id']);assert len(calls)==2
  for status in ['Принята','Начало реагирования','Прибытие','Проведение работ','Работы завершены']:p=command(c,p,'status',{'status':status})
  assert rr.next_warm() is not None
  monkeypatch.setattr(rr.ai,'complete',lambda *a,**k:({'summary':'Разбор готов.','recommendation':'Уточняйте сведения.'},{'model':'test'}))
  rr.generate(p['id'])
  with SessionLocal() as db:assert db.get(Attempt,p['id']).state['warm_report']['review']['summary']=='Разбор готов.'
  p=command(c,p,'finish')
  assert p['assessment']['report_job']['status']=='done'
  assert next(x for x in p['assessment']['criteria'] if x['id']=='phone_conversation')['credit']==.5
  login(c,'teacher')
  result=post(c,f"/attempts/{p['id']}/review",{'criteria':{},'confirm':True,'reason':'Работу проверил.'})
  assert result.status_code==200,result.text
  grade=result.json()['assessment'];assert not grade['ai_preliminary']
  assert next(x for x in grade['criteria'] if x['id']=='phone_conversation')['credit']==.5
  rows=c.get('/api/teacher/students').json();row=next(x for x in rows if x['id']==p['student_id'])
  assert row['checked']>=1 and row['checked_score'] is not None

def test_dds_comment_does_not_advance_status():
 with TestClient(app) as c:
  p=begin(c)
  for status in ['Принята','Начало реагирования']:p=command(c,p,'status',{'status':status})
  own=p['task']['own_service'];before=copy.deepcopy(p['state']['services'][own])
  p=command(c,p,'worklog',{'comment':'Бригада задерживается в пути.'})
  hist=p['state']['services'][own]
  assert hist[:-1]==before and hist[-1]['status']=='Начало реагирования' and hist[-1]['comment']=='Бригада задерживается в пути.'
  p=command(c,p,'status',{'status':'Работы завершены'})
  r=post(c,f"/attempts/{p['id']}/command",{'command_id':str(uuid.uuid4()),'revision':p['revision'],'type':'worklog','payload':{'comment':'Поздняя запись'}})
  assert r.status_code==400
  command(c,p,'abort')
