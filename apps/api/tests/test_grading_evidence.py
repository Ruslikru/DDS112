import copy
from types import SimpleNamespace
import pytest
from test_flows import app  # Initialize an isolated test database before API imports.
from apps.api.app.domain import assess, score
from apps.api.app.evidence import is_learner, speech_context, speech_messages
from apps.api.app.semantic_review import grounded_evaluation, apply_evaluation
from apps.api.app.conversation_review import apply_cached, signature
from apps.api.app.result_report import evidence


def test_model_context_keeps_fact_availability_without_repeated_transcript():
    from apps.api.app.semantic_review import model_context
    first={'text':'Подъезд справа.','who':'Заявитель','at':at(1),'ai':{'seconds':40}}
    later={'text':'Работы завершены.','who':'Бригада','at':at(20)}
    context={'mode':'dds','card':{'house':'21'},'turns':[
        {'learner_text':'Заезжайте справа.','received_before_reply':[first],'available_service_records':[]},
        {'learner_text':'Записал завершение.','received_before_reply':[first,later],'available_service_records':[]} ]}
    compact=model_context(context)
    assert context['turns'][0]['received_before_reply'][0]['ai']=={'seconds':40}
    assert len(compact['received_facts'])==2
    assert compact['received_facts'][0]['before_turn']==0
    assert compact['received_facts'][1]['before_turn']==1
    assert 'ai' not in compact['received_facts'][0] and 'at' not in compact['received_facts'][0]
    assert compact['turns'][0]['learner_text']=='Заезжайте справа.'


def test_report_uses_confirmed_grades_and_does_not_invent_missing_records():
    from apps.api.app.result_report import summarize
    a=assess(attempt())
    result=summarize(a)
    assert result['source']=='criteria' and 'не зачтена' in result['summary']
    assert 'Запись о прибытии' in result['recommendation']
    assert 'model' not in result and 'seconds' not in result
    pending={'criteria':[{'id':'x','kind':'manual','label':'Разговор','expected':'','actual':'Да',
                         'passed':None,'weight':10,'critical':False}]}
    assert 'решение преподавателя' in summarize(pending)['summary']


def test_background_review_waits_for_end_of_exercise_not_each_phone_reply():
    from apps.api.app.conversation_review import ready_for_review
    p=attempt()
    p.state['messages']=[{'actor_role':'learner','text':'Понял.'},{'actor_role':'brigade','text':'До связи.','call_end':True}]
    p.state['services']['Служба 101']=[{'status':'Начало реагирования'}]
    assert not ready_for_review(p)
    p.state['services']['Служба 101'].append({'status':'Работы завершены'})
    assert ready_for_review(p)
    p.snapshot['mode']='112';p.state['call']='connected'
    assert not ready_for_review(p)
    p.state['call']='ended'
    assert ready_for_review(p)


def test_ready_report_does_not_wait_for_busy_model(monkeypatch):
    import asyncio
    from apps.api.app import semantic_review as sr,result_report
    generated=[];ticks=[]
    async def tick(_):
        if ticks:raise asyncio.CancelledError
        ticks.append(True)
    monkeypatch.setattr(sr.asyncio,'sleep',tick)
    monkeypatch.setattr(sr.ai,'lock',SimpleNamespace(locked=lambda:True))
    monkeypatch.setattr(result_report,'next_attempt',lambda:42)
    monkeypatch.setattr(result_report,'generate',generated.append)
    with pytest.raises(asyncio.CancelledError):asyncio.run(sr.worker())
    assert generated==[42]


def at(second):
    return f'2026-10-20T10:00:{second:02d}+03:00'


def attempt():
    criteria=[
        {'id':'arrival','kind':'status','expected':'Прибытие','label':'Прибытие',
         'weight':10,'critical':False,'stage_id':'arrived','report_id':'report-arrived'},
        {'id':'arrival-record','kind':'manual','expected':'Бригада на месте, обстановка подтверждена.',
         'label':'Запись о прибытии','weight':20,'critical':False,'field':'',
         'evidence_source':'written','required_record':True,'status':'Прибытие',
         'stage_id':'arrived','report_id':'report-arrived'},
    ]
    task={'mode':'dds','own_service':'Служба 101','limit_seconds':30,
          'criteria':criteria,'initial_card':{'street':'Берзарина','house':'21'},
          'scenario':{'access':{'source':'unknown','answer':''}}}
    state={'services':{'Служба 101':[]},'messages':[]}
    return SimpleNamespace(snapshot=task,state=state,card={},started_at=at(0),submitted_at=at(50))


