import React,{useEffect,useState} from 'react';
import {Notice,Obj} from './shared';
import './device-connection.css';

export function DeviceConnectionSetup(){
 const [settings,setSettings]=useState<Obj>(),[open,setOpen]=useState(false),[role,setRole]=useState('server'),[name,setName]=useState(''),[server,setServer]=useState(''),[number,setNumber]=useState(''),[password,setPassword]=useState('');
 const [servers,setServers]=useState<Obj[]>([]),[busy,setBusy]=useState(false),[searching,setSearching]=useState(false),[error,setError]=useState(''),[restarting,setRestarting]=useState(false);
 const bridge=()=> (window as any).pywebview?.api;
 async function load(show=false){
  if(!bridge()?.get_device_settings)return;
  try{const value=await bridge().get_device_settings();if(!value.managed)return;setSettings(value);setRole(value.mode==='client'?'client':value.network_mode==='local'?'local':'server');setName(value.name||'');setServer(value.mode==='client'?value.server||'':'');setNumber(value.mode==='client'?value.number||'':'');setError(value.error||'');setPassword('');setOpen(show||!value.setup_complete||value.force_edit);}catch(e:any){setError(e.message);}
 }
 useEffect(()=>{void load();const edit=()=>void load(true),ready=()=>void load();window.addEventListener('edit-device-connection',edit);window.addEventListener('station-ready',ready);return()=>{window.removeEventListener('edit-device-connection',edit);window.removeEventListener('station-ready',ready);};},[]);
 async function search(){setSearching(true);setError('');try{const found=await bridge().discover_device_servers();setServers(found);if(!server&&found.length)setServer(found[0].url);}catch(e:any){setError(e.message);}finally{setSearching(false);}}
 useEffect(()=>{if(open&&role==='client')void search();},[open,role]);
 if(!settings||!open)return null;
 const initial=!settings.setup_complete;
 return <div className="demo-setup-backdrop" data-no-capture><form className="demo-setup-dialog device-connection-dialog" role="dialog" aria-modal="true" aria-labelledby="device-connection-title" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{await bridge().configure_device({role,name:name.trim(),server:server.trim(),number:number.trim(),password});setRestarting(true);}catch(e:any){setError(e.message);}finally{setBusy(false);}}}>
 <h2 id="device-connection-title">{initial?'Настройте этот компьютер':'Подключение этого компьютера'}</h2><p>Настройка сохраняется на этом ПК. При следующем запуске сразу откроется форма входа.</p>
 <div className="device-role-options">{[['server','Сервер класса','Хранит задания и результаты в локальной сети.'],['client','Рабочее место','Подключается к серверу класса.'],['local','На одном ПК','Преподаватель и ученик работают на этом компьютере.']].map(([value,title,help])=><label key={value} className={role===value?'selected':''}><input type="radio" name="device-role" value={value} checked={role===value} onChange={()=>setRole(value)} disabled={busy||restarting}/><span><b>{title}</b><small>{help}</small></span></label>)}</div>
 {role==='client'?<div className="device-connection-fields"><div className="device-server-search"><label>Найденные серверы<select aria-label="Найденные серверы" value={servers.some(s=>s.url===server)?server:''} onChange={e=>setServer(e.target.value)} disabled={busy||restarting}><option value="">Выберите сервер или введите адрес ниже</option>{servers.map(s=><option key={s.id} value={s.url}>{s.name} · {s.url}</option>)}</select></label><button type="button" disabled={searching||busy||restarting} onClick={search}>{searching?'Поиск…':'Обновить'}</button></div>
 <label>Адрес учебного сервера<input required type="url" value={server} onChange={e=>setServer(e.target.value)} placeholder="http://192.168.1.10:8765" disabled={busy||restarting}/></label>
 <label>Номер рабочего места<input required inputMode="numeric" pattern="[1-9][0-9]{0,2}" value={number} onChange={e=>setNumber(e.target.value.replace(/\D/g,'').slice(0,3))} placeholder="Например, 1" disabled={busy||restarting}/></label>
 <label>Пароль администратора выбранного сервера<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} disabled={busy||restarting}/></label><small>Для подключения к новому серверу и допуска рабочего места. Пароль не сохраняется.</small>
 </div>:<div className="device-connection-fields"><label>{role==='server'?'Название учебного сервера':'Название учебного класса'}<input required maxLength={100} value={name} onChange={e=>setName(e.target.value)} placeholder="Например, Кабинет 204" disabled={busy||restarting}/></label>{role==='server'&&settings.urls?.length>0&&<p>Адрес для подключения рабочих мест: <b>{settings.urls[0]}</b></p>}</div>}
 <Notice>{error}</Notice><div className="demo-setup-actions">{!initial&&<button type="button" disabled={busy||restarting} onClick={()=>setOpen(false)}>Отмена</button>}<button className="primary" disabled={busy||restarting}>{restarting?'Перезапуск приложения…':busy?'Сохраняем…':'Сохранить и открыть вход'}</button></div>
 </form></div>;
}
