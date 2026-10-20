"""Independent practice cases. Guided introductions remain in their own catalog."""
import os
from sqlalchemy import select
from .db import User,Ticket,TicketVersion,Assignment,Group
from .schemas import TicketData
from .test_catalog import TITLES


def cases():
    def criterion(id,kind,expected,label,weight=10,critical=False):
        return dict(id=id,kind=kind,expected=expected,label=label,weight=weight,critical=critical)
    base=dict(mode='dds',limit_seconds=600,own_service='ДДС района',services=['ДДС района'],questions=[],
              category='Самостоятельная практика',source='Подготовленный учебный сценарий взаимодействия служб.',
              method_note='Оцените решение, полноту передачи сведений и проверяемость записей о ходе реагирования.')
    card=dict(name='Анна Викторовна Громова',caller_status='житель',country='Россия',region='Москва',city='Москва',
              street='Берзарина',house='21',building='1',entrance='3',victims='no',phone='+7 (900) 112-10-21',
              incident_type='Прорыв трубы горячего водоснабжения',
              description='В подвале у третьего подъезда течёт горячая вода, пар выходит на лестницу. Электрощитовая рядом с местом утечки. Жильцы в подвал не заходили, пострадавших нет. Дом обслуживает ваша организация.')
    reports=['Прибыли на Берзарина, 21, корпус 1. Доступ в подвал ограничили, жильцов рядом нет. Повреждена труба горячего водоснабжения.',
             'Повреждённый стояк перекрыли. Поступление воды прекратилось. Электрощитовая сухая. Выполняем замену участка трубы.',
             'Повреждённый участок заменён. Подачу горячей воды восстановили, повторной утечки нет. Подвал осмотрен. Работы завершены.']
    water={**base,'id':'practice-water-v1','title':TITLES[0],'initial_card':card,'expected_card':{},
           'intro':'Примите карточку. Передайте аварийной бригаде точный адрес, место утечки и сведения об электрощитовой. Примите доклады о прибытии, локализации и завершении работ. Отразите ход реагирования и проверенный результат в статусах и комментариях.',
           'contacts':[dict(id='brigade',name='Старший аварийной бригады',phone='1001',kind='brigade',
                            response='Заявку приняли: Берзарина, 21, корпус 1, третий подъезд. Выезжаем. Проверим утечку и состояние электрощитовой.',updates=[],call_audio={'location':'vehicle'})],
           'service_events':[dict(kind='incoming_call',contact_id='brigade',trigger_contact='brigade',who='Старший аварийной бригады',after=delay,stage=stage,text=text)
                             for delay,stage,text in zip([10,25,40],['arrived','working','done'],reports)],
           'criteria':[criterion('accepted','status','Принята','Карточка принята',10,True),
                       criterion('dispatch','contact','brigade','Заявка передана аварийной бригаде',15,True),
                       *[criterion('status-'+str(i),'status',status,'Зарегистрировано: '+status,10) for i,status in enumerate(['Начало реагирования','Прибытие','Проведение работ','Работы завершены'])],
                       criterion('details','manual','Переданы Берзарина, 21, корпус 1, подъезд 3; горячая вода в подвале, рядом электрощитовая; доступ ограничен; стояк перекрыт; участок заменён; подача восстановлена без утечки.','Полнота передачи, хронологии и итогового комментария',25),
                       criterion('response-time','time',60,'Первичное решение за одну минуту',10)]}
    other={**card,'name':'Павел Сергеевич Миронов','street':'Маршала Тухачевского','house':'43','building':'2','entrance':'1',
           'phone':'+7 (900) 112-43-02','incident_type':'Отключение электроснабжения',
           'description':'В первом подъезде нет света в квартирах и на лестнице. Дыма, запаха гари и пострадавших нет. Лифт пуст. В карточке не указана управляющая организация. По справочнику дом относится к УК «Северный квартал», а не к вашей организации.'}
    referral={**base,'id':'practice-referral-v1','title':TITLES[1],'initial_card':other,'expected_card':{},
              'intro':'Проверьте принадлежность дома и свяжитесь с диспетчерской УК «Северный квартал». Передайте адрес и сведения об отключении, получите подтверждение приёма. Зафиксируйте обоснованное непринятие своей службой: кому, когда и какую информацию передали. Нельзя закрывать карточку без подтверждения передачи.',
              'contacts':[dict(id='receiving-dispatcher',name='Диспетчер УК «Северный квартал»',phone='1002',kind='service',
                               response='Подтверждаю: Маршала Тухачевского, 43, корпус 2 обслуживает наша организация. Заявку об отключении первого подъезда приняли, зарегистрировали под номером 214. Электрик направлен.',updates=[],call_audio={'location':'office'})],
              'service_events':[],
              'criteria':[criterion('handover','contact','receiving-dispatcher','Получено подтверждение принимающей диспетчерской',30,True),
                          criterion('refusal','status','Не принята','Зафиксировано обоснованное непринятие своей службой',25,True),
                          criterion('reason','manual','Дом вне зоны обслуживания. Информация передана диспетчеру УК «Северный квартал», заявка 214 принята, электрик направлен. Указаны адрес, отключение первого подъезда, отсутствие дыма и пострадавших.','Причина непринятия и подтверждение передачи отражены в записи',35),
                          criterion('response-time','time',120,'Первичное решение за две минуты',10)]}
    return [TicketData.model_validate(dict(title=t['title'],description=t['intro'],difficulty_stars=2,tasks=[t])).model_dump() for t in (water,referral)]


def seed(db):
    from .voice import prepare
    owner=db.scalar(select(User).where(User.role=='admin'))
    if not owner:return
    selected=[]
    for data in cases():
        key=data['tasks'][0]['id']
        version=next((v for v in db.scalars(select(TicketVersion).order_by(TicketVersion.id.desc())) if any(t.get('id')==key for t in v.data.get('tasks',[]))),None)
        if not version:
            ticket=Ticket(title=data['title'],created_by=owner.id);db.add(ticket);db.flush()
            version=TicketVersion(ticket_id=ticket.id,number=1,published=True,data=prepare(data,db,owner.id));db.add(version);db.flush()
        selected.append(version)
    if os.getenv('DEMO_CLASSROOM')=='1':
        for student in db.scalars(select(User).where(User.role=='student',User.active==True,User.deleted_at==None)):
            group=db.get(Group,student.group_id) if student.group_id else None
            for version in selected:
                if not db.scalar(select(Assignment.id).where(Assignment.student_id==student.id,Assignment.version_id==version.id,Assignment.lesson_id==None)):
                    db.add(Assignment(version_id=version.id,student_id=student.id,teacher_id=group.teacher_id if group and group.teacher_id else owner.id,title=version.data['title'],training=True))
    db.commit()