def received(second=10):
    return {'actor_role':'brigade','who':'Бригада','text':'Прибыли, обстановка подтверждена.',
            'at':at(second),'report_id':'report-arrived','stage_id':'arrived'}


def criterion(result, key):
    return next(c for c in result['criteria'] if c['id']==key)


def test_spoken_report_and_foreign_dispatcher_cannot_replace_written_comment():
    p=attempt()
    p.state['messages']=[received(),
        {'actor_role':'learner','who':'Диспетчер → Бригада','text':'Прибытие записал, приступайте.','at':at(11)},
        {'who':'Диспетчер другой службы','text':'Я уже записал всё за вас.','at':at(12)}]
    p.state['services']['Служба 101']=[{'actor_role':'learner','status':'Прибытие','comment':'','at':at(13)}]
    result=assess(p)
    assert criterion(result,'arrival')['passed'] is True
    record=criterion(result,'arrival-record')
    assert record['passed'] is False and record['credit']==0 and record['actual']==''
    spoken=criterion(result,'phone_conversation')['actual']
    assert 'Прибытие записал' in spoken and 'всё за вас' not in spoken
    p.assessment=result
    assert all(is_learner(m) for m in evidence(p)['messages'])
    assert result['score']<100 and result['pending']


def test_future_report_cannot_retroactively_justify_status_or_comment():
    p=attempt();p.state['messages']=[received(20)]
    p.state['services']['Служба 101']=[{'status':'Прибытие','comment':'Бригада на месте.',
                                       'at':at(10),'actor_role':'learner'}]
    result=assess(p)
    assert criterion(result,'arrival')['passed'] is False
    assert 'до получения' in criterion(result,'arrival')['evidence_reason']
    assert criterion(result,'arrival-record')['passed'] is False
    p.state['services']['Служба 101'].append({'status':'Прибытие','comment':'Бригада на месте.',
                                            'at':at(21),'actor_role':'learner'})
    result=assess(p)
    assert criterion(result,'arrival')['passed'] is True
    assert criterion(result,'arrival-record')['passed'] is None
    assert criterion(result,'arrival-record')['actual']=='Бригада на месте.'


def test_unrelated_stage_record_does_not_cover_missing_arrival_record():
    p=attempt();p.state['messages']=[received()]
    p.state['services']['Служба 101']=[{'status':'Начало реагирования','comment':'Выехали.',
                                       'at':at(12),'actor_role':'learner'}]
    assert criterion(assess(p),'arrival-record')['credit']==0


@pytest.mark.parametrize('verdict',['full','partial'])
@pytest.mark.parametrize('quote',['','Прибыли и закончили.'])
def test_ungrounded_positive_model_verdict_requires_teacher(verdict,quote):
    c={'actual':'Выезд затруднён.','passed':None}
    result=grounded_evaluation({'verdict':verdict,'reason':'Работы выполнены.','evidence':quote},c['actual'],{})
    apply_evaluation(c,result)
    assert c['passed'] is None and 'credit' not in c
    assert result['verdict']=='uncertain' and result['warning']


def test_grounded_paraphrase_acceptance_and_teacher_cache_protection():
    c={'id':'phone_conversation','actual':'Заезжайте справа, со двора.','expected':'Проезд справа.',
       'passed':None}
    value={'verdict':'full','reason':'Маршрут передан.','evidence':'Заезжайте справа'}
    cached={'conversation_review':{'signature':signature(c),'evaluation':value}}
    assert apply_cached(c,cached) and c['credit']==1
    c.update(teacher_reviewed=True,passed=False,credit=0)
    assert not apply_cached(c,cached) and c['credit']==0


