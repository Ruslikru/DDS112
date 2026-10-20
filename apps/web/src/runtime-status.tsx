import {useEffect,useState} from 'react';
import {api,Obj} from './shared';
import './runtime-status.css';

const states:Obj={ready:'прогрета и готова',warming:'прогревается',cold:'ожидает прогрева',error:'ошибка прогрева'};
export function RuntimeStatus(){
 const [value,setValue]=useState<Obj>(),[offline,setOffline]=useState(false);
 useEffect(()=>{let live=true,timer:ReturnType<typeof setTimeout>;const poll=async()=>{try{const v=await api('/voice/call-status');if(live){setValue(v);setOffline(false);}}catch{if(live)setOffline(true);}finally{if(live)timer=setTimeout(poll,2000);}};void poll();return()=>{live=false;clearTimeout(timer);};},[]);
 const keys=[['dialogue','Ответ'],['stt','Речь'],['tts','Голос']];
 const ready=value&&Object.values(value.models as Record<string,Obj>).every(m=>m.state==='ready');
 const error=value&&Object.values(value.models as Record<string,Obj>).some(m=>m.state==='error');
 return <div className="call-runtime-status" aria-label="Готовность моделей и процессор сервера" aria-live="off">
  <span className="call-runtime-summary" title={value?`Карточки: ${states[value.models.cards.state]}; помощник: ${states[value.models.assistant.state]}`:undefined}>{offline?'Нет связи':error?'Ошибка прогрева':ready?'Готовы':'Прогрев…'}</span>
  {keys.map(([key,label])=>{const m=value?.models[key],state=offline?'cold':m?.state||'warming';return <span key={key} title={`${label}: ${states[state]||state}; потоков процессора: ${m?.threads??'—'}`}><i className={'runtime-dot '+state}/>{label} {m?.threads??'—'} п.</span>;})}
  <span title="Загрузка всего процессора сервера, средняя за последние 2 секунды">ЦП {offline||value?.cpu_percent==null?'—':Math.round(value.cpu_percent)+'%'}</span>
 </div>;
}
