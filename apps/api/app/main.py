import asyncio, copy, hashlib, json, os, re, secrets, time
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from argon2 import PasswordHasher
from .db import *
from .schemas import *
from .domain import *
from .seed import seed
from .caller import caller_questions, contact_questions
from .dds_flow import create_attempt, deliver_due
from .diagnostics import event as diagnostic_event, request_id as diagnostic_request_id
import traceback

ph=PasswordHasher()
def fail(message, code=400): raise HTTPException(code,message)
def audit(db,u,action,target='',detail=None):
    db.add(Audit(actor_id=u.id if u else None,actor_name=u.name if u else 'Система',action=action,target=str(target),detail=detail or {}))
def getdb():
    with SessionLocal() as db: yield db
def current(request:Request,db:Session=Depends(getdb)):
    token=request.cookies.get('session','')
    session=db.get(LoginSession,hashlib.sha256(token.encode()).hexdigest())
    user=db.get(User,session.user_id) if session and session.expires>time.time() else None
    if not user or not user.active or user.deleted_at: fail('Войдите в систему',401)
    if user.must_change_password and request.url.path not in ('/api/me','/api/change-password','/api/logout'):
        fail('Сначала задайте новый пароль',403)
    if user.role!='admin':
        from .server_identity import is_ready
        if not is_ready(db):fail('Сначала администратор должен задать название учебного сервера',403)
    if request.headers.get('x-workstation'):
        from .classroom import station
        workstation=station(request,db,False)
        if workstation and workstation.blocked:fail('Устройство исключено из учебного контура',403)
    if user.role=='student' and (request.headers.get('x-workstation') or os.getenv('ENFORCE_WORKSTATIONS')=='1'):
        from .classroom import station
        station(request,db)
    request.state.actor_id=user.id
    return user
def staff(u):
    if u.role not in ['admin','teacher']: fail('Недостаточно прав',403)
def admin(u):
    if u.role!='admin': fail('Доступ администратора',403)
def visible(db,u,student):
    if u.role=='admin' or u.id==student: return True
    s=db.get(User,student); g=db.get(Group,s.group_id) if s and s.group_id else None
    return u.role=='teacher' and g and g.teacher_id==u.id
def person(u): return {k:getattr(u,k) for k in ['id','login','name','role','active','audit_access','group_id','must_change_password']}
def attempt_view(a,u):
    from .voice import attach_audio
    with SessionLocal() as voice_db:task=attach_audio(a.snapshot,voice_db)
    if a.status not in ['completed','aborted']:
        task['questions']=caller_questions(task)
    if u.role=='student' and not a.assessment:
        for k in ['expected_card','criteria','routing','service_events','validation_note','scenario_details']: task.pop(k,None)
        task['contacts']=[{k:v for k,v in c.items() if k not in ['response','updates','questions','voice_lines']} for c in task.get('contacts',[])]
        task['questions']=[{'id':q['id'],'question':q['question']} for q in task['questions']]
        if a.status=='ringing': task['intro']=''; task['intro_audio']=None
    return {'id':a.id,'assignment_id':a.assignment_id,'student_id':a.student_id,'task_index':a.task_index,'status':a.status,'revision':a.revision,'task':task,'card':a.card,'state':a.state,'assessment':a.assessment,'started_at':a.started_at,'duration':duration(a),'allowed_statuses':allowed_statuses(a.state.get('services',{}).get(a.snapshot['own_service'],[]))}
def process_events(db):
    for event in db.scalars(select(ScheduledEvent).where(ScheduledEvent.done==False,ScheduledEvent.due<=time.time()).order_by(ScheduledEvent.due,ScheduledEvent.id).with_for_update(skip_locked=True)).all():
        a=db.scalar(select(Attempt).where(Attempt.id==event.attempt_id).with_for_update())
        if a.status=='paused' or a.state.get('mini_started'): continue
        if a.state.get('brigade_pacing')=='sequential' and event.data.get('kind')=='incoming_call':
            if a.state.get('incoming_calls') or a.state.get('brigade_waiting_record'):continue
            if a.snapshot.get('onboarding'):
                required={'arrived':'Начало реагирования','done':'Проведение работ'}.get(event.data.get('stage'))
                statuses=[h['status'] for h in a.state.get('services',{}).get(a.snapshot['own_service'],[])]
                if required and required not in statuses:continue
            next_at=a.state.get('brigade_next_at',0)
            if time.time()<next_at:continue
        event.done=True
        if a.status in ['completed','aborted']: continue
        state=copy.deepcopy(a.state); data=event.data
        if a.snapshot['mode']=='dds' and data.get('service')==a.snapshot['own_service']:
            state.setdefault('messages',[]).append({'text':data.get('text') or f"Получены сведения: {data.get('status','')}. Зарегистрируйте статус самостоятельно.",'at':now()})
            a.state=state;a.revision+=1
            continue
        if 'service' in data: state.setdefault('services',{}).setdefault(data['service'],[]).append({'status':data['status'],'at':now(),'comment':'Учебный ответ службы'})
        elif data.get('kind')=='incoming_call':
            if state.get('brigade_pacing')=='sequential':
                state['brigade_next_at']=time.time()+30
                state['brigade_waiting_record']=event.id
            state.setdefault('incoming_calls',[]).append({'id':event.id,'contact_id':data.get('contact_id'),'who':data.get('who','Старший бригады'),'received_at':now()})
        else: state.setdefault('messages',[]).append({**data,'audio':data.get('audio_id'),'at':now()})
        a.state=state; a.revision+=1
        db.add(AttemptEvent(attempt_id=a.id,kind='simulation',data=data)); audit(db,None,'simulation',a.id,data)
    db.commit()
async def worker():
    while True:
        await asyncio.sleep(1)
        try:
            with SessionLocal() as db:
                deliver_due(db)
                process_events(db)
        except Exception:
            import logging
            logging.exception('Simulation worker')
