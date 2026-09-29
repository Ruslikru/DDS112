import React,{useState} from 'react';
import {ManagementConfirm} from './management';
import {Notice} from './shared';
export function ReportDownload({url,name,children}:{url:string,name:string,children:React.ReactNode}){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 async function save(){setOpen(false);setBusy(true);setMessage('');try{const r=await fetch(url,{headers:{'X-Workstation':localStorage.getItem('training112:station-token')||''}});if(!r.ok)throw new Error('Не удалось подготовить отчёт');const blob=await r.blob();const bridge=(window as any).pywebview?.api;
 if(bridge?.save_report){const bytes=new Uint8Array(await blob.arrayBuffer());let raw='';for(let i=0;i<bytes.length;i+=8192)raw+=String.fromCharCode(...bytes.subarray(i,i+8192));const result=await bridge.save_report(name,btoa(raw));setMessage(result?'Отчёт сохранён.':'Сохранение отменено.');}
 else{const href=URL.createObjectURL(blob),a=document.createElement('a');a.href=href;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(href),30000);setMessage('Отчёт передан в загрузки браузера.');}
 }catch(e:any){setMessage(e.message);}finally{setBusy(false);}}
 return <span className="report-download"><button disabled={busy} onClick={()=>setOpen(true)}>{busy?'Подготовка…':children}</button>{message&&<span role="status">{message}</span>}{open&&<ManagementConfirm title="Сохранить отчёт" description={'Будет сохранён файл '+name+'. Выберите папку в следующем окне.'} confirmLabel="Выбрать папку и сохранить" onConfirm={save} onCancel={()=>setOpen(false)}/>}</span>;
}
