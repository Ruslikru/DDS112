import React,{useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {X,ClipboardList} from 'lucide-react';
import {useLoad,Obj} from './shared';
import './assignment-notifications.css';

export function AssignmentNotifications(){
 const {data}=useLoad('/assignments',4000),seen=useRef<Set<string>|null>(null),[incoming,setIncoming]=useState<Obj[]>([]);
 useEffect(()=>{
  if(!data)return;
  const ready=data.filter((a:Obj)=>a.released),key=(a:Obj)=>String(a.id)+':'+a.version;
  if(seen.current===null){seen.current=new Set(ready.map(key));return;}
  const fresh=ready.filter((a:Obj)=>!seen.current!.has(key(a)));
  ready.forEach((a:Obj)=>seen.current!.add(key(a)));
  if(fresh.length)setIncoming(previous=>[...previous,...fresh.filter((a:Obj)=>!previous.some(p=>p.id===a.id))]);
 },[data]);
 if(!incoming.length)return null;
 return <aside className="assignment-notification" role="status" aria-live="polite"><ClipboardList size={22} aria-hidden/><div><strong>{incoming.length===1?'Вам назначен новый билет':'Вам назначены новые билеты'}</strong>{incoming.slice(0,2).map(a=><p key={a.id}>{a.title}</p>)}{incoming.length>2&&<p>И ещё {incoming.length-2}</p>}<Link to="/assignments" onClick={()=>setIncoming([])}>Открыть задания</Link></div><button type="button" aria-label="Скрыть уведомление о новом билете" onClick={()=>setIncoming([])}><X size={17}/></button></aside>;
}
