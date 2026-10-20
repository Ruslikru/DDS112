import {PhoneChannelButton} from './phone-channel-button';
import React,{useEffect,useMemo,useRef,useState} from 'react';
import {BookOpen,Mail,MicOff,Phone,ChevronUp,ChevronDown,ChevronLeft,ChevronRight} from 'lucide-react';
import {api,Obj,uuid} from './shared';
import {CallAudioEngine} from './call-audio';
import {BrigadeAudio,DDSVoiceCall,PhoneCallControl} from './voice';
import './avaya-phone.css';

type Slot={contact:string,held:boolean,ready?:string,incoming?:Obj};
type Entry={id:string,name:string,phone:string,kind:'received'|'outgoing'|'missed',at:string};
const empty=():Slot=>({contact:'',held:false});
const phases:Record<string,string>={idle:'Готов к работе',dialing:'Вызов…',greeting:'Слушайте приветствие',ready:'Можно говорить',starting:'Включаем микрофон…',recording:'Говорите → отпустите',recognizing:'Распознаём речь…',sending:'Слушайте ответ…'};

/** Three independent conversations share the workstation lease, but never their audio or recorder. */
export function AvayaPhone({p,active,busy,textOnly,onSelect,onUpdate,cmd,onOpen,onTranscript,onCallEnd,onCallStart}:{p:Obj,active:boolean,busy:boolean,textOnly:boolean,onSelect:(id:string)=>void,onUpdate:(value:Obj)=>void,cmd:(type:string,payload?:Obj)=>Promise<any>,onOpen:()=>void,onTranscript:(text:string)=>void,onCallEnd:()=>void,onCallStart:()=>void}){
 const engines=useMemo(()=>[new CallAudioEngine(),new CallAudioEngine(),new CallAudioEngine()],[p.id]);
 const [slots,setSlots]=useState<Slot[]>([empty(),empty(),empty()]),[selected,setSelected]=useState(0),[screen,setScreen]=useState<'phone'|'contacts'|'history'>('phone');
 const [device,setDevice]=useState<'handset'|'speaker'|'headset'|null>(null),[muted,setMuted]=useState(false),[digits,setDigits]=useState(''),[error,setError]=useState('');
 const [callVolume,setCallVolume]=useState(7),[ringVolume,setRingVolume]=useState(5),[volumeLabel,setVolumeLabel]=useState(''),[cursor,setCursor]=useState(0),[logKind,setLogKind]=useState<Entry['kind']>('outgoing');
 const [logs,setLogs]=useState<Entry[]>(()=>{try{const saved=JSON.parse(sessionStorage.getItem('avaya-log:'+p.id)||'[]');return Array.isArray(saved)?saved.slice(0,50):[];}catch{return [];}}),[clock,setClock]=useState(new Date()),[incomingPlaying,setIncomingPlaying]=useState<number|null>(null);
 useEffect(()=>{sessionStorage.setItem('avaya-log:'+p.id,JSON.stringify(logs));},[logs,p.id]);
 const lease=useRef(uuid()),started=useRef(new Set<number>()),accepting=useRef(false),volumeTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined),seenRings=useRef(new Map<string,Obj>());
 const contacts:Obj[]=p.task.contacts||[],queue:Obj[]=p.state.incoming_calls||[];
 const incoming=active?queue[0]:undefined;
 const calls=useRef<PhoneCallControl[]>([]);
 const ringSlot=incoming&&incomingPlaying===null&&!accepting.current?slots.findIndex((s,i)=>!started.current.has(i)&&!s.incoming):-1;
 const slot=slots[selected];
 function updateSlot(i:number,value:Partial<Slot>){setSlots(previous=>previous.map((s,n)=>n===i?{...s,...value}:s));}
 function log(c:Obj,kind:Entry['kind']){setLogs(previous=>[{id:uuid(),name:c.name||c.who||'Абонент',phone:String(c.phone||''),kind,at:new Date().toLocaleTimeString('ru',{hour:'2-digit',minute:'2-digit'})},...previous].slice(0,50));}
 async function startLine(i:number){
  if(!started.current.size)await api('/call-audio/attempts/'+p.id+'/line','POST',{session:lease.current,active:true});
  started.current.add(i);onCallStart();engines[i].setVolume(callVolume/10);
 }
 function endLine(i:number){
  const existed=started.current.delete(i);updateSlot(i,{contact:'',held:false,ready:undefined,incoming:undefined});engines[i].setHeld(false);
  if(existed&&!started.current.size){onCallEnd();void api('/call-audio/attempts/'+p.id+'/line','POST',{session:lease.current,active:false}).catch(e=>setError(e.message));}
 }
 useEffect(()=>{const release=()=>{if(!started.current.size)return;started.current.clear();engines.forEach(e=>e.stop());void fetch('/api/call-audio/attempts/'+p.id+'/line',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json','X-Requested-With':'Training112','X-Workstation':localStorage.getItem('training112:station-token')||''},body:JSON.stringify({session:lease.current,active:false})}).catch(()=>{});};window.addEventListener('pagehide',release);return()=>window.removeEventListener('pagehide',release);},[p.id]);
 useEffect(()=>{const timer=setInterval(()=>{setClock(new Date());if(started.current.size)void api('/call-audio/attempts/'+p.id+'/line','POST',{session:lease.current,active:true}).catch(e=>setError(e.message));},20000);return()=>{clearInterval(timer);clearTimeout(volumeTimer.current);engines.forEach(e=>e.dispose());if(started.current.size)void api('/call-audio/attempts/'+p.id+'/line','POST',{session:lease.current,active:false}).catch(()=>{});};},[p.id]);
 useEffect(()=>{engines.forEach((e,i)=>e.setVolume((started.current.has(i)?callVolume:ringVolume)/10));},[callVolume,ringVolume,slots]);
 useEffect(()=>{if(!active){calls.current.forEach(c=>{if(c?.phase!=='idle')c.hangup();});setDevice(null);}},[active]);
 useEffect(()=>{
  if(!incoming||ringSlot<0)return;
  const id=String(incoming.id);seenRings.current.set(id,incoming);let live=true;
  engines[ringSlot].prepare(incoming.call_audio).then(()=>{if(live)return engines[ringSlot].signal('ring',true);}).catch(e=>{if(live)setError(e.message);});
  return()=>{live=false;engines[ringSlot].stop();};
 },[incoming?.id,ringSlot]);
 // A disappeared, unanswered ring belongs in the missed list, not in the conversation transcript.
 useEffect(()=>{const id=String(incoming?.id);for(const [previous,caller] of seenRings.current)if(previous!==id){log(caller,'missed');seenRings.current.delete(previous);}},[incoming?.id]);
 function hold(i:number,value:boolean){engines[i].setHeld(value);updateSlot(i,{held:value});}
 function selectLine(i:number){
  if(!active)return;onOpen();setError('');setScreen('phone');setDigits('');
  if(i===ringSlot&&incoming){if(selected!==i&&started.current.has(selected))hold(selected,true);setSelected(i);return;}
  if(selected!==i&&started.current.has(selected))hold(selected,true);
  setSelected(i);if(started.current.has(i))hold(i,false);setDevice(d=>d||'speaker');onSelect(slots[i].contact);
 }
 async function accept(i=ringSlot){
  if(!incoming||i<0||accepting.current||busy)return;accepting.current=true;setError('');
  if(textOnly){try{const result=await cmd('accept_dds_call',{id:incoming.id});if(result){onSelect(incoming.contact_id||'');log(incoming,'received');seenRings.current.delete(String(incoming.id));}}finally{accepting.current=false;}return;}
  try{
   setIncomingPlaying(i);
   if(started.current.has(selected))hold(selected,true);
   seenRings.current.delete(String(incoming.id));setSelected(i);setDevice(d=>d||'speaker');setScreen('phone');setDigits('');onOpen();
   engines[i].stop();await Promise.all([engines[i].unlock(),startLine(i)]);await engines[i].connect(incoming.call_audio);
   setIncomingPlaying(i);
   const result=await cmd('accept_dds_call',{id:incoming.id});if(!result)throw Error('Не удалось принять звонок');
   const message=result.state.messages.filter((m:Obj)=>m.direction==='incoming').at(-1);
   const contact=contacts.find(c=>c.id===(incoming.contact_id||message?.contact_id));
   updateSlot(i,{contact:contact?.id||'',held:false,incoming:message,ready:message?.audio?undefined:String(message?.event_id||uuid())});
   onSelect(contact?.id||'');log({...incoming,...contact},'received');if(!message?.audio)setIncomingPlaying(null);
  }catch(e:any){setError(e.message);setIncomingPlaying(null);endLine(i);engines[i].hangup();}
  finally{accepting.current=false;}
 }
 async function dial(c?:Obj){
  if(!active||busy)return;
  c??=contacts.find(c=>String(c.phone).replace(/\D/g,'')===digits.replace(/\D/g,''));
  if(!c){setError('Номер отсутствует в телефонной книге этого билета.');return;}
  if(started.current.has(selected)){setError('Выберите свободную линию для нового вызова.');return;}
  setError('');setScreen('phone');setDigits('');setDevice(d=>d||'speaker');updateSlot(selected,{contact:c.id,held:false});onSelect(c.id);onOpen();log(c,'outgoing');
  await calls.current[selected].call(c);
 }
 async function send(text:string,id:string){onTranscript(text);const latest=await api('/attempts/'+p.id);const result=await api('/ai/attempts/'+p.id+'/contact','POST',{text,contact_id:id,revision:latest.revision,command_id:uuid(),session:lease.current});onUpdate(result);return result;}
 function hangup(){setError('');setDigits('');setScreen('phone');calls.current[selected]?.hangup();if(incomingPlaying===selected){setIncomingPlaying(null);endLine(selected);}setDevice(null);setMuted(false);}
 function channel(next:NonNullable<typeof device>){
  if(!active)return;onOpen();if(incoming&&ringSlot>=0){setDevice(next);void accept();return;}
  setDevice(next);if(slot.held)hold(selected,false);setScreen('phone');if(digits&&!started.current.has(selected))void dial();
 }
 function pressDigit(d:string){if(!active)return;if(started.current.has(selected)){setError('Набор номера доступен на свободной линии.');return;}setDevice(v=>v||'speaker');setScreen('phone');void engines[selected].digit(d).catch(e=>setError(e.message));setDigits(v=>(v+d).slice(0,24));setError('');}
 const entries=screen==='contacts'?contacts:logs.filter(e=>e.kind===logKind);
 const choose=()=>{if(screen==='phone'){if(digits)void dial();else if(started.current.has(selected))hold(selected,!slot.held);}else{const row=entries[cursor];if(row)void dial(contacts.find(c=>c.id===row.id)||contacts.find(c=>String(c.phone)===String(row.phone)));}};
 function nav(direction:string){if(direction==='up'||direction==='down')setCursor(v=>Math.max(0,Math.min(entries.length-1,v+(direction==='up'?-1:1))));else if(screen==='history'){const kinds:Entry['kind'][]=['missed','outgoing','received'];setLogKind(kinds[(kinds.indexOf(logKind)+(direction==='left'?2:1))%3]);setCursor(0);}else if(screen==='phone'&&direction==='left')setDigits(v=>v.slice(0,-1));}
 function volume(delta:number){const inCall=started.current.has(selected);const value=Math.max(0,Math.min(10,(inCall?callVolume:ringVolume)+delta));if(inCall)setCallVolume(value);else setRingVolume(value);setVolumeLabel((inCall?'Разговор':'Звонок')+': '+value+'/10');clearTimeout(volumeTimer.current);volumeTimer.current=setTimeout(()=>setVolumeLabel(''),1600);}
 function renderDevice(controls:PhoneCallControl[]){
  calls.current=controls;const control=controls[selected],connected=control.phase!=='idle'||incomingPlaying===selected;
  const status=slot.held?'Вызов на удержании':muted&&connected?'Микрофон отключён':incomingPlaying===selected?'Слушайте абонента':phases[control.phase];
  return <div className="avaya-simulator" data-phase={incomingPlaying===selected?'greeting':control.phase} data-call-active={connected} data-screen={screen} data-selected-contact={entries[cursor]?.id||''} onKeyDown={e=>{if((e.target as HTMLElement).closest('textarea,input'))return;if(/^[0-9*#]$/.test(e.key)){e.preventDefault();pressDigit(e.key);}if(e.key==='Enter'&&e.target===e.currentTarget){e.preventDefault();choose();}if(e.key==='Backspace'){e.preventDefault();setDigits(v=>v.slice(0,-1));}}}>
   <div className="avaya-body" aria-label="Телефон Avaya">

    <div className="avaya-console"><div className="avaya-brand">AVAYA <small>{p.task.own_service||'ДДС'}</small></div>
     <div className="avaya-display-row"><div className="avaya-line-keys">{[0,1,2,3].map(i=><button key={i} aria-label={i<3?'Линия '+(i+1):'Резервная линия'} title={i<3?'Линия '+(i+1):'Резервная линия'} disabled={!active||i===3} onClick={()=>selectLine(i)}><i className={i===ringSlot?'ringing':slots[i]?.held?'held':i<3&&(controls[i].phase!=='idle'||incomingPlaying===i)?'lit':''}/></button>)}</div>
      <div className="avaya-lcd" role="status" aria-live="polite"><div className="avaya-lcd-top"><span>{muted?'⊘':device==='headset'?'♬':device==='speaker'?'◖))':'☎'} {selected+1}</span><time>{clock.toLocaleTimeString('ru',{hour:'2-digit',minute:'2-digit'})} {clock.toLocaleDateString('ru',{day:'2-digit',month:'2-digit'})}</time></div>
       <div className="avaya-lcd-title">{screen==='phone'?'Телефон':screen==='contacts'?'Телефонная книга':({missed:'Пропущенные',outgoing:'Совершённые',received:'Полученные'}[logKind])}</div>
       <div className="avaya-lcd-content">{volumeLabel?<div className="avaya-volume-status">{volumeLabel}<meter min="0" max="10" value={started.current.has(selected)?callVolume:ringVolume}/></div>:screen==='phone'?<>{digits?<div className="avaya-number">{digits}</div>:[0,1,2].map(i=><div key={i} className={'avaya-lcd-line'+(selected===i?' selected':'')}><b>{i+1}</b><span>{i===ringSlot?incoming?.who:contacts.find(c=>c.id===slots[i].contact)?.name||'Свободная линия'}</span><small>{i===ringSlot?'Вызов':slots[i].held?'Удерж.':controls[i].phase!=='idle'||incomingPlaying===i?'☎':''}</small></div>)}<div className="avaya-lcd-status">{incoming&&ringSlot===selected?'Входящий вызов':digits?'Нажмите ОК для вызова':status}</div></>:entries.length?entries.slice(Math.max(0,cursor-2),Math.max(0,cursor-2)+3).map((c,index)=>{const n=Math.max(0,cursor-2)+index;return <div key={c.id} className={'avaya-lcd-entry'+(cursor===n?' selected':'')}><span>{c.name}</span><small>{c.phone}{screen==='history'?' · '+c.at:''}</small></div>;}):<div className="avaya-empty">Нет записей</div>}</div>
       <div className="avaya-soft-labels"><span>{screen!=='phone'||digits?'Вызов':slot.held?'Возвр.':'Удерж.'}</span><span>{screen==='phone'?(digits?'Стереть':'Конф.'):'↑'}</span><span>{screen==='phone'?'Трансф':'↓'}</span><span>{screen==='phone'?'Сброс':'Назад'}</span></div>
      </div><div className="avaya-line-keys">{[0,1,2,3].map(i=><button key={i} aria-label={i<3?'Правая линия '+(i+1):'Правая резервная линия'} title={i<3?'Линия '+(i+1):'Резервная линия'} disabled={!active||i===3} onClick={()=>selectLine(i)}><i className={i===ringSlot?'ringing':slots[i]?.held?'held':i<3&&(controls[i].phase!=='idle'||incomingPlaying===i)?'lit':''}/></button>)}</div></div>
     <div className="avaya-softkeys">{[0,1,2,3].map(i=><button key={i} data-guide={i===3?'end-call':undefined} aria-label={['Вызов / удержание','Конференция / стереть / вверх','Перевод вызова / вниз','Сброс / назад'][i]} disabled={!active||screen==='phone'&&(i===2||i===1&&!digits)} title={screen==='phone'&&(i===2||i===1&&!digits)?'В этом билете не используется':undefined} onClick={()=>{if(i===0)choose();if(i===1)screen==='phone'?setDigits(v=>v.slice(0,-1)):nav('up');if(i===2&&screen!=='phone')nav('down');if(i===3)screen==='phone'?hangup():setScreen('phone');}}/>)}</div>
     <div className="avaya-navigation"><button className="avaya-utility" aria-label="Голосовая почта" title="Голосовая почта не используется в учебном билете" disabled><Mail size={15}/></button><div className="avaya-nav-ring">{(['up','left','right','down'] as const).map((d,i)=><button key={d} className={'avaya-nav-'+d} aria-label={['Вверх','Влево','Вправо','Вниз'][i]} onClick={()=>nav(d)}>{[<ChevronUp/>,<ChevronLeft/>,<ChevronRight/>,<ChevronDown/>][i]}</button>)}<button className="avaya-ok" data-guide="phone-dial" aria-label="ОК / вызов" disabled={!active} onClick={choose}>OK</button></div><button className="avaya-utility" aria-label="Экран телефона" title="Экран телефона" onClick={()=>setScreen('phone')}><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M7 3h10M5 8h14l2 12H3z"/><path d="M8 8v5h8V8"/></svg></button></div>
     <div className="avaya-function-row"><button data-guide="phone-directory" aria-label="Телефонная книга" title="Телефонная книга" onClick={()=>{setScreen('contacts');setCursor(0);}}><BookOpen size={16}/></button><span className="avaya-a">A</span><button aria-label="Журнал вызовов" title="Журнал вызовов · влево / вправо — списки" onClick={()=>{setScreen('history');setCursor(0);}}><Phone size={13}/><span className="avaya-history-lines">≡</span><i/></button></div>
     <div className="avaya-dial-area"><div className="avaya-side-keys">{(['headset','speaker'] as const).map(kind=><PhoneChannelButton key={kind} kind={kind} selected={device===kind} disabled={!active} canTalk={!incoming&&!textOnly&&!busy&&!muted&&!slot.held&&incomingPlaying!==selected&&['ready','starting','recording'].includes(control.phase)} recording={device===kind&&control.phase==='recording'} onActivate={()=>channel(kind)} onTalk={async()=>{setDevice(kind);return control.microphone();}}/>)}</div>
      <div className="avaya-keypad">{'123456789*0#'.split('').map((n,i)=><button key={n} aria-label={'Набрать '+n} disabled={!active} onClick={()=>pressDigit(n)}><small>{['','ABC','DEF','GHI','JKL','MNO','PQRS','TUV','WXYZ','','+',''][i]}</small><b>{n}</b></button>)}</div>
      <div className="avaya-side-keys"><div className="avaya-volume"><button aria-label="Увеличить громкость" title="Громче" onClick={()=>volume(1)}>+</button><button aria-label="Уменьшить громкость" title="Тише" onClick={()=>volume(-1)}>−</button></div><button aria-label="Отключить микрофон" title="Отключить / включить все микрофоны" aria-pressed={muted} disabled={!active} onClick={()=>setMuted(v=>!v)}><MicOff size={18}/><i className={muted?'red':''}/></button></div>
     </div>
    </div>
   </div>
   {textOnly&&<small className="avaya-help">Текстовый режим: передавайте сообщения через чат.</small>}
   {(error||control.error)&&<p className="avaya-error" role="alert">{error||control.error}</p>}
  </div>;
 }
 function renderLine(i:number,controls:PhoneCallControl[]):React.ReactNode{
  if(i===3)return renderDevice(controls);
  return <DDSVoiceCall key={i} disabled={!active||busy||incomingPlaying===i} contacts={contacts} contactId={slots[i].contact} service={p.task.own_service} textOnly={textOnly} held={slots[i].held} muted={muted} engine={engines[i]} incomingReady={slots[i].ready} onStart={()=>startLine(i)} onEnd={()=>endLine(i)} onSelect={id=>{updateSlot(i,{contact:id});onSelect(id);}} onSend={send} render={control=>renderLine(i+1,[...controls,control])}/>;
 }
 return <>{renderLine(0,[])}{slots.map((s,i)=>s.incoming?.audio&&<BrigadeAudio key={s.incoming.event_id||s.incoming.audio} id={s.incoming.audio} playKey={`${p.id}:${s.incoming.event_id||s.incoming.audio}`} hidden autoPlay={active} beforePlay={async player=>engines[i].attach(player)} onError={message=>{setError(message);setIncomingPlaying(null);calls.current[i]?.hangup();}} onEnded={async()=>{await engines[i].replyEnded();setIncomingPlaying(null);updateSlot(i,{ready:String(s.incoming!.event_id||uuid())});}}/>)}</>;
}