@asynccontextmanager
async def lifespan(app):
    if os.getenv('ENFORCE_SERVER_NAME')=='1':
        from .server_identity import reset_activation
        reset_activation()
    diagnostic_event('server_starting',version='0.8.20',database=engine.dialect.name)
    from alembic.config import Config
    from alembic import command as migrations
    config=Config(str(ROOT/'alembic.ini'))
    config.set_main_option('script_location',str(ROOT/'apps'/'api'/'migrations'))
    migrations.upgrade(config,'head')
    with SessionLocal() as db:
        if os.getenv('SEED_DEMO','true').lower()=='true':
            seed(db)
            from .seed_workflow import seed_workflow
            seed_workflow(db)
            if os.getenv('DEMO_CLASSROOM')=='1':
                from .seed import ensure_local_demo_students
                ensure_local_demo_students(db)
                from .demo_learning import seed_demo_learning
                seed_demo_learning(db)
                from .classroom_models import Workstation
                for workstation in db.scalars(select(Workstation)):
                    if workstation.number.isdigit() and workstation.id!=os.getenv('DEMO_SERVER_STATION_ID'):
                        workstation.number=f'Старое-{workstation.id[:12]}'
                        workstation.approved=False
                db.commit()
        file=ROOT/'content'/'classifier.json'
        if file.exists() and not db.scalar(select(func.count()).select_from(Classifier)):
            for row in json.loads(file.read_text(encoding='utf-8')): db.add(Classifier(**row))
            db.commit()
    from .learning import seed_catalog
    with SessionLocal() as db:seed_catalog(db)
    from .voice import worker as voice_worker
    voice_job=asyncio.create_task(voice_worker()) if os.getenv("VOICE_AUTO_GENERATE","true")=="true" else None
    from .tutorials import seed as seed_tutorials
    with SessionLocal() as db:seed_tutorials(db)
    from .communication_examples import seed as seed_communications
    with SessionLocal() as db:seed_communications(db)
    from .voice import recover
    recover()
    from .result_report import recover as recover_reports
    recover_reports()
    job=asyncio.create_task(worker())
    from .semantic_review import worker as semantic_worker
    semantic_job=asyncio.create_task(semantic_worker()) if os.getenv("AI_AUTO_REVIEW","true").lower()=="true" else None
    from local_ai.engine import engine as local_engine
    from .ai_workers import broker
    local_engine.delegate=broker.dispatch
    local_engine.on_event=diagnostic_event
    diagnostic_event('server_ready')
    from .backups import worker as backup_worker
    backup_job=asyncio.create_task(backup_worker())
    yield
    backup_job.cancel()
    from .voice import stopping
    stopping.set()
    if voice_job:voice_job.cancel()
    local_engine.delegate=None
    broker.stop()
    job.cancel()
    if semantic_job: semantic_job.cancel()
    from local_ai.engine import engine as local_engine
    local_engine.stop()
    diagnostic_event('server_stopped')
app=FastAPI(title='112 Учебный контур',lifespan=lifespan)
@app.middleware('http')
async def security(request,call_next):
    if request.method in ['POST','PUT','PATCH','DELETE'] and request.headers.get('x-requested-with')!='Training112':
        return Response('Missing request header',403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api') else 'no-cache'
    response.headers['X-Frame-Options']='DENY'
    return response

@app.middleware('http')
async def diagnostic_requests(request,call_next):
    supplied=request.headers.get('x-request-id','')
    rid=supplied if 8<=len(supplied)<=64 and all(c.isalnum() or c=='-' for c in supplied) else secrets.token_hex(12)
    token=diagnostic_request_id.set(rid);started=time.monotonic()
    try:
        response=await call_next(request)
        response.headers['X-Request-ID']=rid
        if request.url.path.startswith('/api/') and request.url.path!='/api/diagnostics/client':
            diagnostic_event('http',method=request.method,path=request.url.path,status=response.status_code,
                             ms=round((time.monotonic()-started)*1000),actor_id=getattr(request.state,'actor_id',None))
        return response
    except Exception as error:
        diagnostic_event('server_exception',method=request.method,path=request.url.path,error_type=type(error).__name__,
                         error=str(error),stack=traceback.format_exc()[-6000:])
        return Response(json.dumps({'detail':'Ошибка сервера. Код диагностики: '+rid}),status_code=500,media_type='application/json',headers={'X-Request-ID':rid})
    finally: diagnostic_request_id.reset(token)
attempted_logins={}
@app.post('/api/login')
def login(data:LoginIn,request:Request,response:Response,db:Session=Depends(getdb)):
    key=request.client.host+data.login; times=[t for t in attempted_logins.get(key,[]) if t>time.time()-300]
    if len(times)>=10: fail('Слишком много попыток. Подождите 5 минут.',429)
    u=db.scalar(select(User).where(User.login==data.login))
    try:
        if not u or not u.active or u.deleted_at: raise ValueError()
        ph.verify(u.password_hash,data.password)
    except Exception:
        attempted_logins[key]=times+[time.time()]; audit(db,None,'login_failed',detail={'login':data.login}); db.commit(); fail('Неверный логин или пароль',401)
    if u.role!='admin':
        from .server_identity import is_ready
        if not is_ready(db):fail('Сначала администратор должен задать название учебного сервера',403)
    if u.role=='student' and os.getenv('ENFORCE_WORKSTATIONS')=='1':
        from .classroom import station
        station(request,db)
    attempted_logins.pop(key,None); token=secrets.token_urlsafe(40)
    db.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),user_id=u.id,expires=time.time()+43200))
    audit(db,u,'login'); db.commit(); response.set_cookie('session',token,httponly=True,samesite='strict',max_age=43200,secure=request.url.scheme=='https')
    return person(u)
