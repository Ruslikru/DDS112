"""Published advanced communication scenarios, without changing authored tickets."""
import copy
from sqlalchemy import select
from .db import Ticket,TicketVersion,User
from .schemas import TicketData

def seed(db):
    owner=db.scalar(select(User).where(User.role=='admin'))
    base=next((v.data['tasks'][0] for v in db.scalars(select(TicketVersion)) if v.data.get('tasks') and v.data['tasks'][0].get('onboarding')=='dds-2'),None)
    if not owner or not base:return
    from .voice import prepare
    cases=[('ДДС · Контроль задержавшейся бригады',3,[],['Задерживаемся в пути. Ориентировочное прибытие через десять минут.','Мы прибыли. Начинаем работы.','Работы завершены.'], 'Если после выезда долго нет сведений, самостоятельно свяжитесь с бригадой. Уточните причину задержки и время прибытия. Зарегистрируйте сведения.'),
           ('ДДС · ЧП по дороге и резервная бригада',4,[{'kind':'incoming_call','contact_id':'brigade','trigger_contact':'brigade','who':'Старший бригады','after':20,'respect_delay':True,'text':'Машина неисправна, остановились по дороге. Пострадавших нет. Продолжать движение не можем. Нужна резервная бригада.'}],[], 'Примите доклад о поломке. Уточните безопасность людей, организуйте резерв и зафиксируйте изменение реагирования.')]
    for title,level,events,updates,note in cases:
        if db.scalar(select(Ticket.id).where(Ticket.title==title)):continue
        task=copy.deepcopy(base);task.update(id='communications-'+str(level),title=title,onboarding=None,service_events=events,method_note=note)
        task['contacts'][0].update(updates=updates,voice_lines=[])
        if level==4:task['contacts'].append({'id':'reserve','name':'Резервная бригада','phone':'1002','kind':'brigade','response':'Резервная бригада заявку приняла. Выезжаем.','updates':['Мы прибыли. Работы начаты.','Работы завершены.']})
        task['criteria'].append({'id':'coordination','kind':'manual','label':'Контроль реагирования и решение проблемы','field':'','expected':note,'weight':20,'skill':'Координация служб'})
        if level==4:task['criteria'].append({'id':'reserve','kind':'contact','expected':'reserve','label':'Вызвана резервная бригада','weight':20,'skill':'Координация служб'})
        data=TicketData.model_validate({'title':title,'difficulty':'Сложный','difficulty_stars':level,'description':note,'tasks':[task]}).model_dump()
        ticket=Ticket(title=title,created_by=owner.id);db.add(ticket);db.flush()
        db.add(TicketVersion(ticket_id=ticket.id,number=1,published=True,data=prepare(data,db,owner.id)))
    db.commit()
