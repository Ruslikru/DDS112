import React,{useEffect,useState} from 'react';
import {api,Obj} from './shared';
export function StationLogin(){
 const [state,setState]=useState<Obj>({}),[number,setNumber]=useState(''),[error,setError]=useState('');
 useEffect(()=>{const update=()=>api('/classroom/admission').then(setState).catch(()=>{});update();window.addEventListener('station-ready',update);const t=setInterval(update,3000);return()=>{clearInterval(t);window.removeEventListener('station-ready',update);};},[]);
 return state.registered||localStorage.getItem('training112:demo-role')==='client'?null:<div className="station-register"><label>Номер ПК <input value={number} onChange={e=>setNumber(e.target.value)} placeholder="Например, 12"/></label><button type="button" disabled={!number.trim()} onClick={async()=>{try{const r=await api('/classroom/register','POST',{number});localStorage.setItem('training112:station-token',r.token);localStorage.setItem('training112:station-number',r.number);setState({registered:true,number:r.number});}catch(e:any){setError(e.message);}}}>Подключить рабочее место</button>{error&&<small>{error}</small>}</div>;
}
