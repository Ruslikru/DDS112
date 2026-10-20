"""A new classroom starts with two guided DDS tickets."""
import os
from argon2 import PasswordHasher
from sqlalchemy import select
from .db import User,Group

def seed(db):
    if db.scalar(select(User.id).limit(1)):
        ensure_starter_students(db)
        return
    password=PasswordHasher().hash(os.getenv('DEMO_PASSWORD','Training112!'))
    admin=User(login='admin',name='Администратор',role='admin',password_hash=password,audit_access=True)
    teacher=User(login='teacher',name='Елена Волкова',role='teacher',password_hash=password)
    db.add_all([admin,teacher]);db.flush()
    group=Group(name='Учебная группа № 1',teacher_id=teacher.id);db.add(group);db.flush()
    names=['Алексей Морозов','Мария Соколова','Артём Игоревич Кузнецов','Анна Павловна Белова','Илья Максимович Лебедев']
    db.add_all([User(login='student' if n==1 else f'student{n}',name=name,role='student',password_hash=password,group_id=group.id) for n,name in enumerate(names,1)])
    db.commit()

def ensure_starter_students(db):
    """Complete older starter classrooms without changing their users or passwords."""
    first=db.scalar(select(User).where(User.login=='student',User.role=='student'))
    second=db.scalar(select(User).where(User.login=='student2',User.role=='student'))
    if not first or not second or not first.group_id or first.group_id!=second.group_id:return
    names={3:'Артём Игоревич Кузнецов',4:'Анна Павловна Белова',5:'Илья Максимович Лебедев'}
    existing=set(db.scalars(select(User.login)))
    missing=[n for n in names if f'student{n}' not in existing]
    if not missing:return
    password=PasswordHasher().hash(os.getenv('DEMO_PASSWORD','12345678'))
    for n in missing:
        db.add(User(login=f'student{n}',name=names[n],role='student',password_hash=password,group_id=first.group_id))
    db.commit()

def seed_reference_content(db):
    from .classroom_models import ServiceDefinition,MiniQuestion
    from .catalog_expansion import SCENES,MINIS
    owner=db.scalar(select(User).where(User.role=='admin'))
    if not owner:return
    services={'Служба 104':['газ','запах газа'],'ЦОДД':['ДТП'],'Мосводоканал':['водопровод'],'МОСГАЗ':['газопровод']}
    services.update({row[0]:row[5] for row in SCENES})
    for name,tags in services.items():
        if not db.get(ServiceDefinition,name):db.add(ServiceDefinition(name=name,config={'tags':tags,'questions':[],'rules':[]}))
    existing={q.data.get('seed_key') for q in db.scalars(select(MiniQuestion))}
    items=[{'prompt':p,'answer':a,'kind':'choice','options':opts,'level':1} for p,a,opts in MINIS]
    for word in ['Декабристов','Конёнкова','Мусоропровод','Пострадавшие','Реагирование','Набережная','Ограждение','Электроснабжение','Теплотрасса','Подтопление','Управляющая организация','Подземный переход','Улица Кржижановского','Большая Черёмушкинская улица','Первый Красногвардейский проезд','Боровское шоссе']:
        items.append({'prompt':'Введите без ошибок: '+word,'answer':word,'kind':'text','options':[],'level':0})
    for index,item in enumerate(items):
        key=f'expansion020-{index}'
        if key not in existing:db.add(MiniQuestion(owner_id=owner.id,data={**item,'seed_key':key}))
    db.commit()
