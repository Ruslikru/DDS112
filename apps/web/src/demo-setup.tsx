import {DeviceList} from './management';
import React,{useEffect,useState} from 'react';
import {Pencil,X} from 'lucide-react';
import {api,Obj,useLoad,Notice} from './shared';

function stationName(number:string,mode:string){
  return mode==='server' ? (number && number!=='Демо сервер' ? `Сервер · ПК №${number}` : 'Сервер') :
    number && /^\d+$/.test(number) ? `Рабочее место №${number}` : 'Номер не назначен';
}

export function ServerNameSetup(){
  const [mode,setMode]=useState(localStorage.getItem('training112:station-mode')||'');
  const [name,setName]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const {data:connection,load}=useLoad('/classroom/connection');
  useEffect(()=>{if(connection?.named&&connection.ready===false)setName(connection.name||'');},[connection?.name,connection?.named,connection?.ready]);
  useEffect(()=>{
    const update=()=>setMode(localStorage.getItem('training112:station-mode')||'');
    window.addEventListener('station-ready',update);
    return()=>window.removeEventListener('station-ready',update);
  },[]);
  if(mode!=='server'||!connection||connection.ready!==false)return null;
  return <div className="demo-setup-backdrop" data-no-capture><form className="demo-setup-dialog" role="dialog" aria-modal="true" aria-labelledby="server-name-setup-title" onSubmit={async e=>{
    e.preventDefault();setBusy(true);setError('');
    try{await api('/management/server-name','POST',{name:name.trim()});await load();if(localStorage.getItem('training112:demo-role')==='server'){sessionStorage.setItem('training112:demo-admin-exit-tip','true');sessionStorage.setItem('training112:demo-teacher-welcome','true');}window.dispatchEvent(new Event('server-name-set'));}
    catch(e:any){setError(e.message);}finally{setBusy(false);}
  }}>
    <h2 id="server-name-setup-title">{connection.named?'Подтвердите название сервера':'Назовите учебный сервер'}</h2>
    <p>{connection.named?'Проверьте сохранённое название. При необходимости измените его и подтвердите запуск сервера.':'Название задаёт администратор.'} После сохранения преподаватель и ученики смогут войти в систему.</p>
    <label>Название сервера<input autoFocus required maxLength={100} placeholder="Например, Кабинет 204" value={name} onChange={e=>setName(e.target.value)}/></label>
    <div className="demo-setup-actions"><button type="submit" className="primary" disabled={busy||!name.trim()}>Сохранить название</button></div>
    <Notice>{error}</Notice>
  </form></div>;
}

export function DemoStationSetup({user}:{user:Obj}){
  const demoRole=localStorage.getItem('training112:demo-role') || '';
  const [step,setStep]=useState<'number'|'server'|''>(()=>demoRole==='client'&&user.role==='admin' ?
    localStorage.getItem('training112:server-selected')!=='true' ? 'server' :
    localStorage.getItem('training112:station-configured')!=='true' ? 'number' : '' : '');
  const [number,setNumber]=useState(localStorage.getItem('training112:station-configured')==='true' ? localStorage.getItem('training112:station-number')||'' : '');
  const [server,setServer]=useState(localStorage.getItem('training112:server-url')||'http://127.0.0.1:8765');
  const [error,setError]=useState(''),[busy,setBusy]=useState(false);
  const {data:connection}=useLoad('/classroom/connection');
  useEffect(()=>{
    const editNumber=()=>{setNumber(localStorage.getItem('training112:station-number')||'');setError('');setStep('number');};
    const editServer=()=>{setError('');setStep('server');};
    window.addEventListener('demo-edit-number',editNumber);
    window.addEventListener('demo-edit-server',editServer);
    return()=>{window.removeEventListener('demo-edit-number',editNumber);window.removeEventListener('demo-edit-server',editServer);};
  },[]);
  if(!demoRole||user.role!=='admin'||!step)return null;
  const initial=demoRole==='client'&&localStorage.getItem('training112:station-configured')!=='true';
  async function saveNumber(){
    setBusy(true);setError('');
    try{
      const result=await api('/classroom/demo-number','POST',{number:number.trim()});
      const bridge=(window as any).pywebview?.api;
      if(bridge && !await bridge.save_demo_number(result.number))throw new Error('Не удалось сохранить номер на этом ПК.');
      localStorage.setItem('training112:station-number',result.number);
      localStorage.setItem('training112:station-configured','true');
      sessionStorage.setItem('training112:show-number-tip','true');
      if(initial)sessionStorage.setItem('training112:demo-client-exit-tip','true');
      window.dispatchEvent(new Event('station-ready'));
      window.dispatchEvent(new Event('demo-setup-complete'));
      setStep('');
    }catch(e:any){setError(e.message);}finally{setBusy(false);}
  }
  async function saveServer(){
    setBusy(true);setError('');
    try{
      const bridge=(window as any).pywebview?.api;
      if(bridge && !await bridge.save_demo_server(server))throw new Error('Не удалось сохранить выбор сервера.');
      localStorage.setItem('training112:server-url',server);
      localStorage.setItem('training112:server-selected','true');
      sessionStorage.setItem('training112:show-server-tip','true');
      window.dispatchEvent(new Event('demo-setup-complete'));
      setStep(localStorage.getItem('training112:station-configured')==='true'?'':'number');
    }catch(e:any){setError(e.message);}finally{setBusy(false);}
  }
  return <div className="demo-setup-backdrop" data-no-capture><section className="demo-setup-dialog" role="dialog" aria-modal="true" aria-labelledby="demo-setup-title">
    {step==='number'?<><h2 id="demo-setup-title">Назначьте номер этому рабочему месту</h2>
      <p>Номер задаёт администратор. Он должен быть свободен на выбранном сервере.</p>
      <label>Номер рабочего места<input autoFocus inputMode="numeric" pattern="[1-9][0-9]{0,2}" value={number} onChange={e=>setNumber(e.target.value.replace(/\D/g,'').slice(0,3))} placeholder="Например, 1"/></label>
      <div className="demo-setup-actions">{!initial&&<button type="button" onClick={()=>setStep('')}>Отмена</button>}<button type="button" className="primary" disabled={busy||!/^[1-9][0-9]{0,2}$/.test(number)} onClick={saveNumber}>Сохранить номер</button></div>
    </>:<><h2 id="demo-setup-title">Подключите компьютер к серверу</h2>
      <p>Сначала выберите сервер. Затем назначьте номер рабочего места в его контуре.</p>
      <label>Доступные серверы<select value={server} onChange={e=>setServer(e.target.value)}><option value={localStorage.getItem('training112:server-url')||'http://127.0.0.1:8765'}>{connection?.name||'Учебный сервер'} · этот компьютер</option></select></label>
      <div className="demo-setup-actions"><button type="button" className="primary" disabled={busy||!server} onClick={saveServer}>Подключиться</button></div>
    </>}
    <Notice>{error}</Notice>
  </section></div>;
}

