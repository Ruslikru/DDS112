import time
import uuid
from sqlalchemy import select, func
from test_flows import app, TestClient, login, post, SessionLocal, HEAD
from apps.api.app.db import User, Group, Lesson, Assignment, Attempt, TicketVersion
from apps.api.app.classroom_models import Workstation
from apps.api.app.training_session_models import SessionMember, StudentPresence, TrainingSession
from apps.api.app import training_sessions as ts, classroom_flow


def people():
    with SessionLocal() as db:
        teacher=db.scalar(select(User).where(User.login=='teacher'))
        source=db.scalar(select(User).where(User.login=='student'))
        group=Group(name='Постоянная '+uuid.uuid4().hex[:6],teacher_id=teacher.id);db.add(group);db.flush()
        users=[]
        for name in ('Первый Студент','Второй Студент'):
            user=User(login='attendance_'+uuid.uuid4().hex,name=name,role='student',group_id=group.id,password_hash=source.password_hash)
            db.add(user);db.flush();users.append((user.id,user.login))
        db.commit()
        return group.id,users


def session(c,ids):
    result=post(c,'/training-sessions',{'title':'Занятие на перемене','students':ids})
    assert result.status_code==200,result.text
    return result.json()


def approved_station(c):
    row=post(c,'/classroom/register',{'number':'test-'+uuid.uuid4().hex[:8]}).json()
    with SessionLocal() as db:db.get(Workstation,row['id']).approved=True;db.commit()
    c.headers['X-Workstation']=row['token']
    return row


def test_offline_preparation_waits_for_real_presence_and_sprint_uses_common_clock(monkeypatch):
    monkeypatch.setattr(classroom_flow,'summary',lambda *_:{'intro_complete':True,'level':1,'recommended_stars':1})
    with TestClient(app) as c:
        gid,users=people();ids=[user[0] for user in users];login(c,'teacher')
        meeting=session(c,ids)
        lesson=post(c,'/lessons',{'title':'Спринт для группы','students':ids,'delivery_mode':'sprint','session_id':meeting['id'],'duration_minutes':2})
        assert lesson.status_code==200,lesson.text
        lid=lesson.json()['id']
        assert post(c,f'/lessons/{lid}/start').status_code==400
        with SessionLocal() as db:
            assert db.get(Lesson,lid).started_at is None
            assert not db.scalar(select(Attempt.id).join(Assignment).where(Assignment.lesson_id==lid))
        started=post(c,f'/training-sessions/{meeting["id"]}/start').json()
        assert started['present_count']==0
        with SessionLocal() as db:
            lesson=db.get(Lesson,lid)
            assert lesson.started_at==started['started_at']
            assert not db.scalar(select(Attempt.id).join(Assignment).where(Assignment.lesson_id==lid))
        login(c,users[0][1]);approved_station(c)
        assert post(c,'/classroom/heartbeat').status_code==200
        assert post(c,'/classroom/heartbeat').status_code==200
        with SessionLocal() as db:
            lesson=db.get(Lesson,lid);classroom_flow.adaptive_delivery(db,lesson,time.time());db.commit()
            attempts=list(db.scalars(select(Attempt).join(Assignment).where(Assignment.lesson_id==lid)))
            assert len(attempts)==1 and attempts[0].student_id==ids[0]
            member=db.scalar(select(SessionMember).where(SessionMember.session_id==meeting['id'],SessionMember.student_id==ids[0]))
            assert len(member.intervals)==1
            before=lesson.started_at
            classroom_flow.adaptive_delivery(db,lesson,time.time()+130);db.commit()
            assert lesson.started_at==before and lesson.status=='ended'
            assert not db.scalar(select(Attempt.id).join(Assignment).where(Assignment.lesson_id==lid,Attempt.student_id==ids[1]))
        login(c,'teacher');final=post(c,f'/training-sessions/{meeting["id"]}/stop').json()
        assert {row['id']:row['presence'] for row in final['students']}=={ids[0]:'present',ids[1]:'absent'}


