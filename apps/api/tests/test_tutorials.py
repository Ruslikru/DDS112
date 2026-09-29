from test_flows import app,TestClient,login,post,command,SessionLocal
from apps.api.app.tutorials import seed


def test_four_guided_tickets_and_repeat():
    with TestClient(app) as c:
        login(c,'student')
        catalog=c.get('/api/tutorials').json()
        assert {t['key'] for t in catalog}=={'112-1','112-2','dds-1','dds-2'}
        with SessionLocal() as db:seed(db)
        assert len(c.get('/api/tutorials').json())==4
        for t in catalog:
            p=post(c,f"/tutorials/{t['version_id']}/start").json()
            assert p['state']['guided'] and p['state']['teacher_assisted']
            assert post(c,f"/tutorials/{t['version_id']}/start").json()['id']==p['id']
            assert post(c,f"/learning/drill/{p['id']}").json() is None
            if t['mode']=='112':
                p=command(c,p,'accept_call')
                p=command(c,p,'question',{'id':'details'})
                n=t['key'][-1]
                p=command(c,p,'draft',{'name':'Елена Андреевна Соколова','street':'Декабристов' if n=='1' else 'Конёнкова','house':'28' if n=='1' else '26','incident_type':p['task']['type_options'][0],'victims':'no','description':'Пострадавших нет, заявка принята.'})
                p=command(c,p,'notify',{'services':p['task']['services']})
                p=command(c,p,'end_call')
            else:
                for status in ['Принята','Начало реагирования','Прибытие','Проведение работ','Работы завершены']:
                    p=command(c,p,'status',{'status':status,'comment':'Учебная проверка статуса'})
                    if status in ['Принята','Начало реагирования','Проведение работ']:
                        p=command(c,p,'contact',{'id':'brigade','text':'Сообщите обстановку по заявке'})
                assert p['state']['contact_counts']['brigade']==1
                assert all(m.get('audio') for m in p['state']['messages'] if m['who']=='Старший бригады')
            p=command(c,p,'finish')
            assert p['status']=='completed' and p['assessment']['score']==100
            assert post(c,f"/tutorials/{t['version_id']}/start").json()['id']!=p['id']


def test_teacher_own_practice_and_permissions():
    with TestClient(app) as c:
        login(c,'student')
        t=c.get('/api/tutorials').json()[0]
        assert post(c,f"/tickets/{t['version_id']}/try").status_code==403
        login(c,'teacher')
        before=c.get('/api/tickets').json()
        p=post(c,f"/tickets/{t['version_id']}/try").json()
        assert p['student_id']==c.get('/api/me').json()['id']
        assert p['state']['preview'] and p['state']['teacher_assisted']
        assert command(c,p,'accept_call')['state']['call']=='connected'
        assert c.get('/api/tickets').json()==before
        assert post(c,f"/tickets/{t['version_id']}/try",{'task_index':100}).status_code==400
        login(c,'student')
        assert c.get(f"/api/attempts/{p['id']}").status_code==403
