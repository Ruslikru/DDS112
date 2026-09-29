"""Four deterministic, guided introductions to the unchanged operational cards."""
import copy,time
from fastapi import APIRouter,Depends
from sqlalchemy import select
from . import main as m
from .db import Ticket,TicketVersion,Assignment,Attempt,User
from .schemas import TicketData
from .dds_flow import create_attempt

router=APIRouter(prefix='/api')

def seed(db):
    owner=db.scalar(select(User).where(User.role=='admin'))
    if not owner:return
    existing={t.get('onboarding') for v in db.scalars(select(TicketVersion)) for t in v.data.get('tasks',[])}
    for mode in ('112','dds'):
        for n in (1,2):
            key=f'{mode}-{n}'
            if key in existing:continue
            incident='Задымление мусоропровода' if n==1 else 'Прорыв трубы'
            street='Декабристов' if n==1 else 'Конёнкова';house='28' if n==1 else '26'
            service='Служба 101' if n==1 else 'ДДС района'
            description='В подъезде виден дым из мусоропровода. Пострадавших нет.' if n==1 else 'В подвале течёт вода из трубы. Пострадавших нет.'
            title=f'{"112" if mode=="112" else "ДДС"} · Первые шаги {n}: {"приём заявки" if mode=="112" else "реагирование"}'
            card={'name':'Елена Андреевна Соколова','caller_status':'очевидец','country':'Россия','region':'Москва','city':'Москва','street':street,'house':house,'description':description,'incident_type':incident,'victims':'no','phone':'+7 (000) 000-00-01'}
            task={'id':key,'onboarding':key,'title':title,'mode':mode,'category':'Знакомство с интерфейсом','intro':f'Меня зовут Елена Андреевна Соколова. Адрес: Москва, улица {street}, дом {house}. {description}',
                  'limit_seconds':7200,'own_service':service,'services':[service],'type_options':[incident],'traits':[],'initial_card':card if mode=='dds' else {},'expected_card':card,
                  'questions':[{'id':'name','question':'Как вас зовут?','answer':card['name']+'. Я очевидец.'},{'id':'address','question':'Назовите точный адрес','answer':f'Москва, улица {street}, дом {house}.'},{'id':'details','question':'Что произошло? Есть ли пострадавшие?','answer':description}],
                  'contacts':[{'id':'brigade','name':'Старший бригады','phone':'1001','kind':'brigade','response':'Заявку приняли. Выезжаем по указанному адресу.','updates':['Мы прибыли. Обстановка соответствует заявке.','Работы завершены. Опасность устранена.']} ] if mode=='dds' else [],
                  'criteria':([{'id':k,'kind':'field','field':k,'expected':card[k],'label':label,'weight':10} for k,label in [('name','Указан заявитель'),('street','Указана улица'),('house','Указан дом'),('incident_type','Выбран тип происшествия'),('victims','Указаны пострадавшие')]]+[{'id':'notify','kind':'service','expected':service,'label':'Служба оповещена','weight':10}]) if mode=='112' else [{'id':'accept','kind':'status','expected':'Принята','label':'Карточка принята','weight':10},{'id':'dispatch','kind':'contact','expected':'brigade','label':'Заявка передана бригаде','weight':10},{'id':'done','kind':'status','expected':'Работы завершены','label':'Результат зарегистрирован','weight':10}]}
            data=TicketData.model_validate({'title':title,'description':'Пошаговое знакомство с интерфейсом. Жёлтая подсказка показывает следующее действие.','difficulty_stars':1,'tasks':[task]}).model_dump()
            ticket=Ticket(title=title,created_by=owner.id);db.add(ticket);db.flush()
            db.add(TicketVersion(ticket_id=ticket.id,number=1,published=True,data=data))
    # Upgrade only the built-in introductions; authored tickets retain their scenarios.
    from .voice import prepare,attach_audio
    from .db import ScheduledEvent
    def upgrade(task):
        task=copy.deepcopy(task)
        if task.get('mode')=='dds' and task.get('onboarding') and not task.get('service_events'):
            task['service_events']=[{'kind':'incoming_call','contact_id':'brigade','trigger_contact':'brigade','who':'Старший бригады','stage':stage,'respect_delay':True,'after':delay,'text':text} for stage,delay,text in [('arrived',10,'Мы прибыли. Обстановка соответствует заявке.'),('done',35,'Работы завершены. Опасность устранена.')]]
        return task
    for v in db.scalars(select(TicketVersion)):
        if any(t.get('onboarding','') and t['mode']=='dds' and not t.get('service_events') for t in v.data['tasks']):
            updated=copy.deepcopy(v.data);updated['tasks']=[upgrade(t) for t in updated['tasks']]
            v.data=prepare(updated,db,owner.id)
    for attempt in db.scalars(select(Attempt).where(Attempt.status.notin_(['completed','aborted']))):
        updated=upgrade(attempt.snapshot)
        if updated!=attempt.snapshot:
            attempt.snapshot=prepare({'tasks':[updated]},db,owner.id)['tasks'][0]
            if attempt.state.get('contact_counts',{}).get('brigade',0):
                for event in attempt.snapshot['service_events']:db.add(ScheduledEvent(attempt_id=attempt.id,due=time.time()+event['after'],data=event))
    db.commit()