def test_legacy_actor_fallback_is_exact_and_explicit_role_wins():
    assert is_learner({'who':'Диспетчер → Бригада'})
    assert is_learner({'who':'Оператор'})
    assert not is_learner({'who':'Диспетчер другой службы'})
    assert not is_learner({'who':'Диспетчер → Бригада','actor_role':'service'})


def test_speech_context_excludes_future_facts_and_preserves_available_history():
    p=attempt()
    report={'actor_role':'brigade','text':'Как подъехать?','stage_id':'approach','report_id':'report-approach','at':at(10),'contact_id':'brigade'}
    speech={'actor_role':'learner','text':'Данных нет.','at':at(11),'contact_id':'brigade'}
    p.state['messages']=[report,speech,{'actor_role':'caller','text':'Заезд сзади.','at':at(15)}]
    p.state['services']['Служба 102']=[
        {'comment':'Заезд справа.','at':at(5)},
        {'comment':'Теперь проезд перекрыт.','at':at(20)}]
    selected=speech_messages(p.state,p.snapshot,{'stage_id':'approach'})
    context=speech_context(p.state,p.snapshot,selected)
    assert selected==[speech]
    turn=context['turns'][0]
    assert turn['received_before_reply'][0]['text']=='Как подъехать?'
    assert 'Заезд сзади.' not in str(context)
    assert len(turn['available_service_records'])==1
    assert turn['available_service_records'][0]['comment']=='Заезд справа.'
    assert 'данных нет' in context['availability_rule']


def test_pending_manual_points_remain_in_score_denominator():
    result=score({'criteria':[{'weight':20,'passed':True,'critical':False},
                              {'weight':80,'passed':None,'critical':False}]})
    assert result['score']==20 and result['score_is_provisional'] and not result['passed']


def test_querying_caller_on_other_line_preserves_brigade_clarification_scope():
    p=attempt()
    first={'actor_role':'learner','text':'Подождите, уточню.','contact_id':'brigade','at':at(11)}
    answer={'actor_role':'learner','text':'Заезжайте через двор справа.','contact_id':'brigade','at':at(15)}
    p.state['messages']=[
        {'actor_role':'brigade','text':'Как подъехать?','report_id':'report-approach',
         'stage_id':'approach','contact_id':'brigade','at':at(10)},
        first,
        {'actor_role':'learner','text':'Как подъехать?','contact_id':'caller','at':at(12)},
        {'actor_role':'caller','text':'Через двор справа.','report_id':'caller-access',
         'stage_id':'access-source','contact_id':'caller','call_end':True,'at':at(13)},
        answer,
        {'actor_role':'brigade','text':'Понял, до связи.','contact_id':'brigade','call_end':True,'at':at(16)},
        {'actor_role':'learner','text':'Другая тема.','contact_id':'brigade','at':at(17)}]
    selected=speech_messages(p.state,p.snapshot,{'report_id':'report-approach'})
    assert selected==[first,answer]
    context=speech_context(p.state,p.snapshot,selected)
    assert not any(m['text']=='Через двор справа.' for m in context['turns'][0]['received_before_reply'])
    assert any(m['text']=='Через двор справа.' for m in context['turns'][1]['received_before_reply'])


def test_legacy_dds_comment_criterion_uses_only_own_records():
    p=attempt()
    p.snapshot['criteria']=[{'id':'comments','kind':'manual','label':'Комментарии','field':'',
                            'expected':'Прибытие','weight':20,'critical':False}]
    p.state['services']['Служба 101']=[{'status':'Принята','comment':''}]
    p.state['messages']=[{'who':'Диспетчер → Бригада','text':'Всё сделано.'}]
    assert criterion(assess(p),'comments')['credit']==0


def test_initial_system_note_and_later_stage_do_not_replace_acceptance_record():
    p=attempt()
    p.snapshot['criteria']=[{'id':'accept-record','kind':'manual','label':'Принятие','field':'',
        'expected':'Сведения прочитаны.','weight':10,'critical':False,'status':'Принята',
        'evidence_source':'written','required_record':True}]
    p.state['services']['Служба 101']=[
        {'status':'Получена службой','comment':'Карточка поступила из 112.'},
        {'status':'Принята','comment':'','actor_role':'learner'},
        {'status':'Прибытие','comment':'Прибыли.','actor_role':'learner'}]
    assert criterion(assess(p),'accept-record')['credit']==0