def test_offline_manual_assignment_snapshots_and_temporary_teams():
    with TestClient(app) as c:
        gid,users=people();ids=[user[0] for user in users];login(c,'teacher');meeting=session(c,ids);mid=meeting['id']
        first=post(c,f'/training-sessions/{mid}/mini-groups',{'name':'Вариант А','students':ids}).json()
        aid=first['mini_groups'][0]['id']
        second=post(c,f'/training-sessions/{mid}/mini-groups',{'name':'Вариант Б','students':[ids[1]]}).json()
        assert next(g for g in second['mini_groups'] if g['id']==aid)['students']==[ids[0]]
        with SessionLocal() as db:
            assert all(db.get(User,sid).group_id==gid for sid in ids)
            version=next(v for v in db.scalars(select(TicketVersion).where(TicketVersion.published==True)) if v.data['tasks'] and all(t['mode']=='dds' for t in v.data['tasks']))
            vid=version.id
        sent=post(c,'/assignments',{'session_id':mid,'version_id':vid,'students':[ids[1]],'start_mode':'self'})
        assert sent.status_code==200,sent.text
        login(c,users[1][1]);assignments=c.get('/api/assignments').json()
        assert any(a['session_id']==mid and a['student_id']==ids[1] for a in assignments)
        login(c,'teacher');post(c,f'/training-sessions/{mid}/start');post(c,f'/training-sessions/{mid}/stop')
        with SessionLocal() as db:
            old_name=db.get(Group,gid).name
            db.get(Group,gid).name='Переименованная группа';db.get(User,ids[1]).group_id=None;db.commit()
        result=c.get(f'/api/attendance?group_id={gid}').json()
        historical=next(row for row in result['sessions'] if row['id']==mid)
        assert all(s['group_name']==old_name for s in historical['students'])
        assert {s['id'] for s in historical['students']}==set(ids)
        assert post(c,f'/training-sessions/{mid}/mini-groups',{'name':'Вариант В','students':[ids[0]]}).status_code==400
        new=session(c,[ids[0]])
        assert not new['mini_groups']


def test_attendance_ignores_anonymous_heartbeat_and_preserves_reconnection_intervals():
    with TestClient(app) as c:
        gid,users=people();sid=users[0][0];login(c,'teacher');meeting=session(c,[sid]);mid=meeting['id']
        post(c,f'/training-sessions/{mid}/start');station=approved_station(c)
        c.cookies.clear()
        assert post(c,'/classroom/heartbeat').status_code==200
        with SessionLocal() as db:
            assert db.get(StudentPresence,sid) is None
            member=db.scalar(select(SessionMember).where(SessionMember.session_id==mid))
            assert member.first_seen is None
        login(c,users[0][1])
        assert post(c,'/classroom/presence',{'page':'/assignments','sharing':False}).status_code==200
        with SessionLocal() as db:
            member=db.scalar(select(SessionMember).where(SessionMember.session_id==mid));first=member.first_seen
            ts.record_presence(db,db.get(User,sid),first+1)
            ts.record_presence(db,db.get(User,sid),first+40);db.commit()
            assert len(member.intervals)==2
            assert member.first_seen==first
            assert ts.view(db,db.get(TrainingSession,mid),first+41)['students'][0]['presence']=='online'
            assert ts.view(db,db.get(TrainingSession,mid),first+70)['students'][0]['presence']=='left'
        login(c,'teacher');stopped=post(c,f'/training-sessions/{mid}/stop').json()
        assert stopped['students'][0]['presence']=='present'


def test_session_access_and_legacy_attendance_have_no_invented_presence():
    with TestClient(app) as c:
        gid,users=people();login(c,'teacher');meeting=session(c,[users[0][0]])
        with SessionLocal() as db:
            teacher=db.scalar(select(User).where(User.login=='teacher'))
            legacy=Lesson(teacher_id=teacher.id,title='Старое занятие',status='ended',config={'students':[users[0][0]],'training':True})
            db.add(legacy);db.commit();lid=legacy.id
            other=User(login='other_'+uuid.uuid4().hex,name='Другой Преподаватель',role='teacher',password_hash=teacher.password_hash);db.add(other);db.commit();other_login=other.login
        report=c.get(f'/api/attendance?group_id={gid}').json()
        legacy=next(s for s in report['sessions'] if s['id']=='legacy-'+str(lid))
        assert legacy['students'][0]['presence']=='unknown' and legacy['present_count'] is None
        login(c,other_login)
        assert c.get(f'/api/training-sessions/{meeting["id"]}').status_code==403
        assert c.get(f'/api/attendance?group_id={gid}').status_code==403
        assert post(c,'/training-sessions',{'title':'Чужой состав','students':[users[0][0]]}).status_code==403
        login(c,users[0][1])
        assert c.get('/api/attendance').status_code==403
