import React,{useEffect,useState} from 'react';
import {api,Obj,uuid} from './shared';
type Entry={id:string,user:number,attempt:string,type:string,payload:Obj,draft?:Obj,draftId:string};
let processing=false,offline=false,notice='',rejected=false;
const key=(user:number)=>'training112:outbox:'+user;
const read=(user:number):Entry[]=>{try{return JSON.parse(localStorage.getItem(key(user))||'[]');}catch{return [];}};
const emit=()=>window.dispatchEvent(new Event('training-network'));
const save=(user:number,items:Entry[])=>{localStorage.setItem(key(user),JSON.stringify(items));emit();};
export function markNetworkFailure(){offline=true;notice='Проблемы с локальной сетью. Изменения сохранены на этом ПК; билеты на проверку будут отправлены после восстановления связи.';emit();}
export async function submitAttempt(user:number,attempt:string,type:string,payload:Obj,draft?:Obj){
 const items=read(user);let entry=items.find(x=>x.attempt===attempt&&x.type===type&&JSON.stringify(x.payload)===JSON.stringify(payload)&&JSON.stringify(x.draft)===JSON.stringify(draft));
 if(!entry){entry={id:uuid(),draftId:uuid(),user,attempt,type,payload,draft};save(user,[...items,entry]);}
 await flush(user);return read(user).some(x=>x.id===entry!.id)?null:api('/attempts/'+attempt);
}
async function flush(user:number){
 if(processing)return;processing=true;
 try{
  const me=await api('/me');if(me.id!==user)return;
  const restored=offline;offline=false;rejected=false;
  if(restored){notice=read(user).length?'Подключение восстановлено. Отправка очереди билетов на проверку…':'Подключение восстановлено.';emit();}
  for(const entry of read(user)){
   for(const stage of [...(entry.draft?[{type:'draft',payload:entry.draft,id:entry.draftId}]:[]),{type:entry.type,payload:entry.payload,id:entry.id}]){
    let done=false;
    for(let retry=0;retry<3&&!done;retry++){
     const p=await api('/attempts/'+entry.attempt);
     try{await api('/attempts/'+entry.attempt+'/command','POST',{command_id:stage.id,revision:p.revision,type:stage.type,payload:stage.payload});done=true;}
     catch(e:any){if(e.status!==409||retry===2)throw e;}
    }
   }
   save(user,read(user).filter(x=>x.id!==entry.id));
   if(restored)notice='Подключение восстановлено. Сохранённые изменения отправлены, билеты переданы на проверку.';emit();
  }
 }catch(e:any){if(e.network)markNetworkFailure();else if(e.status!==401){rejected=true;notice='Очередь сохранена. Не удалось передать действие: '+e.message;emit();}}
 finally{processing=false;}
}
export function NetworkStatus({user}:{user:number}){
 const [,setTick]=useState(0);
 useEffect(()=>{const update=()=>setTick(x=>x+1),failed=()=>markNetworkFailure(),retry=()=>void flush(user);window.addEventListener('training-network',update);window.addEventListener('offline',failed);window.addEventListener('online',retry);window.addEventListener('training-network-failed',failed);const timer=setInterval(retry,3000);retry();return()=>{clearInterval(timer);window.removeEventListener('training-network',update);window.removeEventListener('offline',failed);window.removeEventListener('online',retry);window.removeEventListener('training-network-failed',failed);};},[user]);
 const items=read(user);if(!notice&&!items.length)return null;
 return <aside className={'network-status '+(offline?'offline':'')} role="status" aria-live="polite"><span>{notice||'Отправляем сохранённые изменения…'}{items.length>0&&` В очереди: ${items.length}.`}</span>{!offline&&items.length>0&&<button onClick={()=>void flush(user)}>Повторить отправку</button>}{rejected&&items.length>0&&<button onClick={()=>{if(window.confirm('Удалить первое неотправленное действие из очереди? Остальные действия и локальный черновик останутся на этом ПК.')){save(user,read(user).slice(1));rejected=false;notice='';void flush(user);}}}>Отменить неотправленное действие</button>}{!offline&&!items.length&&<button aria-label="Скрыть сообщение о сети" onClick={()=>{notice='';emit();}}>×</button>}</aside>;
}