@app.post('/api/logout')
def logout(request:Request,response:Response,u=Depends(current),db:Session=Depends(getdb)):
    s=db.get(LoginSession,hashlib.sha256(request.cookies.get('session','').encode()).hexdigest())
    if s: db.delete(s)
    from .classroom import station
    w=station(request,db,False)
    if w and w.user_id==u.id:w.user_id=None
    audit(db,u,'logout'); db.commit(); response.delete_cookie('session'); return {'ok':True}
@app.get('/api/me')
def me(u=Depends(current)): return person(u)
@app.post('/api/change-password')
def change_password(data:dict,u=Depends(current),db:Session=Depends(getdb)):
    if not u.must_change_password: fail('Смена пароля не требуется',403)
    password=data.get('password')
    if not isinstance(password,str) or not 8<=len(password)<=128: fail('Пароль: от 8 до 128 символов')
    u.password_hash=ph.hash(password)
    u.must_change_password=False
    audit(db,u,'password_changed',u.id)
    db.commit()
    return person(u)
@app.get('/api/users')
def users(u=Depends(current),db:Session=Depends(getdb)):
    staff(u)
    query=select(User).where(User.deleted_at.is_(None)).order_by(User.id)
    return [person(s) for s in db.scalars(query) if u.role=='admin' or s.role=='student']
@app.post('/api/users')
def add_user(data:UserIn,u=Depends(current),db:Session=Depends(getdb)):
    admin(u)
    if db.scalar(select(User).where(User.login==data.login)): fail('Логин уже занят')
    if data.group_id and not db.get(Group,data.group_id): fail('Группа не найдена')
    s=User(**data.model_dump(exclude={'password'}),password_hash=ph.hash(data.password)); db.add(s); db.flush(); audit(db,u,'user_created',s.id); db.commit(); return person(s)
@app.patch('/api/users/{id}')
def edit_user(id:int,data:dict,u=Depends(current),db:Session=Depends(getdb)):
    admin(u); s=db.get(User,id)
    if not s or s.deleted_at: fail('Пользователь не найден',404)
    if id==u.id and ('active' in data or 'role' in data): fail('Нельзя менять собственную роль или блокировать себя')
    if any(k not in ['password','name','login','active','audit_access','group_id'] for k in data): fail('Недопустимое поле пользователя')
    if any(k in data and not isinstance(data[k],bool) for k in ['active','audit_access']): fail('Ожидается логическое значение')
    if 'name' in data and (not isinstance(data['name'],str) or not 2<=len(data['name'])<=160): fail('Имя: от 2 до 160 символов')
    if 'login' in data:
        login=data['login']
        if not isinstance(login,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,80}',login): fail('Логин: 3–80 латинских букв, цифр или символов _ . -')
        existing=db.scalar(select(User).where(User.login==login))
        if existing and existing.id!=id: fail('Логин уже занят')
    if data.get('group_id') is not None and not db.get(Group,data['group_id']): fail('Группа не найдена')
    if 'password' in data:
        if not 8<=len(data['password'])<=128: fail('Пароль: от 8 до 128 символов')
        s.password_hash=ph.hash(data['password'])
    for k in ['name','login','active','audit_access','group_id']:
        if k in data: setattr(s,k,data[k])
    if 'password' in data or data.get('active') is False:
        for session in db.scalars(select(LoginSession).where(LoginSession.user_id==id)): db.delete(session)
    audit(db,u,'user_changed',id,{'fields':list(data)}); db.commit(); return person(s)
@app.post('/api/users/{id}/reset-password')
def reset_user_password(id:int,u=Depends(current),db:Session=Depends(getdb)):
    admin(u); s=db.get(User,id)
    if not s or s.deleted_at: fail('Пользователь не найден',404)
    if id==u.id: fail('Собственный пароль меняется в учётной записи')
    temporary=secrets.token_urlsafe(12)
    s.password_hash=ph.hash(temporary)
    s.must_change_password=True
    for session in db.scalars(select(LoginSession).where(LoginSession.user_id==id)): db.delete(session)
    audit(db,u,'password_reset',id); db.commit()
    return {'temporary_password':temporary}
@app.delete('/api/users/{id}')
async def delete_user(id:int,u=Depends(current),db:Session=Depends(getdb)):
    admin(u); s=db.get(User,id)
    if not s or s.deleted_at: fail('Пользователь не найден',404)
    if id==u.id: fail('Нельзя удалить собственную учётную запись')
    from .backups import perform
    backup=await asyncio.to_thread(perform)
    if backup.get('error') or not backup.get('last_folder'): fail('Не удалось создать резервную копию: '+backup.get('error','неизвестная ошибка'),503)
    old_login=s.login
    s.deleted_at=now();s.active=False
    s.login=f'deleted_{id}_{secrets.token_hex(4)}'
    for session in db.scalars(select(LoginSession).where(LoginSession.user_id==id)): db.delete(session)
    audit(db,u,'user_deleted',id,{'login':old_login,'backup':backup['last_folder']})
    db.commit()
    return {'ok':True,'backup':backup['last_folder']}
@app.get('/api/groups')
def groups(u=Depends(current),db:Session=Depends(getdb)):
    staff(u); return [{'id':g.id,'name':g.name,'teacher_id':g.teacher_id} for g in db.scalars(select(Group)) if u.role=='admin' or g.teacher_id==u.id]
@app.post('/api/groups')
def add_group(data:dict,u=Depends(current),db:Session=Depends(getdb)):
    staff(u); teacher=db.get(User,int(data.get('teacher_id',0))) if u.role=='admin' else u
    if not teacher or teacher.role not in ['teacher','admin'] or not str(data.get('name','')).strip(): fail('Укажите название и преподавателя')
    g=Group(name=str(data['name'])[:160],teacher_id=teacher.id); db.add(g); audit(db,u,'group_created',detail={'name':g.name}); db.commit(); return {'id':g.id}
