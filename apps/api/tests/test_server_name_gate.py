from fastapi.testclient import TestClient

from test_flows import app, SessionLocal, HEAD
from apps.api.app.management_models import ManagementSetting


def test_administrator_names_server_before_other_users_log_in(monkeypatch):
    monkeypatch.setenv('ENFORCE_SERVER_NAME', '1')
    monkeypatch.setenv('DEMO_CLASSROOM', '1')
    with TestClient(app) as admin, TestClient(app) as teacher:
        with SessionLocal() as db:
            row=db.get(ManagementSetting,'server_identity')
            original=dict(row.value) if row else None
            if row:
                row.value={'name':'Кабинет 101'}
            else:
                db.add(ManagementSetting(key='server_identity',value={'name':'Кабинет 101'}))
            db.commit()
        try:
            status=teacher.get('/api/classroom/server-setup').json()
            assert status['named'] is True
            assert status['name']=='Кабинет 101'
            assert status['ready'] is False
            credentials={'login':'teacher','password':'Training112!'}
            blocked=teacher.post('/api/login',json=credentials,headers=HEAD)
            assert blocked.status_code==403
            assert 'администратор' in blocked.json()['detail']
            assert admin.post('/api/login',json={'login':'admin','password':'Training112!'},headers=HEAD).status_code==200
            saved=admin.post('/api/management/server-name',json={'name':'Кабинет 204'},headers=HEAD)
            assert saved.status_code==200
            assert teacher.get('/api/classroom/server-setup').json()['name']=='Кабинет 204'
            assert teacher.get('/api/classroom/server-setup').json()['ready'] is True
            assert teacher.post('/api/login',json=credentials,headers=HEAD).status_code==200
        finally:
            with SessionLocal() as db:
                row=db.get(ManagementSetting,'server_identity')
                if original is None:
                    if row:db.delete(row)
                else:
                    row.value=original
                db.commit()


def test_lan_server_keeps_its_saved_name_after_restart(monkeypatch):
    from apps.api.app.server_identity import reset_activation
    monkeypatch.setenv('ENFORCE_SERVER_NAME','1')
    monkeypatch.delenv('DEMO_CLASSROOM',raising=False)
    with TestClient(app) as teacher:
        with SessionLocal() as db:
            row=db.get(ManagementSetting,'server_identity')
            original=dict(row.value) if row else None
            if row:row.value={'name':'Кабинет 305'}
            else:db.add(ManagementSetting(key='server_identity',value={'name':'Кабинет 305'}))
            db.commit()
        try:
            reset_activation()
            status=teacher.get('/api/classroom/server-setup').json()
            assert status['name']=='Кабинет 305' and status['ready'] is True
            assert teacher.post('/api/login',json={'login':'teacher','password':'Training112!'},headers=HEAD).status_code==200
        finally:
            with SessionLocal() as db:
                row=db.get(ManagementSetting,'server_identity')
                if original is None:
                    if row:db.delete(row)
                else:row.value=original
                db.commit()
