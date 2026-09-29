"""Add a versioned demonstration of the clarified DDS workflow, without changing old tickets."""
from copy import deepcopy
from sqlalchemy import select
from .db import User, Ticket, TicketVersion, Assignment, Attempt
from .schemas import TicketData
from .seed import sample_tasks

def seed_workflow(db):
    marker='ДДС · взаимодействие с бригадой'
    if db.scalar(select(Ticket.id).where(Ticket.title==marker)): return
    admin=db.scalar(select(User).where(User.login=='admin',User.role=='admin'))
    teacher=db.scalar(select(User).where(User.login=='teacher',User.role=='teacher'))
    if not admin or not teacher: return
    task=deepcopy(sample_tasks()[3])
    task.update(title=marker,limit_seconds=30,service_events=[],
        intro='Получена карточка о прорыве трубы. Дом входит в район обслуживания вашей ДДС. Примите карточку, передайте заявку старшему бригады, затем фиксируйте статусы и комментарии по его докладам.',
        validation_note='',
        contacts=[{'id':'unit1','name':'Старший аварийной бригады № 1','kind':'brigade','phone':'1001','response':'Заявка принята: Учебная улица, дом 12. Бригада выезжает.',
                   'updates':[]},
                  {'id':'caller','name':'Учебный заявитель','kind':'caller','phone':task['phone'],'response':'По адресу Учебная, дом 12, подъезд 2 течёт горячая вода. Звонил в 112 по этому поводу.'},
                  {'id':'water','name':'Диспетчер Мосводоканала','kind':'service','service':'Мосводоканал','phone':'1002','response':'Карточку получили. Подтверждаем координацию с вашей бригадой.'}],
        source='Учебная адаптация S4 и ответов заказчика в Telegram №638, 684, 691, 701. Реплики, номера и ситуация созданы для демонстрации, не являются официальным регламентом.')
    task['service_events']=[{'after':delay,'kind':'incoming_call','contact_id':'unit1','trigger_contact':'unit1',
                            'who':'Старший аварийной бригады № 1','text':text}
                           for delay,text in [(20,'По заявке на Учебной, дом 12: прибыли, повреждённый участок ограждён.'),
                                              (40,'По заявке на Учебной, дом 12: перекрыли повреждённый участок, выполняем ремонт.'),
                                              (60,'По заявке на Учебной, дом 12: утечка устранена, работы завершены.')]]
    task['criteria'] += [{'id':'contact','kind':'contact','label':'Связь со старшим бригады','expected':'unit1','weight':20,'critical':True,'skill':'Организация реагирования'}]
    data=TicketData(title=marker,description=task['initial_card']['description'],tasks=[task]).model_dump()
    ticket=db.scalar(select(Ticket).where(Ticket.title=='ДДС · взаимодействие с бригадой и проверка карточки'))
    if ticket:
        ticket.title=marker
        old_versions=list(db.scalars(select(TicketVersion.id).where(TicketVersion.ticket_id==ticket.id)))
        number=max(db.scalars(select(TicketVersion.number).where(TicketVersion.ticket_id==ticket.id)),default=0)+1
    else:
        ticket=Ticket(title=marker,created_by=admin.id);db.add(ticket);db.flush();number=1
    version=TicketVersion(ticket_id=ticket.id,number=number,published=True,data=data);db.add(version);db.flush()
    if number>1:
        for assignment in db.scalars(select(Assignment).where(Assignment.version_id.in_(old_versions),Assignment.lesson_id==None)):
            if not db.scalar(select(Attempt.id).where(Attempt.assignment_id==assignment.id)):
                assignment.version_id=version.id;assignment.title=marker
        db.flush()
    for student in db.scalars(select(User).where(User.login.in_(['student','student2']),User.role=='student')):
        if not db.scalar(select(Assignment.id).where(Assignment.version_id==version.id,Assignment.student_id==student.id)):
            db.add(Assignment(version_id=version.id,student_id=student.id,teacher_id=teacher.id,title=marker))
    db.commit()
