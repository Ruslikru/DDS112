import copy
import time
import uuid
from types import SimpleNamespace
from sqlalchemy import select
from test_flows import app, TestClient, login, post, command, SessionLocal
from apps.api.app.db import Attempt, Assignment, ScheduledEvent, User
from apps.api.app.dds_scenarios import generated_dds
from apps.api.app.domain import assess
from apps.api.app.evidence import is_learner
from apps.api.app.main import process_events


def draft():
    config=SimpleNamespace(incident_type='Пожар',own_service='Служба 101',
        services=['Служба 101','Служба 102'],district='Москва',access_source='service_history')
    facts={'city':'Москва','street':'Берзарина','house':'21','caller_name':'Иванов Иван',
        'title':'Проверка сценария '+uuid.uuid4().hex[:8],
        'description':'Горит мусорный контейнер во дворе.','victims':'Пострадавших нет.',
        'victims_state':'no','difficulty_stars':5,
        'address_note':'Заезд справа через двор, ворота открыты.'}
    return generated_dds(config,facts,{'model':'fixture'}).model_dump()


def start_scenario(c):
    login(c,'admin')
    data=draft()
    saved=post(c,'/tickets',data)
    assert saved.status_code==200,saved.text
    version_id=saved.json()['id']
    result=post(c,f'/tickets/{version_id}/publish')
    assert result.status_code==200,result.text
    with SessionLocal() as db:
        student=db.scalar(select(User).where(User.login=='student'))
        student_id=student.id
    result=post(c,'/assignments',{'version_id':version_id,'students':[student_id],'start_mode':'self','training':True})
    assert result.status_code==200,result.text
    with SessionLocal() as db:
        assignment_id=db.scalar(select(Assignment.id).where(Assignment.version_id==version_id,Assignment.student_id==student_id))
    login(c,'student')
    response=post(c,f'/assignments/{assignment_id}/start')
    assert response.status_code==200,response.text
    return response.json(),data['tasks'][0]


def deliver(attempt_id, report_id):
    with SessionLocal() as db:
        p=db.get(Attempt,attempt_id)
        p.state={**copy.deepcopy(p.state),'brigade_next_at':0}
        for event in db.scalars(select(ScheduledEvent).where(ScheduledEvent.attempt_id==attempt_id,ScheduledEvent.done==False)):
            event.due=time.time()-1 if event.data.get('report_id')==report_id else time.time()+3600
        db.commit()
        process_events(db)


def grade(attempt_id,key):
    with SessionLocal() as db:
        return next(c for c in assess(db.get(Attempt,attempt_id))['criteria'] if c['id']==key)


