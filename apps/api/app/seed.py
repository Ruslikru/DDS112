import os
from copy import deepcopy
from sqlalchemy import select
from argon2 import PasswordHasher
from .db import User, Group, Ticket, TicketVersion, Assignment

def field(id,label,value,weight=10,critical=False):
    return {'id':id,'label':label,'kind':'field','field':id,'expected':value,'weight':weight,'critical':critical,'skill':'Карточка и классификация'}

def sample_tasks():
    smoke={
        'id':'smoke','title':'Задымление мусоропровода','mode':'112','category':'Пожар и задымление',
        'intro':'Здравствуйте! У нас в доме дым из мусоропровода. Пожалуйста, пришлите помощь!',
        'phone':'+7 (000) 000-00-01','source':'S2, билет 2, задача 1. Контакты заменены учебными.',
        'method_note':'',
        'limit_seconds':300,'own_service':'ДДС района','intro_audio':None,
        'questions':[
            {'id':'address','question':'Назовите адрес, подъезд и код домофона.','answer':'Москва, улица Берзарина, дом 21, корпус 1. Третий подъезд, домофон 68.','required':True},
            {'id':'fire','question':'Вы видите открытое пламя?','answer':'Нет, открытого пламени не вижу. Только дым из мусоропровода.','required':True},
            {'id':'victims','question':'Есть ли пострадавшие?','answer':'Пострадавших людей нет, насколько мне известно.','required':True},
            {'id':'floor','question':'На каком вы этаже и сколько этажей в доме?','answer':'Я на седьмом этаже, всего в доме семнадцать этажей.','required':False},
            {'id':'name','question':'Как вас зовут?','answer':'Учебный заявитель. Я жилец этого дома.','required':True}
        ],
        'initial_card':{},'expected_card':{'name':'Учебный заявитель','caller_status':'очевидец','region':'Москва','city':'Москва','street':'Берзарина','house':'21','building':'1','entrance':'3','code':'68','victims':'no','incident_type':'Задымление мусоропровода','traits':['Дом многоквартирный','Дым','Мусоропровод'],'description':'Дым из мусоропровода. Пламя не наблюдается. Со слов заявителя пострадавших нет. Заявитель на 7 этаже, дом 17 этажей.'},
        'type_options':['Задымление мусоропровода','Пожар в квартире','ДТП без пострадавших'],
        'traits':['Дом многоквартирный','Дым','Открытое пламя','Мусоропровод','Квартира','Угроза людям'],
        'services':['Служба 101','ДДС района'],
        'routing':[{'type':'Задымление мусоропровода','services':['Служба 101','ДДС района']},{'type':'Пожар в квартире','services':['Служба 101','ДДС района']},{'victims':'yes','services':['Служба 103']}],
        'service_events':[],
        'criteria':[field('street','Правильно указана улица','Берзарина',15,True),field('house','Правильно указан дом','21',10,True),field('building','Указан корпус','1'),field('incident_type','Выбрано задымление мусоропровода','Задымление мусоропровода',20),field('victims','Пострадавшие — нет по сообщению заявителя','no'),{'id':'ask-victims','label':'Уточнено наличие пострадавших','kind':'question','expected':'victims','weight':10,'skill':'Опрос заявителя'}, {'id':'service101','label':'Оповещена служба 101','kind':'service','expected':'Служба 101','weight':15,'critical':True,'skill':'Оповещение'}, {'id':'description','label':'Полнота описания со слов заявителя','kind':'manual','expected':'Отражены дым, мусоропровод, отсутствие видимого пламени, этаж заявителя и этажность дома.','weight':10,'skill':'Описание'}, {'id':'time','label':'Учебный срок заполнения — 5 минут','kind':'time','expected':300,'weight':5,'skill':'Время'}]
    }
    accident=deepcopy(smoke)
    accident.update(id='accident',title='ДТП на МКАД',category='ДТП',intro='На МКАД столкнулись две машины. Нам нужна помощь.',source='S2, билет 25, задача 2; учебная адаптация с дополненными ответами.',questions=[{'id':'address','question':'Где произошло ДТП?','answer':'МКАД, от Варшавского шоссе в сторону Каширского, напротив ТЦ Вегас, в левом ряду.','required':True},{'id':'victims','question':'Есть пострадавшие или заблокированные?','answer':'Пострадавших нет. Никто не заблокирован.','required':True},{'id':'cars','question':'Какие автомобили участвовали?','answer':'Пежо и Фольксваген.','required':True}],expected_card={'street':'МКАД','address_note':'От Варшавского шоссе в сторону Каширского, напротив ТЦ Вегас, левый ряд','victims':'no','incident_type':'ДТП без пострадавших','description':'Столкновение Пежо и Фольксваген, без пострадавших и заблокированных.'},type_options=['ДТП без пострадавших','ДТП с пострадавшими','Пожар автомобиля'],traits=['Два автомобиля','Нет пострадавших','Есть пострадавшие','Есть заблокированные','Разлив топлива'],services=['Служба 102','ЦОДД'],routing=[{'type':'ДТП без пострадавших','services':['Служба 102','ЦОДД']},{'type':'ДТП с пострадавшими','services':['Служба 102','Служба 103','ЦОДД']}],criteria=[field('street','Указана МКАД','МКАД',20),field('incident_type','Верно выбран тип ДТП','ДТП без пострадавших',25),field('victims','Пострадавшие отсутствуют','no',15),{'id':'q','label':'Уточнены пострадавшие','kind':'question','expected':'victims','weight':15,'skill':'Опрос заявителя'},{'id':'service','label':'Оповещена служба 102','kind':'service','expected':'Служба 102','weight':15,'critical':True,'skill':'Оповещение'},{'id':'desc','label':'Указаны направление, ориентир и ряд','kind':'manual','expected':'От Варшавского к Каширскому, ТЦ Вегас, левый ряд.','weight':10,'skill':'Описание'}])
    gas=deepcopy(smoke)
    gas.update(id='gas',title='Запах газа в частном доме',category='Газ',intro='В частном доме пахнет газом, у ввода трубы слышно шипение.',source='S2, билет 30, задача 3; учебная адаптация.',questions=[{'id':'address','question':'Назовите адрес.','answer':'Москва, Вороновское, посёлок ЛМС, микрорайон Солнечный, дом 20.','required':True},{'id':'gas','question':'Газ магистральный или баллонный?','answer':'Магистральный. Запах у трубы на вводе в дом.','required':True},{'id':'victims','question':'Требуется медицинская помощь?','answer':'Нет, медицинская помощь не требуется.','required':True}],expected_card={'street':'Солнечный','house':'20','victims':'no','incident_type':'Запах газа в помещении','description':'Запах магистрального газа и шум у трубы на вводе в частный дом. Медицинская помощь не требуется.'},type_options=['Запах газа в помещении','Запах газа на улице','Пожар в квартире'],traits=['Частный дом','Магистральный газ','Баллонный газ','Угроза людям'],services=['Служба 104'],routing=[{'type':'Запах газа в помещении','services':['Служба 104']},{'type':'Запах газа на улице','services':['Служба 104']}],criteria=[field('house','Верный номер дома','20',20),field('incident_type','Верный тип происшествия','Запах газа в помещении',25),{'id':'gas','label':'Уточнён вид газа','kind':'question','expected':'gas','weight':20,'skill':'Опрос заявителя'},{'id':'service','label':'Оповещена служба 104','kind':'service','expected':'Служба 104','weight':25,'critical':True,'skill':'Оповещение'},{'id':'desc','label':'Описание обстоятельств','kind':'manual','expected':'Магистральный газ, труба на вводе, частный дом.','weight':10,'skill':'Описание'}])
    dds=deepcopy(smoke)
    dds.update(id='dds-water',title='ДДС: прорыв трубы',mode='dds',category='Коммунальная авария',intro='Поступила карточка 112. В подъезде жилого дома течёт горячая вода. Дом находится в зоне ответственности вашей службы.',source='S4, стр. 31: пример необходимости регистрации хода работ. Адрес и события учебные.',questions=[],initial_card={'name':'Учебный заявитель','street':'Учебная','house':'12','entrance':'2','incident_type':'Прорыв трубы горячего водоснабжения','victims':'unknown','description':'Горячая вода заливает подъезд. Дом обслуживается вашей организацией.'},expected_card={},type_options=['Прорыв трубы горячего водоснабжения'],traits=[],services=['ДДС района','Мосводоканал'],routing=[],service_events=[{'after_seconds':10,'text':'Бригада: выехали к дому 12 на Учебной улице.','suggested_status':'Начало реагирования'},{'after_seconds':22,'text':'Бригада: прибыли, перекрываем повреждённый участок.','suggested_status':'Прибытие'},{'after_seconds':35,'text':'Бригада: аварийные работы начаты.','suggested_status':'Проведение работ'},{'after_seconds':48,'text':'Бригада: утечка устранена, работы завершены.','suggested_status':'Работы завершены'}],criteria=[{'id':'ack','label':'Карточка принята к реагированию','kind':'status','expected':'Принята','weight':20,'critical':True,'skill':'Принятие карточки'},{'id':'depart','label':'Зарегистрировано начало реагирования','kind':'status','expected':'Начало реагирования','weight':15,'skill':'Статусы ДДС'},{'id':'finish','label':'Зарегистрировано завершение работ','kind':'status','expected':'Работы завершены','weight':25,'skill':'Статусы ДДС'},{'id':'time','label':'Первичное решение принято за 30 секунд','kind':'time','expected':30,'weight':20,'skill':'Время'},{'id':'comment','label':'Комментарии отражают ход и результат работ','kind':'manual','expected':'Выезд бригады, проведение работ и устранение утечки.','weight':20,'skill':'Комментарии ДДС'}])
    refusal=deepcopy(dds)
    refusal.update(id='dds-refusal',title='ДДС: карточка вне зоны обслуживания',category='Обоснованный отказ',intro='Поступила карточка. Дом обслуживает другая управляющая организация. Вы уточнили принадлежность и передали информацию в её диспетчерскую.',source='S4, стр. 30: причины непринятия и информация о передаче; учебная адаптация.',initial_card={**dds['initial_card'],'house':'18','description':'Пожарная сигнализация в доме 18. Дом обслуживает УК «Учебная». Информация передана диспетчеру этой УК.'},service_events=[],criteria=[{'id':'reject','label':'Выбран статус «Не принята»','kind':'status','expected':'Не принята','weight':50,'critical':True,'skill':'Принятие карточки'},{'id':'comment','label':'Причина и факт передачи отражены в комментарии','kind':'manual','expected':'Дом не обслуживается; информация передана диспетчеру УК «Учебная».','weight':30,'skill':'Комментарии ДДС'},{'id':'time','label':'Первичный статус за 30 секунд','kind':'time','expected':30,'weight':20,'skill':'Время'}])
    from .caller import enrich_task, generated_details
    for task in (smoke,accident,gas):
        task['scenario_details']=generated_details(task)
    return [enrich_task(t) for t in [smoke,accident,gas,dds,refusal]]