@app.get('/api/tickets')
def tickets(u=Depends(current),db:Session=Depends(getdb)):
    staff(u)
    from .voice import readiness
    return [{'id':v.id,'ticket_id':v.ticket_id,'number':v.number,'published':v.published,'data':v.data,'editable':True,'archived':db.get(Ticket,v.ticket_id).archived,'voice':readiness(v.data,db)} for v in db.scalars(select(TicketVersion).order_by(TicketVersion.id.desc())) if v.data.get('description')!='Снимок занятия']
@app.post('/api/tickets')
def save_ticket(data:TicketData,ticket_id:int|None=None,u=Depends(current),db:Session=Depends(getdb)):
    staff(u)
    t=db.get(Ticket,ticket_id) if ticket_id else Ticket(title=data.title,created_by=u.id)
    if not t: fail('Билет не найден',404)
    db.add(t); db.flush(); number=(db.scalar(select(func.max(TicketVersion.number)).where(TicketVersion.ticket_id==t.id)) or 0)+1
    from .voice import prepare
    v=TicketVersion(ticket_id=t.id,number=number,data=prepare(data.model_dump(),db,u.id)); db.add(v); db.flush(); audit(db,u,'ticket_version_created',v.id); db.commit(); return {'id':v.id}
@app.post('/api/tickets/{id}/publish')
def publish(id:int,u=Depends(current),db:Session=Depends(getdb)):
    staff(u); v=db.get(TicketVersion,id)
    if not v: fail('Билет не найден',404)
    if v.published: return {'ok':True}
    for task in v.data['tasks']:
        if not task['criteria']: fail('У каждого задания нужны критерии оценки')
        if task['mode']=='112' and not any(task['type_options']): fail('Для задания 112 укажите хотя бы один тип происшествия')
        if task['mode']=='dds':
            if any(c['kind']=='validation' for c in task['criteria']): fail('ДДС не проверяет заполнение карточки 112. Замените критерий на реагирование или комментарии.')
            if not task['initial_card'].get('incident_type') or not task['initial_card'].get('description'): fail('Для ДДС заполните входящую карточку: тип и описание происшествия')
        for event in task['service_events']:
            delay=event.get('after',event.get('after_seconds',10))
            if not isinstance(delay,(int,float)) or not 0<=delay<=7200 or not str(event.get('text','')).strip(): fail('Сообщение бригады: нужен текст и задержка 0–7200 секунд')
            if task['mode']=='dds' and event.get('service')==task['own_service']: fail('Статусы своей ДДС меняет ученик; используйте сообщение или входящий звонок')
            for key in ['trigger_contact','contact_id']:
                if event.get(key) and event[key] not in [c['id'] for c in task['contacts']]: fail('Событие ссылается на отсутствующий контакт')
        for c in task['criteria']:
            if c['kind']=='field' and c['field'] not in CARD_FIELDS: fail('Неизвестное поле в критерии')
            if c['kind']=='question' and c['expected'] not in [q['id'] for q in task['questions']]: fail('Критерий ссылается на отсутствующий вопрос')
            if c['kind']=='time':
                try:
                    if not 0<float(c['expected'])<=7200: fail('Норматив должен быть от 1 до 7200 секунд')
                except (ValueError,TypeError): fail('В критерии времени укажите число секунд')
        for contact in task.get('contacts',[]):
            if contact['kind']=='service' and contact.get('service') not in task['services']+[task['own_service']]: fail('Контакт ДДС должен соответствовать службе-получателю')
            ids=[q['id'] for q in contact.get('questions',[])]
            if len(ids)!=len(set(ids)) or set(ids)&{'dispatch','progress','name','address','details','unknown'}: fail('Дополнительные вопросы абонента должны иметь уникальные ID, отличные от стандартных')
        if task['mode']=='dds' and any(e.get('kind')=='incoming_call' and not e.get('contact_id') for e in task['service_events']): fail('Для входящего звонка выберите абонента')
        for criterion in task['criteria']:
            if criterion['kind']=='contact' and criterion['expected'] not in [c['id'] for c in task.get('contacts',[])]: fail('Критерий ссылается на отсутствующий контакт')
        for key in ['questions','criteria','contacts']:
            ids=[q['id'] for q in task.get(key,[])]
            if len(ids)!=len(set(ids)): fail('Идентификаторы должны быть уникальны')
        audio=[task.get('intro_audio')]+[q.get('audio_id') for q in task['questions']]
        if any(x and not db.get(Media,x) for x in audio): fail('Аудиофайл не найден')
    v.published=True; audit(db,u,'ticket_published',id); db.commit(); return {'ok':True}
@app.post('/api/tickets/{id}/archive')
def archive(id:int,u=Depends(current),db:Session=Depends(getdb)):
    staff(u); t=db.get(Ticket,id)
    if not t: fail('Билет не найден',404)
    t.archived=not t.archived; audit(db,u,'ticket_archived',id); db.commit(); return {'ok':True}
@app.get('/api/assignments')
def assignments(u=Depends(current),db:Session=Depends(getdb)):
    from .voice import readiness
    out=[]
    for a in db.scalars(select(Assignment).order_by(Assignment.id.desc())):
        if not visible(db,u,a.student_id): continue
        v=db.get(TicketVersion,a.version_id); student=db.get(User,a.student_id)
        attempts=db.scalars(select(Attempt).where(Attempt.assignment_id==a.id).order_by(Attempt.id.desc())).all()
        out.append({'id':a.id,'lesson_id':a.lesson_id,'title':a.title,'student_id':a.student_id,'student':student.name,'released':a.released,'training':a.training,'start_mode':a.start_mode,'version':v.number,'tasks':[{'title':t['title'],'mode':t['mode'],'voice':readiness({'tasks':[t]},db)} for t in v.data['tasks']],'attempts':[{'id':p.id,'status':p.status,'task_index':p.task_index,'assessment':p.assessment} for p in attempts]})
    return out
