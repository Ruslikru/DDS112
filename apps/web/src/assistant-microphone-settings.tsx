import React,{useEffect,useId,useRef,useState} from 'react';
import {Check,ChevronDown,Mic,RefreshCw,Settings} from 'lucide-react';
import './assistant-microphone-settings.css';

type Microphone={id:string,label:string};
type Props={value:string,onChange:(id:string)=>void,disabled?:boolean};

export function AssistantMicrophoneSettings({value,onChange,disabled=false}:Props){
 const [open,setOpen]=useState(false),[expanded,setExpanded]=useState(false);
 const [devices,setDevices]=useState<Microphone[]>([]),[loading,setLoading]=useState(false);
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[active,setActive]=useState(0);
 const container=useRef<HTMLDivElement>(null),gear=useRef<HTMLButtonElement>(null),field=useRef<HTMLButtonElement>(null);
 const generation=useRef(0),current=useRef({value,onChange});current.current={value,onChange};
 const popup=useRef({open,expanded});popup.current={open,expanded};
 const id=useId(),listId=id+'-list',labelId=id+'-label';
 const options=[{id:'',label:'Системный микрофон'},...devices];
 const selected=options.findIndex(item=>item.id===value);
 const selectedLabel=options[selected]?.label||'Микрофон недоступен';

 async function refresh(requestPermission=false){
  const run=++generation.current;setLoading(true);setError('');
  try{
   const media=navigator.mediaDevices;
   if(!media?.enumerateDevices||!media?.getUserMedia)throw Error('Откройте программу Windows или страницу по HTTPS, чтобы выбрать микрофон.');
   let all=await media.enumerateDevices();
   if(requestPermission&&!all.some(device=>device.kind==='audioinput'&&device.label)){
    const native=(window as any).pywebview?.api;
    if(typeof native?.allow_microphone==='function')await native.allow_microphone();
    const stream=await media.getUserMedia({audio:true});
    // Only obtain device names. Settings never record or transcribe sound.
    stream.getTracks().forEach(track=>track.stop());
    if(run!==generation.current)return;
    all=await media.enumerateDevices();
   }
   if(run!==generation.current)return;
   const seen=new Set<string>();
   const list=all.filter(device=>device.kind==='audioinput'&&device.deviceId&&!['default','communications'].includes(device.deviceId)&&!seen.has(device.deviceId)&&!!seen.add(device.deviceId))
    .map((device,index)=>({id:device.deviceId,label:device.label||`Микрофон ${index+1}`}));
   setDevices(list);setExpanded(false);
   if(current.current.value&&!list.some(device=>device.id===current.current.value)){
    current.current.onChange('');setNotice('Выбранный микрофон отключён. Используется системный.');
   }
   if(!all.some(device=>device.kind==='audioinput'))setError('Микрофоны не найдены. Подключите устройство и обновите список.');
  }catch(problem:any){
   if(run!==generation.current)return;
   setError(problem?.name==='NotAllowedError'?'Доступ к микрофону запрещён. Разрешите его в настройках браузера или приложения и обновите список.':problem?.name==='NotFoundError'?'Микрофоны не найдены. Подключите устройство и обновите список.':problem?.message||'Не удалось получить список микрофонов.');
  }finally{if(run===generation.current)setLoading(false);}
 }

 useEffect(()=>{
  if(!open)return;
  void refresh(true);field.current?.focus();
  const changed=()=>void refresh();
  const outside=(event:PointerEvent)=>{if(!container.current?.contains(event.target as Node)){setExpanded(false);setOpen(false);}};
  navigator.mediaDevices?.addEventListener?.('devicechange',changed);document.addEventListener('pointerdown',outside);
  return()=>{generation.current++;navigator.mediaDevices?.removeEventListener?.('devicechange',changed);document.removeEventListener('pointerdown',outside);};
 },[open]);
 useEffect(()=>{if(disabled)setExpanded(false);},[disabled]);
 // ArmDialog listens for Escape on its native DOM node. Handle it here before
 // that listener, so closing a dropdown never also closes the assistant.
 useEffect(()=>{
  const node=container.current;
  const escape=(event:KeyboardEvent)=>{
   if(event.key!=='Escape'||!popup.current.open)return;
   event.preventDefault();event.stopPropagation();
   if(popup.current.expanded){setExpanded(false);field.current?.focus();}
   else{setOpen(false);gear.current?.focus();}
  };
  node?.addEventListener('keydown',escape);return()=>node?.removeEventListener('keydown',escape);
 },[]);
 useEffect(()=>{if(open&&!loading&&(document.activeElement===document.body||document.activeElement===gear.current))field.current?.focus();},[open,loading]);
 useEffect(()=>{if(expanded)document.getElementById(listId+'-'+active)?.scrollIntoView({block:'nearest'});},[expanded,active,listId]);

 function choose(index:number){const item=options[index];if(!item||disabled)return;onChange(item.id);setNotice('');setExpanded(false);field.current?.focus();}
 function keyboard(event:React.KeyboardEvent){
  if(event.ctrlKey||event.metaKey||event.altKey)return;
  if(disabled||loading)return;
  if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
   event.preventDefault();const initial=selected<0?0:selected;
   setActive(event.key==='Home'?0:event.key==='End'?options.length-1:!expanded?initial:Math.max(0,Math.min(options.length-1,active+(event.key==='ArrowDown'?1:-1))));setExpanded(true);
  }else if(event.key==='Enter'||event.key===' '){event.preventDefault();if(expanded)choose(active);else{setActive(Math.max(0,selected));setExpanded(true);}}
  else if(event.key==='Tab')setExpanded(false);
 }

 return <div className="assistant-settings" ref={container}>
  <button ref={gear} type="button" className="assistant-settings-toggle" aria-label="Настройки микрофона" title="Настройки микрофона" aria-expanded={open} aria-controls={id+'-panel'} onClick={()=>{setExpanded(false);setOpen(value=>!value);}}><Settings size={19}/></button>
  {open&&<section className="assistant-settings-panel" id={id+'-panel'} aria-label="Настройки голосового ввода">
   <div className="assistant-settings-heading"><div><h3>Голосовой ввод</h3><p>Выберите микрофон для ассистента.</p></div><button type="button" className="assistant-microphone-refresh" title="Обновить список микрофонов" aria-label="Обновить список микрофонов" disabled={loading||disabled} onClick={()=>void refresh(true)}><RefreshCw size={17} className={loading?'is-loading':''}/></button></div>
   <span className="assistant-microphone-label" id={labelId}>Микрофон</span>
   <div className="assistant-microphone-select">
    <button ref={field} type="button" role="combobox" className="assistant-microphone-field" aria-labelledby={labelId} aria-expanded={expanded} aria-haspopup="listbox" aria-controls={listId} aria-activedescendant={expanded?listId+'-'+active:undefined} disabled={disabled||loading} onKeyDown={keyboard} onClick={()=>{setActive(Math.max(0,selected));setExpanded(value=>!value);}}><Mic size={18}/><span title={selectedLabel}>{selectedLabel}</span><ChevronDown size={17} className={expanded?'is-expanded':''}/></button>
    {expanded&&<ul id={listId} role="listbox" aria-labelledby={labelId} className="assistant-microphone-options">{options.map((item,index)=><li key={item.id} id={listId+'-'+index} role="option" aria-selected={item.id===value} className={(index===active?'is-active ':'')+(item.id===value?'is-selected':'')} onPointerMove={()=>setActive(index)} onPointerDown={event=>event.preventDefault()} onClick={()=>choose(index)}><Mic size={17}/><span title={item.label}>{item.label}{!item.id&&<small>Устройство по умолчанию в Windows</small>}</span>{item.id===value&&<Check size={17}/>}</li>)}</ul>}
   </div>
   <p className="assistant-microphone-help" role="status">{loading?'Обновляю список устройств…':disabled?'Завершите запись, чтобы сменить микрофон.':notice||'Выбор сохраняется на этом компьютере.'}</p>
   {error&&<p className="assistant-microphone-error" role="alert">{error}</p>}
  </section>}
 </div>;
}