def test_approach_comment_at_departure_status_cannot_cover_dispatch_record():
    p=attempt()
    p.snapshot['criteria']=[{'id':'dispatch-record','kind':'manual','label':'Выезд','field':'',
        'expected':'Бригада выехала.','weight':10,'critical':False,'status':'Начало реагирования',
        'evidence_source':'written','required_record':True,'report_id':'report-dispatch','stage_id':'dispatch'}]
    p.state['messages']=[
        {'actor_role':'brigade','text':'Выезжаем.','at':at(5),'report_id':'report-dispatch','stage_id':'dispatch'},
        {'actor_role':'brigade','text':'Как подъехать?','at':at(10),'report_id':'report-approach','stage_id':'approach'}]
    p.state['services']['Служба 101']=[{'status':'Начало реагирования','comment':'Заезд справа.',
        'actor_role':'learner','at':at(15),'report_id':'report-approach','stage_id':'approach','comment_only':True}]
    assert criterion(assess(p),'dispatch-record')['credit']==0
    # A legacy record with no stage metadata still uses its status and timestamp.
    p.state['services']['Служба 101'].append({'status':'Начало реагирования','comment':'Бригада выехала.',
        'actor_role':'learner','at':at(6)})
    assert criterion(assess(p),'dispatch-record')['actual']=='Бригада выехала.'


def test_status_label_is_not_a_quote_from_written_evidence():
    p=attempt();p.state['messages']=[received()]
    p.state['services']['Служба 101']=[{'status':'Прибытие','comment':'Принято.',
        'actor_role':'learner','at':at(12),'report_id':'report-arrived','stage_id':'arrived'}]
    record=criterion(assess(p),'arrival-record')
    assert record['actual']=='Принято.'
    result=grounded_evaluation({'verdict':'full','reason':'Прибытие записано.','evidence':'Прибытие'},
                                record['actual'],{})
    apply_evaluation(record,result)
    assert record['passed'] is None and result['verdict']=='uncertain' and 'credit' not in record


def test_one_missing_required_record_blocks_pass_despite_high_points():
    result=score({'criteria':[{'weight':95,'passed':True,'critical':False,'actual':'Выполнено'},
        {'weight':5,'passed':False,'credit':0,'critical':False,'required_record':True,'actual':''}]})
    assert result['score']==95 and not result['pending']
    assert result['missing_required_records']==1 and not result['passed']
    result['criteria'][1].update(passed=True,credit=1,teacher_reviewed=True)
    # A deliberate teacher override remains supported.
    assert score(result)['passed'] and result['missing_required_records']==0


def test_closed_clarification_does_not_turn_wrong_route_into_correct_speech():
    p=attempt()
    p.snapshot['criteria']=[{'id':'access','kind':'manual','label':'Подъезд','field':'',
        'expected':'Заезд справа.','weight':15,'critical':False,'evidence_source':'speech',
        'report_id':'report-approach','stage_id':'approach'}]
    p.state['messages']=[
        {'actor_role':'brigade','text':'Как подъехать?','at':at(5),'contact_id':'brigade',
         'report_id':'report-approach','stage_id':'approach'},
        {'actor_role':'caller','text':'Заезд справа.','at':at(8),'contact_id':'caller',
         'report_id':'caller-access','stage_id':'access-source','call_end':True},
        {'actor_role':'learner','text':'Заезжайте слева.','at':at(10),'contact_id':'brigade'},
        {'actor_role':'brigade','text':'Понял, до связи.','at':at(11),'contact_id':'brigade','call_end':True}]
    record=criterion(assess(p),'access')
    assert record['actual']=='Заезжайте слева.' and record['passed'] is None
    assert any(m['text']=='Заезд справа.' for m in record['evidence_context']['turns'][0]['received_before_reply'])
    evaluation=grounded_evaluation({'verdict':'incorrect','reason':'Перепутана сторона въезда.',
        'evidence':'Заезжайте слева.'},record['actual'],{})
    apply_evaluation(record,evaluation)
    assert record['passed'] is False and record['credit']==0
