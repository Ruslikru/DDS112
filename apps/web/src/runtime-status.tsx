import React,{useEffect,useState} from 'react';
import {api,Obj} from './shared';
import './runtime-status.css';

const key='training112:runtime-stats',changed='runtime-stats-changed';
const states:Record<string,string>={ready:'разогрета',warming:'разогревается',cold:'не разогрета',error:'ошибка прогрева'};
function useEnabled(){
 const [enabled,setEnabled]=useState(()=>localStorage.getItem(key)!=='false');
 useEffect(()=>{const update=()=>setEnabled(localStorage.getItem(key)!=='false');window.addEventListener(changed,update);window.addEventListener('storage',update);return()=>{window.removeEventListener(changed,update);window.removeEventListener('storage',update);};},[]);
 return enabled;
}
export function RuntimeStatsSettings(){
 const enabled=useEnabled();
 return <label className="runtime-stats-setting"><input type="checkbox" checked={enabled} onChange={e=>{localStorage.setItem(key,String(e.target.checked));window.dispatchEvent(new Event(changed));}}/>Показывать внизу состояние моделей, потоки и загрузку ЦП</label>;
}
export function RuntimeStatus(){
 const enabled=useEnabled();
 useEffect(()=>{document.documentElement.dataset.runtimeStats=enabled?'on':'off';return()=>{delete document.documentElement.dataset.runtimeStats;};},[enabled]);
 return enabled?<RuntimeStrip/>:null;
}
function RuntimeStrip(){
 const [value,setValue]=useState<Obj>(),[offline,setOffline]=useState(false);
 useEffect(()=>{let live=true,timer:ReturnType<typeof setTimeout>;const poll=async()=>{try{const result=await api('/voice/call-status');if(live){setValue(result);setOffline(false);}}catch{if(live)setOffline(true);}finally{if(live)timer=setTimeout(poll,2000);}};void poll();return()=>{live=false;clearTimeout(timer);};},[]);
 return <aside className="runtime-status-strip" aria-label="Состояние нейросетей" aria-live="off">{[['cards','Qwen 4B'],['stt','GigaAM'],['tts','Piper']].map(([id,label])=>{
  const model=value?.models[id],state=offline?'cold':model?.state||'warming',description=offline?'нет связи с сервером':states[state]||state;
  return <span key={id} data-model={id} data-state={state} aria-label={`${label}: ${description}`} title={`${label}: ${description}; ${model?.model||''}; ${String(model?.mode||'cpu').toUpperCase()}; потоков: ${model?.threads??'—'}`}><i className={'runtime-dot '+state}/>{label} <b>{model?.threads??'—'}</b> п.</span>;
 })}<span className="runtime-cpu" title="Загрузка процессора этого устройства">ЦП {offline||value?.cpu_percent==null?'—':Math.round(value.cpu_percent)+'%'}</span></aside>;
}