export function AdminWorkstations(){
  const {data:admission,load:loadAdmission}=useLoad('/classroom/admission',2500);
  const {data:stations,error}=useLoad('/classroom/stations',2500);
  const {data:connection,load:loadConnection}=useLoad('/classroom/connection',3000);
  const [editingName,setEditingName]=useState(false),[serverName,setServerName]=useState(''),[nameError,setNameError]=useState('');
  const [revision,setRevision]=useState(0),[numberTip,setNumberTip]=useState(sessionStorage.getItem('training112:show-number-tip')==='true'),[serverTip,setServerTip]=useState(sessionStorage.getItem('training112:show-server-tip')==='true');
  useEffect(()=>{const update=()=>{setRevision(v=>v+1);setNumberTip(sessionStorage.getItem('training112:show-number-tip')==='true');setServerTip(sessionStorage.getItem('training112:show-server-tip')==='true');loadAdmission();};window.addEventListener('demo-setup-complete',update);window.addEventListener('station-ready',update);window.addEventListener('server-name-set',loadConnection);return()=>{window.removeEventListener('demo-setup-complete',update);window.removeEventListener('station-ready',update);window.removeEventListener('server-name-set',loadConnection);};},[loadAdmission,loadConnection]);
  const mode=localStorage.getItem('training112:station-mode')||'client';
  const demo=!!localStorage.getItem('training112:demo-role');
  const number=admission?.configured ? admission.number : localStorage.getItem('training112:station-configured')==='true' ? localStorage.getItem('training112:station-number')||'' : '';
  const serverUrl=localStorage.getItem('training112:server-url')||'http://127.0.0.1:8765';
  const current=(stations||[]).filter((s:Obj)=>s.online).sort((a:Obj,b:Obj)=>Number(b.mode==='server')-Number(a.mode==='server'));
  void revision;
  return <div className="admin-workstations"><h1>Рабочие места</h1><Notice>{error}</Notice><div className="admin-station-summary">
    <section className="admin-workstation-card"><div className="admin-workstation-head"><div><small>Текущее рабочее место</small><h2>{stationName(number,mode)}</h2></div><button type="button" aria-label="Изменить номер текущего рабочего места" title="Изменить номер" disabled={!demo} onClick={()=>window.dispatchEvent(new Event('demo-edit-number'))}><Pencil size={18}/></button></div>
      {numberTip&&<div className="admin-setup-tip">Здесь можно изменить номер рабочего места.<button aria-label="Закрыть подсказку" onClick={()=>{sessionStorage.removeItem('training112:show-number-tip');setNumberTip(false);}}><X size={16}/></button></div>}
    </section>
    <section className="admin-workstation-card"><div className="admin-workstation-head"><div><small>Учебный сервер</small><h2>{connection?.name||'Учебный сервер'}</h2><p>{serverUrl}</p></div><button type="button" aria-label={mode==='server'?'Изменить название сервера':'Изменить учебный сервер'} title={mode==='server'?'Изменить название':'Изменить сервер'} disabled={!demo&&mode!=='server'} onClick={()=>{if(mode==='server'){setServerName(connection?.name||'');setEditingName(v=>!v);}else window.dispatchEvent(new Event('demo-edit-server'));}}><Pencil size={18}/></button></div>
      {mode==='server'&&!connection?.named&&<div className="admin-setup-tip">Дайте серверу название, например «Кабинет 204». По нему ученики найдут свой класс.<button title="Задать название" onClick={()=>{setServerName('');setEditingName(true);}}><Pencil size={16}/></button></div>}
      {editingName&&<form className="server-name-form" onSubmit={async e=>{e.preventDefault();try{await api('/management/server-name','POST',{name:serverName});setEditingName(false);setNameError('');loadConnection();}catch(e:any){setNameError(e.message);}}}><label>Название сервера<input autoFocus required maxLength={100} placeholder="Кабинет 204" value={serverName} onChange={e=>setServerName(e.target.value)}/></label><button className="primary">Сохранить</button></form>}<Notice>{nameError}</Notice>
      {serverTip&&<div className="admin-setup-tip">Здесь можно выбрать другой сервер.<button aria-label="Закрыть подсказку" onClick={()=>{sessionStorage.removeItem('training112:show-server-tip');setServerTip(false);}}><X size={16}/></button></div>}
    </section>
    </div><section className="admin-workstation-card"><h2 className="section-title-bar">Подключённые рабочие места в текущем контуре сети</h2><DeviceList/></section>
  </div>;
}