def seed(db):
    if db.scalar(select(User.id).limit(1)): return
    from .schemas import TicketData
    password=os.getenv('DEMO_PASSWORD','Training112!')
    ph=PasswordHasher()
    admin=User(login='admin',name='Администратор',role='admin',password_hash=ph.hash(password),audit_access=True)
    teacher=User(login='teacher',name='Елена Волкова',role='teacher',password_hash=ph.hash(password))
    db.add_all([admin,teacher]);db.flush()
    group=Group(name='Учебная группа № 1',teacher_id=teacher.id);db.add(group);db.flush()
    students=[User(login='student',name='Алексей Морозов',role='student',password_hash=ph.hash(password),group_id=group.id),User(login='student2',name='Мария Соколова',role='student',password_hash=ph.hash(password),group_id=group.id)]
    db.add_all(students);db.flush()
    for i,task in enumerate(sample_tasks()):
        ticket=Ticket(title=task['title'],created_by=admin.id);db.add(ticket);db.flush()
        data=TicketData.model_validate({'title':task['title'],'description':task.get('initial_card',{}).get('description') or task['intro'],'tasks':[task]}).model_dump()
        version=TicketVersion(ticket_id=ticket.id,number=1,published=True,data=data);db.add(version);db.flush()
        for student in students:
            db.add(Assignment(version_id=version.id,student_id=student.id,teacher_id=teacher.id,title=f'Билет {i+1:02d} · {task["title"]}'))
    db.commit()


def ensure_local_demo_students(db):
    """Add the five named demonstration logins without changing existing users."""
    from .db import User, Group
    group = db.scalar(select(Group).order_by(Group.id))
    if not group:
        return
    existing = set(db.scalars(select(User.login)).all())
    ph = PasswordHasher()
    names=['Дмитрий Сергеевич Орлов','Мария Андреевна Соколова','Артём Игоревич Кузнецов','Анна Павловна Белова','Илья Максимович Лебедев']
    for number in range(1, 6):
        login = f'student{number}'
        if login not in existing:
            db.add(User(login=login, name=names[number-1], role='student',
                        password_hash=ph.hash('12345678'), group_id=group.id))
        else:
            student=db.scalar(select(User).where(User.login==login))
            if student and student.name==f'Студент {number}':student.name=names[number-1]
    db.commit()