@app.post('/api/assignments')
def assign(data:AssignmentIn,u=Depends(current),db:Session=Depends(getdb)):
    staff(u); v=db.get(TicketVersion,data.version_id)
    if not v or not v.published or db.get(Ticket,v.ticket_id).archived: fail('Выберите опубликованный билет')
    from .voice import ensure_ready
    ensure_ready(v.data,db)
    for id in set(data.students):
        s=db.get(User,id)
        if not s or s.role!='student' or not visible(db,u,id): fail('Ученик недоступен',403)
    for id in set(data.students): db.add(Assignment(version_id=v.id,student_id=id,teacher_id=u.id,title=v.data['title'],start_mode=data.start_mode,released=data.start_mode=='self',training=data.training))
    audit(db,u,'assignments_created',v.id,{'students':data.students}); db.commit(); return {'ok':True}
@app.post('/api/assignments/{id}/release')
def release(id:int,u=Depends(current),db:Session=Depends(getdb)):
    staff(u); a=db.get(Assignment,id)
    if not a or not visible(db,u,a.student_id): fail('Назначение недоступно',403)
    if a.lesson_id: fail('Запустите занятие целиком в разделе «Занятия»')
    a.released=True; audit(db,u,'assignment_released',id); db.commit(); return {'ok':True}
@app.post('/api/assignments/{id}/start')
def start(id:int,data:dict,u=Depends(current),db:Session=Depends(getdb)):
    lesson_id=db.scalar(select(Assignment.lesson_id).where(Assignment.id==id))
    if lesson_id: db.scalar(select(Lesson).where(Lesson.id==lesson_id).with_for_update())
    a=db.scalar(select(Assignment).where(Assignment.id==id).with_for_update())
    if not a or a.student_id!=u.id: fail('Это назначение другого ученика',403)
    if a.lesson_id:
        lesson=db.scalar(select(Lesson).where(Lesson.id==a.lesson_id).with_for_update())
        if lesson.status!='active': fail('Занятие ещё не начато или уже завершено')
        if lesson.config.get('delivery_mode') in ('dds_stream','adaptive','sprint','cooperative'):
            p=db.scalar(select(Attempt).where(Attempt.assignment_id==id,Attempt.task_index==int(data.get('task_index',0))))
            if not p: fail('Карточка ещё не поступила. Откройте очередь занятия.')
            return attempt_view(p,u)
    if not a.released: fail('Ожидайте запуска преподавателем')
    active=db.scalar(select(Attempt).where(Attempt.assignment_id==id,Attempt.status.notin_(['completed','aborted'])))
    if active: return attempt_view(active,u)
    tasks=db.get(TicketVersion,a.version_id).data['tasks']; index=int(data.get('task_index',0))
    if not 0<=index<len(tasks): fail('Задание не найдено')
    if a.lesson_id:
        finished=set(db.scalars(select(Attempt.task_index).where(Attempt.assignment_id==id,Attempt.status.in_(['completed','aborted']))))
        expected=next((i for i in range(len(tasks)) if i not in finished),None)
        if index!=expected: fail('Продолжите занятие по порядку карточек')
    p=create_attempt(db,a,tasks[index],index)
    audit(db,u,'attempt_started',p.id); db.commit(); return attempt_view(p,u)
@app.get('/api/attempts/{id}')
def get_attempt(id:int,u=Depends(current),db:Session=Depends(getdb)):
    p=db.get(Attempt,id)
    if not p or not visible(db,u,p.student_id): fail('Попытка недоступна',403)
    return attempt_view(p,u)
@app.get('/api/attempts/{id}/events')
def events(id:int,u=Depends(current),db:Session=Depends(getdb)):
    p=db.get(Attempt,id)
    if not p or not visible(db,u,p.student_id): fail('Попытка недоступна',403)
    return [{'id':e.id,'kind':e.kind,'data':e.data,'at':e.at} for e in db.scalars(select(AttemptEvent).where(AttemptEvent.attempt_id==id).order_by(AttemptEvent.id))]
@app.post('/api/attempts/{id}/command')
def command(id:int,c:Command,u=Depends(current),db:Session=Depends(getdb)):
    return apply_command(id,c,u,db)

