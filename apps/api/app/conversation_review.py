"""Evaluate spoken evidence while the learner is still filling the card."""
import copy,hashlib,json,time
from sqlalchemy import select,update
from .db import Attempt,SessionLocal,now
from .domain import assess

def signature(c):
    return hashlib.sha256(json.dumps([c['actual'],c['expected']],ensure_ascii=False).encode()).hexdigest()

def next_attempt():
    with SessionLocal() as db:
        for p in db.scalars(select(Attempt).where(Attempt.status=='active').order_by(Attempt.id.desc())):
            c=next((c for c in assess(p)['criteria'] if c['id']=='phone_conversation'),None)
            if not c:continue
            cached=p.state.get('conversation_review',{})
            if cached.get('signature')==signature(c):continue
            if cached.get('retry_after',0)>time.time():continue
            return p.id

def generate(id):
    from .semantic_review import ai,SYSTEM,SCHEMA,verified_quote,compact_context
    with SessionLocal() as db:
        p=db.get(Attempt,id)
        if not p or p.status!='active':return
        c=next((c for c in assess(p)['criteria'] if c['id']=='phone_conversation'),None)
        if not c:return
        key=signature(c);context=compact_context(p.card,p.state,p.snapshot['mode'])
        from .answer_memory import examples,rejected_examples
        approved=examples(db,p,c);rejected=rejected_examples(db,p,c)
    try:
        payload=json.dumps({'criterion':c['label'],'expected':c['expected'],'learner_text':c['actual'],'context':context,'teacher_approved_examples':approved,'teacher_rejected_examples':rejected},ensure_ascii=False)
        if len(payload)>14000:raise ValueError('Слишком большой объём разговора для локальной проверки')
        value,meta=ai.complete(SYSTEM,payload,SCHEMA,tokens=240)
        if not isinstance(value.get('reason'),str) or not value['reason'].strip() or not isinstance(value.get('evidence'),str):raise ValueError('Некорректный ответ модели')
        verdict=value['verdict']
        if verdict not in ('full','partial','incorrect','uncertain'):raise ValueError('Некорректная оценка')
        quote,warning=verified_quote(value['evidence'],c['actual'])
        evaluation={**meta,'verdict':verdict,'reason':value['reason'],'evidence':quote,'warning':warning,'at':now()}
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
    cached=state.get('conversation_review',{})
    if c['id']!='phone_conversation' or cached.get('signature')!=signature(c):return False
    value=cached['evaluation'];verdict=value['verdict'];c['ai_evaluation']=value
    if verdict!='uncertain':c['passed']=verdict=='full';c['credit']={'full':1,'partial':.5,'incorrect':0}[verdict]
    return True