def test_generated_flow_sources_dispatch_approach_and_records_are_distinct():
    with TestClient(app) as c:
        p,task=start_scenario(c)
        assert not {'scenario','criteria','service_events','expected_card'} & p['task'].keys()
        deliver(p['id'],'access-source')
        p=c.get(f'/api/attempts/{p["id"]}').json()
        rows=p['state']['services']['Служба 102']
        source=next(h for h in rows if h.get('report_id')=='access-source')
        assert source['comment']==task['scenario']['access']['answer']
        assert source['actor_role']=='service' and source['author']=='Диспетчер Служба 102'
        assert source['status']=='Получена службой' and source['comment_only']
        message=next(m for m in p['state']['messages'] if m.get('report_id')=='access-source')
        assert not is_learner(message)
        assert 'Учебный ответ службы' not in source['comment']

        p=command(c,p,'status',{'status':'Принята','comment':'',
            'actor_role':'brigade','report_id':'report-done','stage_id':'done'})
        own=p['task']['own_service']
        initial=p['state']['services'][own][-1]
        assert initial['actor_role']=='learner' and not initial.get('report_id')
        assert all(c['id']!='accept-record' for c in task['criteria'])
        assert grade(p['id'],'accept')['passed'] is True
        p=command(c,p,'contact',{'id':'brigade','text':'Москва, Берзарина, 21. Горит контейнер.',
            'actor_role':'service','report_id':'report-done','stage_id':'done','call_end':False})
        spoken,response=p['state']['messages'][-2:]
        assert spoken['actor_role']=='learner' and not spoken.get('report_id')
        assert response['report_id']=='report-dispatch' and response['stage_id']=='dispatch'
        assert response['actor_role']=='brigade'
        p=command(c,p,'status',{'status':'Начало реагирования','comment':'Бригада выехала.',
            'report_id':'report-done','stage_id':'done'})
        record=p['state']['services'][own][-1]
        assert record['report_id']=='report-dispatch' and not record['comment_only']
        assert grade(p['id'],'status-dispatch')['passed'] is True

        deliver(p['id'],'report-approach')
        p=c.get(f'/api/attempts/{p["id"]}').json()
        incoming=p['state']['incoming_calls'][0]
        p=command(c,p,'accept_dds_call',{'id':incoming['id'],'stage_id':'arrived','report_id':'report-arrived'})
        message=p['state']['messages'][-1]
        assert message['report_id']=='report-approach' and message['stage_id']=='approach'
        assert message['status']==''
        assert p['state']['services'][own][-1]['status']=='Начало реагирования'
        assert grade(p['id'],'status-arrived')['passed'] is False
        p=command(c,p,'worklog',{'comment':'Бригада уточнила подъезд. Передал: заезд справа через двор.',
            'report_id':'report-arrived','stage_id':'arrived','actor_role':'system'})
        record=p['state']['services'][own][-1]
        assert record['comment_only'] and record['stage_id']=='approach'
        assert record['actor_role']=='learner' and record['status']=='Начало реагирования'
        assert grade(p['id'],'record-approach')['passed'] is None
        assert grade(p['id'],'status-arrived')['passed'] is False
        assert 'brigade_waiting_record' not in p['state']
        command(c,p,'abort')


def test_client_cannot_fabricate_received_report_to_pass_early_status():
    with TestClient(app) as c:
        p,_=start_scenario(c)
        p=command(c,p,'status',{'status':'Принята'})
        p=command(c,p,'status',{'status':'Прибытие','comment':'Мы уже на месте.',
            'report_id':'report-arrived','stage_id':'arrived','at':'2099-01-01T00:00:00Z',
            'actor_role':'brigade'})
        row=p['state']['services'][p['task']['own_service']][-1]
        assert row['actor_role']=='learner' and not row.get('report_id')
        assert not row['at'].startswith('2099')
        assert grade(p['id'],'status-arrived')['passed'] is False
        assert grade(p['id'],'record-arrived')['credit']==0
        command(c,p,'abort')


def test_clicking_all_statuses_without_reports_and_comments_cannot_pass():
    with TestClient(app) as c:
        p,_=start_scenario(c)
        for status in ['Принята','Начало реагирования','Прибытие','Проведение работ','Работы завершены']:
            p=command(c,p,'status',{'status':status})
        p=command(c,p,'finish')
        assessment=p['assessment']
        records=[item for item in assessment['criteria'] if item.get('required_record')]
        assert len(records)==5
        assert all(item['passed'] is False and item['credit']==0 for item in records)
        assert all(item['passed'] is False for item in assessment['criteria'] if item['id'].startswith('status-'))
        assert assessment['score']<20 and not assessment['passed']


def test_publish_rejects_inconsistent_source_stage_and_unreachable_field():
    with TestClient(app) as c:
        login(c,'admin')
        for mutate in (
            lambda task:task['service_events'][0].update(comment='Источник потерян'),
            lambda task:task['scenario']['stages'][1].update(status='Прибытие'),
            lambda task:task['criteria'].append({'id':'edit-house','kind':'field','field':'house',
                                                 'label':'Дополнить дом','expected':'21'}),
        ):
            data=draft();mutate(data['tasks'][0])
            saved=post(c,'/tickets',data)
            assert saved.status_code==200,saved.text
            result=post(c,f'/tickets/{saved.json()["id"]}/publish')
            assert result.status_code==400 and 'сценарий' in result.json()['detail']