def apply_command(id,c,u,db,_trusted_ai=False):
    if c.type=='ai_question' and not _trusted_ai: fail('Используйте обработчик текстового вопроса',403)
    lesson_id=db.scalar(select(Assignment.lesson_id).join(Attempt,Attempt.assignment_id==Assignment.id).where(Attempt.id==id))
    if lesson_id: db.scalar(select(Lesson).where(Lesson.id==lesson_id).with_for_update())
    p=db.scalar(select(Attempt).where(Attempt.id==id).with_for_update())
    if not p or p.student_id!=u.id: fail('Попытка недоступна',403)
    if db.scalar(select(AttemptEvent).where(AttemptEvent.attempt_id==id,AttemptEvent.command_id==c.command_id)): return attempt_view(p,u)
    if p.revision!=c.revision: fail('Состояние обновилось. Повторите действие.',409)
    if p.status in ['completed','aborted']: fail('Попытка завершена')
    state=copy.deepcopy(p.state); task=p.snapshot; payload=c.payload; kind=c.type
    if state.get('mini_started'):fail('Сначала завершите минивопрос')
    if p.status=='paused' and kind not in ['resume','abort']: fail('Продолжите тренировку')
    if kind=='accept_call':
        if state['call']!='ringing': fail('Нет входящего звонка')
        from .caller import caller_gender
        state['voice_gender']=caller_gender(task)
        state['call']='connected'; state['accepted_at']=now(); state['paused_seconds']=0; p.status='active'; state['dialogue'].append({'who':'Заявитель','text':task['intro'],'audio':task.get('intro_audio')})
    elif kind in ['question','ai_question']:
        if state['call']!='connected': fail('Сначала ответьте на звонок')
        questions=caller_questions(task)
        q=next((q for q in questions if q['id']==payload.get('id')),None)
        if not q and kind=='question': fail('Неизвестный вопрос')
        if q and questions != task['questions']:
            p.snapshot={**copy.deepcopy(task),'questions':questions}
            audit(db,None,'caller_catalog_completed',p.id,{'question_ids':[x['id'] for x in questions if x not in task['questions']]})
        from .caller import caller_gender
        state['voice_gender']=caller_gender(task)
        if q: state['asked'].append(q['id'])
        state['dialogue'] += [{'who':'Оператор','text':payload['text'] if kind=='ai_question' else q['question']},
                             {'who':'Заявитель','text':q['answer'] if q else payload.get('voice_reply') or 'Я не понял вопрос. Уточните, пожалуйста.',
                              'audio':q.get('audio_id') if q else None}]
    elif kind=='validate_card':
        fail('ДДС не контролирует заполнение карточки 112. Используйте статусы и комментарии.')
    elif kind=='accept_dds_call':
        if task['mode']!='dds': fail('Входящие сообщения бригады доступны в ДДС')
        incoming=next((x for x in state.get('incoming_calls',[]) if x['id']==payload.get('id')),None)
        if not incoming: fail('Входящий звонок уже принят или недоступен')
        event=db.get(ScheduledEvent,incoming['id'])
        if not event or event.attempt_id!=id: fail('Звонок недоступен')
        state['incoming_calls'].remove(incoming)
        if state.get('brigade_pacing')=='sequential' and state.get('brigade_waiting_record')==event.id:state['brigade_next_at']=time.time()+30
        if not event.data.get('audio_id') and event.data.get('voice_key'):
            from .voice import VoiceJob
            job=db.get(VoiceJob,event.data['voice_key'])
            if job and job.status=='ready':event.data={**event.data,'audio_id':job.audio_id}
        state['messages'].append({'who':incoming['who'],'text':event.data['text'],'at':now(),'direction':'incoming','event_id':event.id,'audio':event.data.get('audio_id')})
        state.setdefault('received_calls',[]).append(event.id)
        if event.data.get('stage'):state.setdefault('received_stages',[]).append(event.data['stage'])
        if incoming.get('contact_id'): state.setdefault('contacts',[]).append(incoming['contact_id'])
    elif kind=='contact':
        if task['mode']!='dds': fail('Исходящая учебная связь доступна в ДДС')
        contact=next((x for x in task.get('contacts',[]) if x['id']==payload.get('id')),None)
        if not contact or not contact.get('phone'): fail('Контакт или телефон недоступен')
        if contact['kind']=='service' and contact.get('service') not in state['services']: fail('Эта служба не получала карточку')
        text=str(payload.get('text','')).strip()
        if not 3<=len(text)<=4000: fail('Введите сообщение для передачи (3–4000 символов)')
        counts=state.setdefault('contact_counts',{}); count=counts.get(contact['id'],0)
        updates=contact.get('updates',[])
        scheduled=[e for e in task.get('service_events',[]) if e.get('trigger_contact')==contact['id']]
        progress=contact['response'] if count else None
        if scheduled:
            for event in db.scalars(select(ScheduledEvent).where(ScheduledEvent.attempt_id==id,ScheduledEvent.done==True).order_by(ScheduledEvent.due,ScheduledEvent.id)):
                if event.data.get('contact_id')==contact['id']: progress=event.data.get('text',progress)
        elif count and updates:
            progress=updates[min(count-1,len(updates)-1)]
        if 'question_id' in payload:
            if not _trusted_ai: fail('Используйте обработчик текстового вопроса',403)
            question=next((q for q in contact_questions(task,contact,progress) if q['id']==payload['question_id']),None)
            answer=question['answer'] if question else 'Уточните, пожалуйста, вопрос по этому происшествию.'
            dispatch=payload['question_id']=='dispatch'
        else:
            answer=contact['response'] if count==0 else progress or contact['response']
            dispatch=count==0
        if dispatch or not scheduled and 'question_id' not in payload: counts[contact['id']]=count+1
        if dispatch and count==0:
            for event in task.get('service_events',[]):
                if event.get('trigger_contact')==contact['id']:
                    db.add(ScheduledEvent(attempt_id=id,due=time.time()+(2 if state.get('brigade_pacing')=='sequential' and event.get('kind')=='incoming_call' and not event.get('respect_delay') else float(event.get('after',event.get('after_seconds',10)))),data=event))
        if 'question_id' not in payload or question:
            state.setdefault('contacts',[]).append(contact['id'])
        from .voice import response_audio
        audio=response_audio(contact,answer,db)
        state['messages'] += [{'who':'Диспетчер → '+contact['name'],'text':text,'at':now()},
                              {'who':contact['name'],'text':answer,'at':now(),'audio':audio,'direction':'outgoing_answer'}]
    elif kind=='draft':
        if task['mode']=='dds': fail('Полученная карточка доступна для чтения')
        if state['call']=='ringing': fail('Сначала примите звонок')
        p.card={**p.card,**{k:v for k,v in payload.items() if k in CARD_FIELDS and (isinstance(v,str) and len(v)<=5000 or k=='traits' and isinstance(v,list) and all(isinstance(x,str) for x in v))}}
    elif kind=='notify':
        if task['mode']!='112' or state['call']=='ringing': fail('Недоступно')
        if not p.card.get('incident_type') or not p.card.get('description') or not p.card.get('street'): fail('Заполните улицу, тип и описание происшествия')
        selected=payload.get('services',[])
        from .classroom_models import ServiceDefinition
        available=list(db.scalars(select(ServiceDefinition.name).where(ServiceDefinition.active==True)))
        if not selected or any(s not in available+SERVICES+task.get('services',[]) for s in selected): fail('Выберите службы')
        for s in selected:
            if s not in state['services']:
                state['services'][s]=[{'status':'Добавлена','at':now(),'comment':''}]
                for sec,status in ([] if p.state.get('flow')=='cooperative' or lesson_id and db.get(Lesson,lesson_id).config.get('delivery_mode')=='cooperative' else [(3,'Получена службой'),(7,'Принята')]): db.add(ScheduledEvent(attempt_id=id,due=time.time()+sec,data={'service':s,'status':status}))
        state['registered']=True; state.setdefault('fill_seconds',duration(p))
    elif kind=='end_call':
        if state['call']!='connected': fail('Нет активного разговора')
        state['call']='ended'
    elif kind in ['status','worklog']:
        if task['mode']!='dds': fail('Этот режим предназначен для ДДС')
        hist=state['services'][task['own_service']]; status=payload.get('status'); comment=str(payload.get('comment','')).strip()
        if kind=='worklog':
            status=hist[-1]['status']
            if not comment:fail('Введите комментарий')
            if status in ['Работы завершены','Отказ от выполнения работ']:fail('Работа службы завершена')
        elif status not in allowed_statuses(hist): fail('Недопустимый переход статуса')
        if status in ['Не принята','Отказ от выполнения работ'] and not comment: fail('Укажите причину')
        if status in ['Принята','Не принята'] and 'ack_seconds' not in state:
            state['ack_seconds']=max(0,round((datetime.fromisoformat(now())-datetime.fromisoformat(p.started_at)).total_seconds()-state.get('paused_seconds',0)))
        if state.get('brigade_pacing')=='sequential' and state.get('brigade_waiting_record') in state.get('received_calls',[]) and (comment or task.get('onboarding')):
            state['brigade_next_at']=time.time()+2
            state.pop('brigade_waiting_record',None)
        hist.append({'status':status,'comment':comment[:2000],'unit':str(payload.get('unit',''))[:100],'at':now()})
    elif kind=='hint':
        if not state['training']: fail('В экзамене подсказки отключены')
        state['hint']='Уточните адрес и угрозы, выберите тип происшествия и службы. В ДДС подтвердите приём, фиксируйте сообщения и обоснуйте отказ.'; state['hints']=state.get('hints',0)+1
    elif kind=='pause':
        if not state['training']: fail('В экзамене пауза отключена')
        if state.get('flow')=='dds_stream': fail('В потоке ДДС таймеры всех карточек продолжают идти; индивидуальная пауза недоступна')
        state['before_pause']=p.status; state['pause_at']=now(); p.status='paused'
    elif kind=='resume':
        if p.status!='paused': fail('Тренировка не на паузе')
        seconds=(datetime.fromisoformat(now())-datetime.fromisoformat(state['pause_at'])).total_seconds()
        if state.get('brigade_next_at'):state['brigade_next_at']+=seconds
        state['paused_seconds']+=seconds; state.pop('pause_at'); p.status=state.pop('before_pause')
        for e in db.scalars(select(ScheduledEvent).where(ScheduledEvent.attempt_id==id,ScheduledEvent.done==False)): e.due+=seconds
    elif kind=='abort': p.status='aborted'; p.submitted_at=now()
    elif kind=='finish':
        if task['mode']=='112' and (not state['registered'] or state['call']!='ended'): fail('Оповестите службы и завершите разговор')
        if task['mode']=='dds' and state['services'][task['own_service']][-1]['status'] not in ['Не принята','Работы завершены','Отказ от выполнения работ']: fail('Завершите обработку карточки или укажите причину отказа')
        p.status='completed'; p.submitted_at=now()
    p.state=state; p.revision+=1
    if kind=='notify':
        from .classroom_flow import relay_card
        relay_card(db,p,selected)
    if kind in ('status','worklog'):
        from .classroom_flow import relay_status
        relay_status(db,p)
    if kind=='finish':
        from .conversation_review import apply_cached
        from .result_report import evidence
        grade=assess(p)
        for criterion in grade['criteria']:apply_cached(criterion,p.state)
        p.assessment={**score(grade),'report_job':{'status':'queued','at':now()}}
        warm=state.get('warm_report',{})
        if warm.get('evidence')==evidence(p):p.assessment={**p.assessment,'ai_review':warm['review'],'report_job':{'status':'done','at':now()}}
    db.add(AttemptEvent(attempt_id=id,command_id=c.command_id,kind=kind,data=payload,actor_id=u.id)); audit(db,u,kind,id,payload); db.commit()
    diagnostic_event('attempt_command',actor_id=u.id,attempt_id=id,command_id=c.command_id,command=kind,revision=p.revision,status=p.status)
    return attempt_view(p,u)