@router.get('/tutorials')
def catalog(u=Depends(m.current),db=Depends(m.getdb)):
    from .voice import readiness
    rows=[]
    for v in db.scalars(select(TicketVersion).where(TicketVersion.published==True)):
        if not v.data.get('tasks'):continue
        key=v.data['tasks'][0].get('onboarding')
        if not key or any(x['key']==key for x in rows):continue
        attempts=db.scalars(select(Attempt).join(Assignment).where(Assignment.version_id==v.id,Attempt.student_id==u.id)).all()
        rows.append({'key':key,'version_id':v.id,'title':v.data['title'],'completed':any(p.status=='completed' for p in attempts),'mode':v.data['tasks'][0]['mode'],'voice':readiness({'tasks':[v.data['tasks'][0]]},db)})
    return sorted(rows,key=lambda x:x['key'])

@router.post('/tutorials/{id}/start')
def start_tutorial(id:int,u=Depends(m.current),db=Depends(m.getdb)):
    v=db.get(TicketVersion,id)
    if not v or not v.published or not v.data.get('tasks') or not v.data['tasks'][0].get('onboarding'):m.fail('Вводный билет не найден',404)
    a=db.scalar(select(Assignment).where(Assignment.version_id==id,Assignment.student_id==u.id))
    if not a:
        a=Assignment(version_id=id,student_id=u.id,teacher_id=u.id,title=v.data['title'],training=True);db.add(a);db.flush()
    active=db.scalar(select(Attempt).where(Attempt.assignment_id==a.id,Attempt.status.notin_(['completed','aborted'])))
    p=active or create_attempt(db,a,v.data['tasks'][0],0)
    p.state={**p.state,'teacher_assisted':True,'guided':True};db.commit()
    return m.attempt_view(p,u)

@router.post('/tickets/{id}/try')
def try_ticket(id:int,data:dict,u=Depends(m.current),db=Depends(m.getdb)):
    m.staff(u);v=db.get(TicketVersion,id)
    if not v:m.fail('Билет не найден',404)
    index=data.get('task_index',0)
    if not isinstance(index,int) or not 0<=index<len(v.data['tasks']):m.fail('Задание не найдено')
    a=Assignment(version_id=id,student_id=u.id,teacher_id=u.id,title='Просмотр преподавателя: '+v.data['title'][:160],training=True);db.add(a);db.flush()
    p=create_attempt(db,a,v.data['tasks'][index],index,preview=True)
    p.state={**p.state,'preview':True,'teacher_assisted':True};db.commit()
    return m.attempt_view(p,u)
