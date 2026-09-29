"""Opt-in local demonstration: distinct starting skills and playable assignments."""
from types import SimpleNamespace
from sqlalchemy import select
from .db import User, Group, Ticket, TicketVersion, Assignment
from .classroom_models import TrainingProfile, MiniQuestion
from .scenario_facts import base_facts,enrich_facts
from .dds_scenarios import generated_dds
from .ticket_difficulty import apply_difficulty
from .schemas import TicketData

def seed_demo_learning(db):
    from .learning import seed_catalog
    seed_catalog(db)
    owner=db.scalar(select(User).where(User.login=='admin'))
    if not owner:return
    titles=['Первые шаги','Базовая подготовка','Самостоятельная работа','Уверенный диспетчер','Опытный диспетчер']
    for n in range(1,6):
        user=db.scalar(select(User).where(User.login==f'student{n}',User.role=='student'))
        if not user:continue
        profile=db.get(TrainingProfile,user.id)
        if not profile:profile=TrainingProfile(user_id=user.id,data={});db.add(profile)
        if profile.data.get('demo_learning_v1'):continue
        profile.data={**profile.data,'demo_learning_v1':True,'demo_level':n-1 if n<5 else 5,'demo_stars':n,'intro_complete':False if n==1 else True}
        group=db.get(Group,user.group_id) if user.group_id else None
        teacher_id=group.teacher_id if group and group.teacher_id else owner.id
        for index,(incident,description,service) in enumerate([
            ('Остановка лифта','В жилом доме лифт остановился между этажами. Два человека отвечают через двери.','ДДС района'),
            ('Прорыв трубы','В подвале жилого дома течёт вода из трубы. Вода растекается по полу.','ДДС района'),
            ('Задымление мусоропровода','В подъезде жилого дома виден дым из мусоропровода. Открытого пламени не видно.','Служба 101')]):
            config=SimpleNamespace(mode='dds',incident_type=incident,traits=[],animals=False,victims_state='no',victims_count=0,own_service=service,services=[service],district='',affiliation='')
            facts=base_facts(incident);facts.update(description=description,victims='Пострадавших нет.',victims_state='no',difficulty_stars=n)
            config.district=facts['area'];enrich_facts(facts,config)
            facts['title']=f'{incident} · {titles[n-1]}'
            ticket=generated_dds(config,facts,{'model':'Подготовленный пример'}).model_dump()
            apply_difficulty(ticket,facts,n)
            task=ticket['tasks'][0];task['source']='Демонстрационное задание для знакомства с уровнем';task['difficulty_level']=n
            data=TicketData.model_validate(ticket).model_dump()
            t=Ticket(title=data['title'],created_by=owner.id);db.add(t);db.flush()
            v=TicketVersion(ticket_id=t.id,number=1,published=True,data=data);db.add(v);db.flush()
            db.add(Assignment(version_id=v.id,student_id=user.id,teacher_id=teacher_id,title=f'{"★"*n} · {titles[n-1]} · {incident}',training=True))
    questions=[
        (2,'В карточке указан один дом, а заявитель по телефону называет другой. Что сделать первым?','Уточнить адрес у заявителя',['Уточнить адрес у заявителя','Выбрать первый адрес','Закрыть карточку']),
        (3,'Бригада приняла заявку. Какое событие подтверждает её прибытие?','Доклад бригады о прибытии',['Доклад бригады о прибытии','Истечение пяти минут','Сам факт передачи заявки']),
        (4,'Бригада сообщила о задержке в пути. Что отразить в карточке?','Причину задержки и полученную информацию о дальнейшем прибытии',['Причину задержки и полученную информацию о дальнейшем прибытии','Статус «Работы завершены»','Ничего до прибытия']),
        (5,'Одна служба завершила работы, другая продолжает. Что должен отражать итоговый комментарий?','Отдельный результат каждой службы и незавершённые действия',['Отдельный результат каждой службы и незавершённые действия','Полное завершение по первому докладу','Только время первого звонка']),
        (5,'Позднее уточнение противоречит первому докладу. Как сохранить проверяемую историю?','Указать источник, время уточнения и что изменилось',['Указать источник, время уточнения и что изменилось','Удалить первый доклад','Оставить удобный вариант'])]
    existing={q.data.get('prompt') for q in db.scalars(select(MiniQuestion))}
    for level,prompt,answer,options in questions:
        if prompt not in existing:db.add(MiniQuestion(owner_id=owner.id,data={'prompt':prompt,'kind':'choice','answer':answer,'options':options,'level':level}))
    db.commit()
