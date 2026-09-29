"""Teacher-approved exemplars scoped to the exact facts and rubric, never self-training."""
import hashlib
import json
from sqlalchemy import select
from .classroom_models import ApprovedAnswer

def scope_for(attempt, criterion):
    source={k:attempt.snapshot.get(k) for k in ('mode','id','expected_card','initial_card','own_service')}
    source.update(criterion={k:criterion.get(k) for k in ('id','label','expected','field')})
    return hashlib.sha256(json.dumps(source,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()

def remember(db, attempt, criterion, teacher, accepted):
    rows=db.scalars(select(ApprovedAnswer).where(ApprovedAnswer.attempt_id==attempt.id,
        ApprovedAnswer.criterion_id==criterion['id'])).all()
    for row in rows: row.active=False
    text=str(criterion.get('actual','')).strip()
    if accepted and text and criterion['kind']=='manual':
        db.add(ApprovedAnswer(scope=scope_for(attempt,criterion),text=text[:14000],
            criterion=criterion['label'],attempt_id=attempt.id,criterion_id=criterion['id'],teacher_id=teacher.id))

def examples(db, attempt, criterion):
    return [x.text for x in db.scalars(select(ApprovedAnswer).where(
        ApprovedAnswer.scope==scope_for(attempt,criterion),ApprovedAnswer.active==True)
        .order_by(ApprovedAnswer.id.desc()).limit(4))]


def rejected_examples(db, attempt, criterion):
    """Use the latest explicit teacher correction, never a model's own verdict."""
    from .db import Attempt
    result=[]
    scope=scope_for(attempt,criterion)
    for other in db.scalars(select(Attempt).where(Attempt.assessment.is_not(None)).order_by(Attempt.id.desc()).limit(200)):
        for c in (other.assessment or {}).get('criteria',[]):
            if c.get('kind')=='manual' and c.get('teacher_reviewed') and c.get('passed') is False and scope_for(other,c)==scope:
                reviews=(other.assessment or {}).get('reviews',[])
                reason=next((r.get('reason','') for r in reversed(reviews) if c['id'] in r.get('criteria',{}) or r.get('confirm')),'')
                result.append({'answer':str(c.get('actual',''))[:1500],'reason':reason[:500],'credit':c.get('credit',0)})
                if len(result)>=2:return result
    return result
