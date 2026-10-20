import uuid
from sqlalchemy import select
from test_flows import app, TestClient, login, post, HEAD, SessionLocal
from apps.api.app.db import Group, User


def test_group_names_members_and_profile_are_persistent_and_authorized():
    suffix=uuid.uuid4().hex[:8]
    with TestClient(app) as c:
        login(c,'admin')
        sid=post(c,'/users',{'login':'groups_'+suffix,'name':'Студент постоянной группы','password':'Training112!','role':'student'}).json()['id']
        foreign=post(c,'/teacher/groups',{'name':'Другая '+suffix}).json()['id']
        post(c,'/logout');login(c,'teacher')
        name='ДДС '+suffix
        response=post(c,'/teacher/groups',{'name':'  '+name+'  '})
        assert response.status_code==200,response.text
        gid=response.json()['id']
        assert response.json()['name']==name
        assert post(c,'/teacher/groups',{'name':name}).status_code==400
        assert post(c,'/teacher/groups',{'name':'   '}).status_code==400
        response=c.put(f'/api/teacher/groups/{gid}',json={'name':name+' Б','students':[sid]},headers=HEAD)
        assert response.status_code==200,response.text
        row=next(s for s in c.get('/api/teacher/students').json() if s['id']==sid)
        assert row['group_id']==gid and row['group_name']==name+' Б'
        assert row['can_assign']
        response=c.put(f'/api/teacher/groups/{foreign}',json={'name':'Чужая','students':[sid]},headers=HEAD)
        assert response.status_code==403
        # Invalid member must roll back a rename, not leave a partial edit.
        response=c.put(f'/api/teacher/groups/{gid}',json={'name':'Не сохранять','students':[999999999]},headers=HEAD)
        assert response.status_code==404
        with SessionLocal() as db:
            assert db.get(Group,gid).name==name+' Б'
            assert db.get(User,sid).group_id==gid
        post(c,'/logout');login(c,'student')
        assert post(c,'/teacher/groups',{'name':'Недоступно'}).status_code==403
        assert c.put(f'/api/teacher/groups/{gid}',json={'name':'Недоступно','students':[]},headers=HEAD).status_code==403
