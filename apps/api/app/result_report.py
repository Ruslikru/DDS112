"""Durable summaries of already checked criteria, without another model request."""
import copy
import time
from sqlalchemy import select, update
from .db import Attempt, SessionLocal, now
from .domain import assess,score
from .conversation_review import apply_cached,ready_for_review
from .evidence import is_learner
from types import SimpleNamespace

def recover():
    with SessionLocal() as db:
        for p in db.scalars(select(Attempt).where(Attempt.status=='completed')):
            if not p.assessment:continue
            a=copy.deepcopy(p.assessment)
            if not a.get('report_job') or a['report_job'].get('status')=='running':
                a['report_job']={'status':'done' if a.get('ai_review') else 'queued','at':now()}
                p.assessment=a;p.revision+=1
        db.commit()

def evidence(p):
    dialogue=[x for x in p.state.get('dialogue',[]) if is_learner(x)]
    messages=[x for x in p.state.get('messages',[]) if is_learner(x)]
    criteria=[{k:c.get(k) for k in ('label','expected','actual','passed','credit','teacher_reviewed','evidence_reason')} for c in p.assessment['criteria']]
    for source,criterion in zip(p.assessment['criteria'],criteria):
        if source['id']=='phone_conversation':criterion['actual']='\n'.join(x['who']+': '+x.get('text','') for x in dialogue+messages)
    return {'criteria':criteria,
            'card':{k:v for k,v in p.card.items() if v},
            'dialogue':dialogue,'messages':messages}

def prepared(p):
    grade=assess(p)
    for c in grade['criteria']:apply_cached(c,p.state)
    return SimpleNamespace(assessment=score(grade),card=p.card,state=p.state)

def next_warm():
    with SessionLocal() as db:
        for p in db.scalars(select(Attempt).where(Attempt.status=='active').order_by(Attempt.id.desc())):
            if not ready_for_review(p):continue
            candidate=prepared(p)
            if candidate.assessment['pending']:continue
            cache=p.state.get('warm_report',{})
            if cache.get('evidence')==evidence(candidate) or cache.get('retry_after',0)>time.time():continue
            return p.id

def next_attempt():
    with SessionLocal() as db:
        for p in db.scalars(select(Attempt).where(Attempt.status=='completed').order_by(Attempt.id)):
            a=p.assessment or {};job=a.get('report_job',{})
            if not job or job.get('status') in ('done','error'):continue
            if job.get('status')=='running' and time.time()-job.get('started',0)<300:continue
            if job.get('retry_after',0)>time.time():continue
            if any(c['kind']=='manual' and c.get('passed') is None and not c.get('teacher_reviewed') for c in a.get('criteria',[])) and a.get('semantic_review',{}).get('status') not in ('done','error'):continue
            return p.id


def summarize(assessment):
    """Report established grades without asking the model to reassess them."""
    a=score(copy.deepcopy(assessment))
    if a['pending']:
        summary='Для завершения проверки требуется решение преподавателя по оставшимся критериям.'
    elif a['score'] is None:
        summary='Нет оценённых критериев для итогового результата.'
    else:
        summary=f"Работа {'зачтена' if a['passed'] else 'не зачтена'}: {a['score']} из 100."
    missing=[c for c in a['criteria'] if c.get('required_record') and not str(c.get('actual') or '').strip() and c.get('passed') is not True]
    problems=[c for c in a['criteria'] if c.get('passed') is False or c.get('credit',1)<1]
    if missing:
        recommendation='Оформите обязательные записи: '+', '.join(c['label'] for c in missing)+'.'
    elif problems:
        c=next((c for c in problems if c.get('critical')),problems[0])
        reason=c.get('evidence_reason') or c.get('ai_evaluation',{}).get('reason')
        recommendation='Повторите действие «'+c['label']+'».'+(' '+reason if reason else '')
    elif a['pending']:
        recommendation='Обсудите с преподавателем критерии, по которым пока нет подтверждённой оценки.'
    else:
        recommendation='Продолжайте тренировку, сохраняя последовательность действий и полноту записей.'
    return {'summary':summary,'recommendation':recommendation,'at':now(),'advisory':True,'source':'criteria'}

def generate(attempt_id):
    with SessionLocal() as db:
        p=db.get(Attempt,attempt_id)
        if not p or p.status not in ('active','completed'):return
        warm=p.status=='active'
        if warm:
            candidate=prepared(p);payload=evidence(candidate);a=candidate.assessment
        else:
            payload=evidence(p);a=copy.deepcopy(p.assessment)
        revision=p.revision
        a['report_job']={'status':'running','started':time.time(),'at':now()}
        if not warm:
            claimed=db.execute(update(Attempt).where(Attempt.id==p.id,Attempt.revision==revision).values(assessment=a,revision=revision+1));db.commit()
            if claimed.rowcount!=1:return
    result=None
    try:
        result=summarize(a)
        job={'status':'done','at':now()}
    except Exception as error:
        job={'status':'error','error':str(error)[:500]}
    with SessionLocal() as db:
        p=db.scalar(select(Attempt).where(Attempt.id==attempt_id).with_for_update())
        if not p:return
        if p.status=='active':
            if result and evidence(prepared(p))==payload:p.state={**p.state,'warm_report':{'evidence':payload,'review':result}}
            elif not result:p.state={**p.state,'warm_report':{'retry_after':time.time()+30}}
            db.commit();return
        if not p.assessment:return
        a=copy.deepcopy(p.assessment)
        if evidence(p)!=payload:job={'status':'queued','at':now()};result=None
        if result:a['ai_review']=result
        a['report_job']=job;p.assessment=a;p.revision+=1;db.commit()
