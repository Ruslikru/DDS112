"""Evaluate spoken evidence while the learner is still filling the card."""
import copy,hashlib,json,time
from sqlalchemy import select,update
from .db import Attempt,SessionLocal,now
from .domain import assess

def signature(c):
    return hashlib.sha256(json.dumps([c['actual'],c['expected'],c.get('evidence_context')],ensure_ascii=False).encode()).hexdigest()

def ready_for_review(p):
    if p.snapshot['mode']=='112':return p.state.get('call')=='ended'
    history=p.state.get('services',{}).get(p.snapshot['own_service'],[])
    return bool(history) and history[-1].get('status') in ('Работы завершены','Отказ от выполнения работ','Не принята')

def next_attempt():
    with SessionLocal() as db:
        for p in db.scalars(select(Attempt).where(Attempt.status=='active').order_by(Attempt.id.desc())):
            if not ready_for_review(p):continue
            c=next((c for c in assess(p)['criteria'] if c['id']=='phone_conversation'),None)
            if not c:continue
            cached=p.state.get('conversation_review',{})
            if cached.get('signature')==signature(c):continue
            if cached.get('retry_after',0)>time.time():continue
            return p.id

def generate(id):
    from .semantic_review import ai,SYSTEM,SCHEMA,grounded_evaluation,compact_context,model_context
    with SessionLocal() as db:
        p=db.get(Attempt,id)
        if not p or p.status!='active':return
        c=next((c for c in assess(p)['criteria'] if c['id']=='phone_conversation'),None)
        if not c:return
        key=signature(c);context=c.get('evidence_context') or compact_context(p.card,p.state,p.snapshot['mode'])
        from .answer_memory import examples,rejected_examples
        approved=examples(db,p,c);rejected=rejected_examples(db,p,c)
    try:
        payload=json.dumps({'criterion':c['label'],'expected':c['expected'],'learner_text':c['actual'],'context':model_context(context),'teacher_approved_examples':approved,'teacher_rejected_examples':rejected},ensure_ascii=False,separators=(',',':'))
        if len(payload)>14000:raise ValueError('Слишком большой объём разговора для локальной проверки')
        value,meta=ai.complete(SYSTEM,payload,SCHEMA,tokens=240,priority=10)
        evaluation=grounded_evaluation(value,c['actual'],meta)
        cached={'signature':key,'evaluation':evaluation}
    except Exception as error:
        cached={'error':str(error)[:300],'retry_after':time.time()+30}
    with SessionLocal() as db:
        p=db.get(Attempt,id)
        if not p:return
        current=next((c for c in (p.assessment or assess(p))['criteria'] if c['id']=='phone_conversation'),None)
        if not current or signature(current)!=key:return
        state=copy.deepcopy(p.state);state['conversation_review']=cached
        db.execute(update(Attempt).where(Attempt.id==id,Attempt.revision==p.revision).values(state=state));db.commit()

def apply_cached(c,state):
    from .semantic_review import grounded_evaluation,apply_evaluation
    cached=state.get('conversation_review',{})
    if c.get('teacher_reviewed') or c['id']!='phone_conversation' or cached.get('signature')!=signature(c) or not cached.get('evaluation'):return False
    value=cached['evaluation']
    apply_evaluation(c,grounded_evaluation(value,c['actual'],value))
    return True
