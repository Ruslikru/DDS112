from sqlalchemy import select
from test_new_student_guidance import classroom,learner
from test_flows import login,post,command,SessionLocal
from apps.api.app.classroom_models import MiniQuestion
from apps.api.app.db import Attempt


def test_builtin_dictations_have_ready_audio_and_hide_target(classroom):
    from apps.api.app.dictation import is_dictation
    from apps.api.app.learning import question_view
    with SessionLocal() as db:
        questions=[q for q in db.scalars(select(MiniQuestion)) if is_dictation(q.data)]
        assert len(questions)>=17
        for q in questions:
            view=question_view(q,db,True)
            assert view['audio_id'] and view['audio_status']=='ready'
            assert q.data['answer'] not in view['prompt']
            assert 'answer' not in view and 'audio_text' not in view


def test_tutorial_records_comment_for_background_analysis_and_result_review(classroom):
    name,sid=learner(0);login(classroom,name)
    tutorial=classroom.get('/api/tutorials').json()[0]
    attempt=post(classroom,f"/tutorials/{tutorial['version_id']}/start").json()
    result=post(classroom,f"/attempts/{attempt['id']}/command",{'command_id':'bad-comment-test','revision':attempt['revision'],'type':'status','payload':{'status':'Принята','comment':'абракадабра'}})
    assert result.status_code==200,result.text
    attempt=result.json()
    assert attempt['state']['services'][attempt['task']['own_service']][-1]['comment']=='абракадабра'
    attempt=command(classroom,attempt,'contact',{'id':'brigade','text':'Передаю заявку по указанному адресу.'})
    for status,comment in [('Начало реагирования','Бригада выехала.'),('Прибытие','Бригада прибыла.'),('Проведение работ','Выполняется ремонт.'),('Работы завершены','Опасность устранена, работы завершены.')]:
        attempt=command(classroom,attempt,'status',{'status':status,'comment':comment})
    attempt=command(classroom,attempt,'finish')
    comments=next(c for c in attempt['assessment']['criteria'] if c['id']=='tutorial-comments')
    assert comments['kind']=='manual' and comments['passed'] is None and 'абракадабра' in comments['actual']
    from apps.api.app import semantic_review
    assert semantic_review.next_attempt() is not None  # No result page was opened.
    assert post(classroom,f"/tutorials/attempts/{attempt['id']}/reviewed").status_code==400
    with SessionLocal() as db:
        row=db.get(Attempt,attempt['id']);row.assessment={**row.assessment,'report_job':{'status':'done'}};db.commit()
    assert post(classroom,f"/tutorials/attempts/{attempt['id']}/reviewed").status_code==200
    assert classroom.get(f"/api/attempts/{attempt['id']}").json()['state']['tutorial_result_seen']
