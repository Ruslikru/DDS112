import React, {useState} from 'react';
import {Pencil, Plus} from 'lucide-react';
import {api, Field, Heading, Notice, UserContext, useLoad, type Obj} from './shared';
import './people.css';

const tabs=[{role:'student',title:'Ученики',add:'Добавить ученика'},{role:'teacher',title:'Преподаватели',add:'Добавить преподавателя'},{role:'admin',title:'Администраторы',add:'Добавить администратора'}];

export function People(){
  const actor=React.useContext(UserContext);
  const {data:users,error,load}=useLoad('/users');
  const [role,setRole]=useState('student');
  const [creating,setCreating]=useState(false);
  const [editing,setEditing]=useState<Obj|null>(null);
  const [name,setName]=useState('');
  const [login,setLogin]=useState('');
  const [deleting,setDeleting]=useState<Obj|null>(null);
  const [temporary,setTemporary]=useState<{name:string;password:string}|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [err,setErr]=useState('');
  const activeTab=tabs.find(t=>t.role===role)!;
  const selected=(users||[]).filter((person:Obj)=>person.role===(actor.role==='admin'?role:'student'));
  const run=async (job:()=>Promise<any>,done:string)=>{
    setBusy(true);setErr('');setMessage('');
    try{await job();await load();setMessage(done);return true;}
    catch(error:any){setErr(error.message);return false;}
    finally{setBusy(false);}
  };
  return <div className="page people-page">
    <Heading eyebrow="ПОЛЬЗОВАТЕЛИ" title={actor.role==='admin'?'Пользователи':'Ученики'}>
      {actor.role==='admin'&&<button className="primary" onClick={()=>{setCreating(!creating);setErr('');}}><Plus size={17}/>{activeTab.add}</button>}
    </Heading>
    {actor.role==='admin'&&<nav className="people-tabs" aria-label="Категории пользователей">{tabs.map(tab=><button type="button" key={tab.role} className={role===tab.role?'active':''} aria-current={role===tab.role?'page':undefined} onClick={()=>{setRole(tab.role);setCreating(false);setMessage('');setErr('');}}>{tab.title}</button>)}</nav>}
    <Notice>{error||err}</Notice>{message&&<p className="people-message" role="status">{message}</p>}
    {creating&&actor.role==='admin'&&<form className="panel form-panel people-create" onSubmit={async e=>{e.preventDefault();const form=e.currentTarget;const values=Object.fromEntries(new FormData(form));await run(async()=>{await api('/users','POST',{...values,role});setCreating(false);form.reset();},'Пользователь добавлен.');}}>
      <h2>{activeTab.add}</h2><div className="form-grid"><Field label="Имя и фамилия"><input name="name" minLength={2} maxLength={160} required/></Field><Field label="Логин"><input name="login" minLength={3} maxLength={80} pattern="[a-zA-Z0-9_.-]+" required autoComplete="off"/></Field><Field label="Первый пароль"><input name="password" type="password" minLength={8} maxLength={128} required autoComplete="new-password"/></Field></div><button className="primary" disabled={busy}>Создать</button>
    </form>}
    <section className="panel people-list"><h2 className="section-title-bar">{actor.role==='admin'?activeTab.title:'Ученики'}</h2>
      {selected.length===0?<p className="people-empty">Пока никого нет.</p>:<ul>{selected.map((person:Obj)=><li key={person.id}><div className="people-identity"><div><strong>{person.name}</strong><small>{person.login}</small></div>{actor.role==='admin'&&<button type="button" className="people-pencil" aria-label={'Изменить имя и ник: '+person.name} title="Изменить имя и ник" onClick={()=>{setEditing(person);setName(person.name);setLogin(person.login);}}><Pencil size={16}/></button>}</div>
        {actor.role==='admin'&&<div className="people-actions"><button type="button" disabled={busy||person.id===actor.id} onClick={async()=>{setBusy(true);setErr('');try{const result=await api('/users/'+person.id+'/reset-password','POST');setTemporary({name:person.name,password:result.temporary_password});}catch(error:any){setErr(error.message);}finally{setBusy(false);}}}>Сбросить пароль</button><button type="button" disabled={busy||person.id===actor.id} onClick={()=>run(()=>api('/users/'+person.id,'PATCH',{active:!person.active}),person.active?'Учётная запись заблокирована.':'Учётная запись разблокирована.')}>{person.active?'Заблокировать':'Разблокировать'}</button><button type="button" className="people-delete" disabled={busy||person.id===actor.id} onClick={()=>setDeleting(person)}>Удалить</button></div>}
      </li>)}</ul>}
    </section>
    {editing&&<div className="people-overlay" role="presentation"><form className="people-dialog" role="dialog" aria-modal="true" aria-label="Изменить имя и ник" onSubmit={async e=>{e.preventDefault();const self=editing.id===actor.id;if(await run(()=>api('/users/'+editing.id,'PATCH',{name:name.trim(),login:login.trim()}),'Данные пользователя изменены.')){setEditing(null);if(self)window.location.reload();}}}><h2>Имя и ник</h2><Notice>{err}</Notice><Field label="Имя и фамилия"><input value={name} onChange={e=>setName(e.target.value)} minLength={2} maxLength={160} required autoFocus/></Field><Field label="Ник (логин)"><input value={login} onChange={e=>setLogin(e.target.value)} minLength={3} maxLength={80} pattern="[a-zA-Z0-9_.-]+" required autoComplete="off"/></Field><div className="people-dialog-actions"><button type="button" onClick={()=>setEditing(null)}>Отмена</button><button className="primary" disabled={busy}>Сохранить</button></div></form></div>}
    {deleting&&<div className="people-overlay" role="presentation"><div className="people-dialog" role="dialog" aria-modal="true" aria-label="Удалить учётную запись"><h2>Удалить учётную запись?</h2><Notice>{err}</Notice><p>{deleting.name} больше не сможет войти. Перед удалением сохранится резервная копия.</p><div className="people-dialog-actions"><button type="button" onClick={()=>setDeleting(null)}>Отмена</button><button type="button" className="people-delete-button" disabled={busy} onClick={async()=>{const target=deleting;if(await run(()=>api('/users/'+target.id,'DELETE'),'Учётная запись удалена. Резервная копия создана.'))setDeleting(null);}}>Удалить</button></div></div></div>}
    {temporary&&<div className="people-overlay" role="presentation"><div className="people-dialog" role="dialog" aria-modal="true" aria-label="Временный пароль"><h2>Пароль сброшен</h2><p>Передайте {temporary.name} временный пароль. При входе пользователь задаст свой.</p><output className="people-temporary">{temporary.password}</output><div className="people-dialog-actions"><button type="button" onClick={()=>navigator.clipboard?.writeText(temporary.password)}>Скопировать</button><button type="button" className="primary" onClick={()=>setTemporary(null)}>Готово</button></div></div></div>}
  </div>;
}
