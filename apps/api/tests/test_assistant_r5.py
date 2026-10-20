"""Regression cases from the teacher's spoken assistant commands."""
import uuid
import pytest
from sqlalchemy import select
from test_assistant import teacher, classroom, ask
from test_flows import post, SessionLocal
from apps.api.app.db import Group, User
from apps.api.app.learning import MiniQuestion

@pytest.fixture(autouse=True)
def no_model_warmup(monkeypatch):
    from apps.api.app import startup_models
    async def no_warm(): pass
    monkeypatch.setattr(startup_models, 'warm_models', no_warm)


@pytest.mark.parametrize('phrase', ['Озвучка не нужна.', 'Звук не нужен', 'Без озвучки', 'Не нужно', 'Не надо озвучивать', 'Не озвучивайте', 'Нет'])
def test_audio_refusal_is_not_spoken_content(teacher, phrase):
    slots={'prompt':'Какие клавиши обновляют журнал?', 'answer':'Ctrl + F5', 'options':['Ctrl + F5','Ctrl + R'], 'options_answered':True,'answer_slot':'audio_text'}
    result=ask(teacher,phrase,dialog={'intent':'create_question','slots':slots})
    assert result['intent']=='create_question' and result['confirm_required'],result
    assert result['slots']['audio_text']=='' and result['slots']['audio_answered']
    created=post(teacher,'/assistant/execute',{'intent':result['intent'],'slots':result['slots'],'confirm_token':result['confirm_token']})
    assert created.status_code==200,created.text
    with SessionLocal() as db:
        question=db.get(MiniQuestion,created.json()['slots']['question_id'])
        assert not question.data.get('audio_text')


def test_actual_audio_text_survives(teacher):
    phrase='Озвучка не нужна только для письменных ответов'
    slots={'prompt':'Запишите фразу', 'answer':phrase,'options_answered':True,'answer_slot':'audio_text'}
    result=ask(teacher,phrase,dialog={'intent':'create_question','slots':slots})
    assert result['slots']['audio_text']==phrase


@pytest.mark.parametrize('phrase',['Пока никого.','Никого','Без студентов','Добавлю позже'])
def test_empty_group_is_created_without_moving_students(teacher,classroom,phrase):
    with SessionLocal() as db:
        before={u.id:u.group_id for u in db.scalars(select(User).where(User.role=='student'))}
    name='Пустая группа '+uuid.uuid4().hex[:8]
    result=ask(teacher,phrase,dialog={'intent':'create_group','slots':{'name':name,'answer_slot':'members'}})
    assert result['confirm_required'] and result['slots']['student_ids']==[],result
    created=post(teacher,'/assistant/execute',{'intent':'create_group','slots':result['slots'],'confirm_token':result['confirm_token']})
    assert created.status_code==200,created.text
    with SessionLocal() as db:
        group=db.get(Group,created.json()['slots']['group_id'])
        assert group.name==name
        assert before=={u.id:u.group_id for u in db.scalars(select(User).where(User.role=='student'))}


@pytest.mark.parametrize('phrase',['Начать трансляцию.','Начни трансляцию','Запусти трансляцию','Включи трансляцию'])
def test_start_broadcast_requests_real_client_action(teacher,phrase):
    result=ask(teacher,phrase,page='/classroom/modes')
    assert result['intent']=='demo_mode',result
    assert result['action']=={'kind':'start_broadcast','students':[]}
    assert 'начата' not in result['preview'].lower()


def test_broadcast_named_student_and_unavailable_student(teacher,classroom,monkeypatch):
    from apps.api.app import assistant
    monkeypatch.setattr(assistant,'station_rows',lambda *args:[{'user_id':classroom['kuz'],'online':True,'number':2}])
    result=ask(teacher,'Запусти режим «Делай как я» для Кузнецова')
    assert result['action']=={'kind':'start_broadcast','students':[classroom['kuz']]},result
    missing=ask(teacher,'Запусти трансляцию для Несуществующего')
    assert missing['action'] is None
    outside=ask(teacher,'Запусти трансляцию для Петрова')
    assert outside['action'] is None
    monkeypatch.setattr(assistant,'station_rows',lambda *args:[])
    offline=ask(teacher,'Запусти трансляцию для Кузнецова')
    assert offline['action']['kind']=='navigate' and 'не в сети' in offline['preview']


def test_ambiguous_broadcast_keeps_the_start_intent(teacher,classroom,monkeypatch):
    from apps.api.app import assistant
    monkeypatch.setattr(assistant,'station_rows',lambda *args:[{'user_id':classroom['iv1'],'online':True,'number':2}])
    result=ask(teacher,'Запусти трансляцию для Ивановой')
    assert len(result['candidates'])==2
    chosen=ask(teacher,'Мария Иванова',dialog={'intent':'demo_mode','slots':{**result['slots'],'student_id':classroom['iv1']}})
    assert chosen['action']=={'kind':'start_broadcast','students':[classroom['iv1']]},chosen


def test_explicit_cancel_still_cancels_the_audio_question(teacher):
    result=ask(teacher,'Отмена',dialog={'intent':'create_question','slots':{'prompt':'Вопрос','answer':'Ответ','answer_slot':'audio_text'}})
    assert result['intent']=='cancel' and not result['confirm_required']
