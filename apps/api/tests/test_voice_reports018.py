import copy
from test_flows import app,TestClient,login,post,command,SessionLocal
from apps.api.app.db import Attempt
from apps.api.app import voice,result_report


def test_greeting_is_prepared_with_same_voice_and_authorized():
    with TestClient(app) as c:
        login(c,'student')
        t=next(t for t in c.get('/api/tutorials').json() if t['key']=='dds-1')
        p=post(c,f"/tutorials/{t['version_id']}/start").json()
        contact=p['task']['contacts'][0]
        assert contact['greeting_audio'] and 'voice_lines' not in contact
        assert c.get('/api/media/'+contact['greeting_audio']).content.startswith(b'RIFF')
        with SessionLocal() as db:
            lines=db.get(Attempt,p['id']).snapshot['contacts'][0]['voice_lines']
            jobs=[db.get(voice.VoiceJob,x['voice_key']) for x in lines]
            assert any(x.get('role')=='greeting' for x in lines)
            assert all(j.data['gender']==jobs[0].data['gender'] and j.data['settings']==jobs[0].data['settings'] for j in jobs)
        command(c,p,'abort')


def test_background_report_and_reviewed_guided_work(monkeypatch):
    from apps.api.app import semantic_review
    with TestClient(app) as c:
        login(c,'student');t=next(t for t in c.get('/api/tutorials').json() if t['key']=='dds-1')
        p=post(c,f"/tutorials/{t['version_id']}/start").json()
        p=command(c,p,'contact',{'id':'brigade','text':'Москва, улица Декабристов, дом 28. Видим дым.'})
        for status in ['Принята','Начало реагирования','Прибытие','Проведение работ','Работы завершены']:p=command(c,p,'status',{'status':status})
        p=command(c,p,'finish');assert p['assessment']['report_job']['status']=='queued'
        monkeypatch.setattr(semantic_review.ai,'complete',lambda *_args,**_kwargs:({'verdict':'full','reason':'Адрес передан.','evidence':'Москва'},{}))
        semantic_review.review_attempt(p['id'])
        seen=[]
        def complete(system,prompt,*args,**kwargs):
            seen.append(prompt)
            return {'summary':'Сведения переданы.','recommendation':'Продолжить обучение.'},{'model':'test'}
        monkeypatch.setattr(result_report.ai,'complete',complete)
        result_report.generate(p['id'])
        p=c.get('/api/attempts/'+str(p['id'])).json()
        assert p['assessment']['report_job']['status']=='done'
        assert 'Диспетчер' in seen[0] and 'Декабристов' in seen[0]
        login(c,'teacher');p=post(c,f"/attempts/{p['id']}/review",{'criteria':{'phone_conversation':True},'reason':'Проверено преподавателем.'}).json()
        rows=c.get('/api/teacher/students').json();row=next(x for x in rows if x['id']==p['student_id'])
        assert row['checked']>=1 and row['checked']>row['confirmed']
        item=next(x for x in row['history'] if x['id']==p['id'])
        assert item['checked'] and item['assisted'] and not item['confirmed']
        # A failed report is explicit; it never creates fabricated recommendations.
        def fail(*a,**k):raise ValueError('test inference unavailable')
        monkeypatch.setattr(result_report.ai,'complete',fail)
        result_report.generate(p['id'])
        assert c.get('/api/attempts/'+str(p['id'])).json()['assessment']['report_job']['status']=='error'