@app.post('/api/attempts/{id}/review')
def review(id:int,data:ReviewIn,u=Depends(current),db:Session=Depends(getdb)):
    staff(u); p=db.scalar(select(Attempt).where(Attempt.id==id).with_for_update())
    if not p or not visible(db,u,p.student_id) or not p.assessment: fail('Результат недоступен',403)
    a=db.get(Assignment,p.assignment_id)
    if u.role=='admin' and a.lesson_id and db.get(Lesson,a.lesson_id).status=='active': fail('Администратор не меняет оценки во время активного занятия',403)
    valid={c['id'] for c in p.assessment['criteria']}
    if not set(data.criteria).issubset(valid): fail('Неизвестный критерий')
    r=copy.deepcopy(p.assessment)
    if data.confirm and r.get('report_job',{}).get('status') not in (None,'done'):fail('Дождитесь анализа и оцените все критерии')
    if not data.confirm and not data.criteria:fail('Выберите критерии или подтвердите оценку')
    for c in r['criteria']:
        if c['id'] in data.criteria:
            c.setdefault('automatic',c['passed']); c['passed']=data.criteria[c['id']]; c['credit']=1 if c['passed'] else 0; c['teacher_reviewed']=True
            from .answer_memory import remember
            if not data.confirm:remember(db,p,c,u,c['passed'])
    if data.confirm:
        if any(c['passed'] is None for c in r['criteria']):fail('Оцените все критерии перед подтверждением')
        from .answer_memory import remember
        for c in r['criteria']:
            c['teacher_reviewed']=True
            remember(db,p,c,u,c['passed'] and c.get('credit',1)==1)
    r['reviews'].append({'by':u.name,'at':now(),**data.model_dump()}); p.assessment=score(r); p.revision+=1
    audit(db,u,'assessment_reviewed',id,data.model_dump()); db.commit(); return attempt_view(p,u)
@app.get('/api/results')
def results(u=Depends(current),db:Session=Depends(getdb)):
    return [{**attempt_view(p,u),'student':db.get(User,p.student_id).name} for p in db.scalars(select(Attempt).where(Attempt.status=='completed').order_by(Attempt.id.desc())) if visible(db,u,p.student_id)]
@app.get('/api/audit')
def audit_list(q:str='',offset:int=0,u=Depends(current),db:Session=Depends(getdb)):
    if not u.audit_access: fail('Нет права просмотра журнала',403)
    query=select(Audit).where(Audit.action.contains(q)).order_by(Audit.id.desc()).offset(max(0,offset)).limit(100)
    return [{'id':e.id,'at':e.at,'actor':e.actor_name,'action':e.action,'target':e.target,'detail':e.detail} for e in db.scalars(query)]
@app.post('/api/ui-event')
def ui_event(data:dict,u=Depends(current),db:Session=Depends(getdb)):
    diagnostic_event('ui_action',actor_id=u.id,path=str(data.get('page','')).split('?')[0][:100],action=str(data.get('action',''))[:200])
    audit(db,u,'ui',str(data.get('page',''))[:100],{'action':str(data.get('action',''))[:200]}); db.commit(); return {'ok':True}
@app.get('/api/classifier')
def classifier(q:str='',u=Depends(current),db:Session=Depends(getdb)):
    return [{'code':r.code,'title':r.title,'traits':r.traits,'source':r.source} for r in db.scalars(select(Classifier).where(Classifier.title.icontains(q)).limit(100))]
@app.get('/api/system')
def system(u=Depends(current),db:Session=Depends(getdb)):
    admin(u); return {'database':'PostgreSQL' if engine.dialect.name=='postgresql' else 'SQLite','classifier_count':db.scalar(select(func.count()).select_from(Classifier)),'users':db.scalar(select(func.count()).select_from(User)),'attempts':db.scalar(select(func.count()).select_from(Attempt)),'version':'0.8.20','offline':True}
@app.post('/api/media')
async def upload(file:UploadFile,u=Depends(current),db:Session=Depends(getdb)):
    admin(u); data=await file.read(20*1024*1024+1)
    if len(data)>20*1024*1024: fail('Максимум 20 МБ')
    mime='audio/wav' if data[:4]==b'RIFF' and data[8:12]==b'WAVE' else 'audio/mpeg' if data[:3]==b'ID3' or len(data)>2 and data[0]==255 and data[1]&224==224 else None
    if not mime: fail('Поддерживаются WAV и MP3')
    id=hashlib.sha256(data).hexdigest()
    if not db.get(Media,id):
        (DATA/'media'/id).write_bytes(data); db.add(Media(id=id,filename=(file.filename or 'audio')[:200],mime=mime,size=len(data),owner_id=u.id))
    audit(db,u,'media_uploaded',id); db.commit(); return {'id':id,'filename':file.filename}
@app.get('/api/media/{id}')
def media(id:str,u=Depends(current),db:Session=Depends(getdb)):
    m=db.get(Media,id)
    if not m: fail('Файл не найден',404)
    if u.role=='student':
        from .voice import attach_audio
        allowed=False
        for p in db.scalars(select(Attempt).where(Attempt.student_id==u.id)):
            if any(c.get('greeting_audio')==id for c in attach_audio(p.snapshot,db).get('contacts',[])):allowed=True
            if any(d.get('audio')==id for d in p.state.get('dialogue',[])+p.state.get('messages',[])): allowed=True
        from .learning import profile,question_view
        pending=profile(db,u.id).data.get('pending_drill')
        if pending:
            q=type('Pending',(),{'id':pending['id'],'data':pending['data'],'active':True})()
            allowed=allowed or question_view(q,db,True).get('audio_id')==id
        if not allowed: fail('Аудиозапись пока недоступна',403)
    return FileResponse(DATA/'media'/id,media_type=m.mime)
from .extensions import router as extensions_router
app.include_router(extensions_router)
from .ai_routes import router as ai_router
app.include_router(ai_router)
from .diagnostic_routes import router as diagnostic_router
app.include_router(diagnostic_router)

from .scenario_wizard import router as wizard_router
app.include_router(wizard_router)
from .classroom import router as classroom_router
app.include_router(classroom_router)
from .ai_workers import router as workers_router
app.include_router(workers_router)
from .learning import router as learning_router
app.include_router(learning_router)
from .management import router as management_router
app.include_router(management_router)

from .teacher import router as teacher_router
app.include_router(teacher_router)

from .voice import router as voice_router
app.include_router(voice_router)

from .tutorials import router as tutorials_router
app.include_router(tutorials_router)

if (ROOT/'dist').exists():
    app.mount('/assets',StaticFiles(directory=ROOT/'dist'/'assets'),name='assets')
    @app.get('/{path:path}')
    def frontend(path:str):
        if path.startswith('api/'): fail('Не найдено',404)
        return FileResponse(ROOT/'dist'/'index.html')
