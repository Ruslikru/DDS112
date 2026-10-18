import React,{useContext,useEffect,useRef,useState} from 'react';
import {useLocation,useNavigate} from 'react-router-dom';
import {Sparkles,Send,Mic,MicOff} from 'lucide-react';
import {api,UserContext,type Obj} from './shared';
import {ArmDialog} from './arm-ui';
import {record,hasVoiceBridge,serverTranscribe} from './voice';

/** Teacher assistant: text commands parsed by server rules. Reading and navigation run at once,
 *  changing commands (tickets) go through a slot form and confirmation cards with a server token.
 *  The log and the open slot form live in TeacherAssistant, so closing the window keeps them.
 *  The window is a docked panel in the bottom-right corner without a shade: the page behind stays
 *  usable and a navigation command keeps the panel open; whether it is open survives a reload. */
const TOGGLE='training112:assistant-toggle';
const OPEN_KEY='training112:assistant-open';
/** Push-to-talk: recording runs while the microphone button or Ctrl+Space is held and is sent on release. */
const VOICE_START='training112:assistant-voice-start';
const VOICE_STOP='training112:assistant-voice-stop';
/** A press shorter than this is treated as a click, not speech: the recording is discarded. */
const MIN_HOLD_MS=400;
const VOICE_HINT='Голосовой ввод доступен в приложении Windows или на ПК сервера.';
/** Spoken answers to an open confirmation card are handled on the client, without the server. JS \b ignores Cyrillic, hence the lookahead. */
const VOICE_YES=/^(да|ага|выполняй|выполни|выполнить|подтверждаю|подтверди|давай|сохрани|сохранить|ок|окей|хорошо)(?=[\s.,!?]|$)/i;
const VOICE_NO=/^(нет|отмена|отмени|отменить|не надо|не нужно|стоп|не выполняй)(?=[\s.,!?]|$)/i;
const HINTS=['Что умеешь?','Журнал','Проверить работы','Кто сейчас в классе?','Новый билет'];
const DIALOG_INTENTS=['create_ticket','edit_ticket','save_ticket'];
const HISTORY_KEY='training112:assistant-history';
const HISTORY_SIZE=10;
const WELCOME:Message={who:'assistant',text:'Напишите команду: например, «открой журнал», «покажи, какие работы нужно проверить», «где сидит Кузнецов» или «создай билет про пожар на 3 звезды».'};
/** Last typed commands, newest first; kept per browser only as a convenience. */
function readHistory():string[]{try{const list=JSON.parse(localStorage.getItem(HISTORY_KEY)||'[]');return Array.isArray(list)?list.filter(x=>typeof x==='string').slice(0,HISTORY_SIZE):[];}catch{return [];}}
function remember(list:string[],phrase:string):string[]{const next=[phrase,...list.filter(x=>x!==phrase)].slice(0,HISTORY_SIZE);try{localStorage.setItem(HISTORY_KEY,JSON.stringify(next));}catch{}return next;}
const allowed=(role:string)=>role==='teacher'||role==='admin';

type Confirm={intent:string,slots:Obj,token:string};
type Link={label:string,to:string};
type Message={who:'user'|'assistant',text:string,candidates?:Obj[],options?:{slot:string,options:Obj[]},confirm?:Confirm,links?:Link[],error?:boolean,retry?:{confirm:Confirm}|{origin:string}};
/** The open slot form: intent, accumulated slots and the question waiting for an answer. */
type Dialog={intent:string,slots:Obj,missing?:string}|null;
type Store={messages:Message[],setMessages:React.Dispatch<React.SetStateAction<Message[]>>,dialog:Dialog,setDialog:(d:Dialog)=>void,origin:React.MutableRefObject<string>,creation:React.MutableRefObject<Confirm|null>,autoRecord:React.MutableRefObject<boolean>,holding:React.MutableRefObject<boolean>};
type VoiceSource='checking'|'bridge'|'server'|'none';

/** Header button: the window itself is mounted once in App, so the shortcut is registered once. */
export function AssistantButton(){
 const u=useContext(UserContext);
 if(!allowed(u.role))return null;
 return <button type="button" className="assistant-button" title="Ассистент преподавателя (Ctrl+Space)" onClick={()=>window.dispatchEvent(new Event(TOGGLE))}><Sparkles size={17}/><span>ассистент</span></button>;
}

export function TeacherAssistant(){
 const u=useContext(UserContext),[open,setOpen]=useState(()=>{try{return localStorage.getItem(OPEN_KEY)==='1';}catch{return false;}});
 useEffect(()=>{try{localStorage.setItem(OPEN_KEY,open?'1':'0');}catch{}},[open]);
 const [messages,setMessages]=useState<Message[]>([WELCOME]),[dialog,setDialog]=useState<Dialog>(null);
 /** The phrase that opened the current slot form (for «Составить заново») and the last create confirmation (for «Сгенерировать заново»). */
 const origin=useRef(''),creation=useRef<Confirm|null>(null),autoRecord=useRef(false),holding=useRef(false);
 const opened=useRef(open);opened.current=open;
 useEffect(()=>{
  if(!allowed(u.role))return;
  const toggle=()=>setOpen(value=>!value);
  // Ctrl+Space held: opens the window if needed and records while the keys are down; releasing Space or Ctrl sends the phrase.
  const down=(e:KeyboardEvent)=>{if(e.ctrlKey&&!e.altKey&&!e.metaKey&&e.code==='Space'){e.preventDefault();if(e.repeat||holding.current)return;holding.current=true;if(opened.current)window.dispatchEvent(new Event(VOICE_START));else{autoRecord.current=true;setOpen(true);}}};
  const up=(e:KeyboardEvent)=>{if(holding.current&&(e.code==='Space'||e.key==='Control')){holding.current=false;window.dispatchEvent(new Event(VOICE_STOP));}};
  const blur=()=>{if(holding.current){holding.current=false;window.dispatchEvent(new Event(VOICE_STOP));}};
  window.addEventListener(TOGGLE,toggle);document.addEventListener('keydown',down);document.addEventListener('keyup',up);window.addEventListener('blur',blur);
  return()=>{window.removeEventListener(TOGGLE,toggle);document.removeEventListener('keydown',down);document.removeEventListener('keyup',up);window.removeEventListener('blur',blur);};
 },[u.role]);
 if(!allowed(u.role)||!open)return null;
 return <AssistantDialog onClose={()=>setOpen(false)} store={{messages,setMessages,dialog,setDialog,origin,creation,autoRecord,holding}}/>;
}

function AssistantDialog({onClose,store}:{onClose:()=>void,store:Store}){
 const navigate=useNavigate(),location=useLocation();
 const {messages,setMessages,dialog,setDialog,origin,creation,autoRecord,holding}=store;
 const [text,setText]=useState(''),[busy,setBusy]=useState<''|'ask'|'run'|'generate'>('');
 const [voice,setVoice]=useState<VoiceSource>(()=>hasVoiceBridge()?'bridge':'checking'),[recording,setRecording]=useState(false),[listening,setListening]=useState(''),[heard,setHeard]=useState('');
 const stopRecording=useRef<((cancel?:boolean)=>void)|undefined>(undefined),startedAt=useRef(0);
 /** Recognition finishes asynchronously, so spoken answers must look at the current log and slot form, not at the ones captured when recording started. */
 const latest=useRef({messages,dialog});latest.current={messages,dialog};
 useEffect(()=>{
  if(voice!=='checking')return;
  let alive=true;
  api('/voice/settings').then((s:Obj)=>{if(alive)setVoice(s?.available?'server':'none');}).catch(()=>{if(alive)setVoice('none');});
  return()=>{alive=false;};
 },[voice]);
 useEffect(()=>()=>{stopRecording.current?.();},[]);
 const [history,setHistory]=useState<string[]>(readHistory),[historyOpen,setHistoryOpen]=useState(false),[cursor,setCursor]=useState(-1);
 const input=useRef<HTMLTextAreaElement>(null),log=useRef<HTMLDivElement>(null);
 useEffect(()=>{const t=setTimeout(()=>input.current?.focus(),0);return()=>clearTimeout(t);},[]);
 useEffect(()=>{log.current?.scrollTo({top:log.current.scrollHeight});},[messages,busy]);
 const push=(message:Message)=>setMessages(list=>[...list,message]);
 const focus=()=>setTimeout(()=>input.current?.focus(),0);
 /** Navigation keeps the panel open: the page changes behind it and the answer stays in the log. */
 const go=(to:string)=>{navigate(to);focus();};
 const finish=(action:Obj|undefined)=>{
  if(action?.kind==='navigate'){go(action.to);return true;}
  if(action?.kind==='close'){onClose();return true;}
  return false;
 };
 /** Sends a phrase; `slots` carries an answer given with a button, `shown` is what the log displays. */
 const send=async(command:string,slots?:Obj,shown?:string):Promise<Obj|null>=>{
  const phrase=command.trim();
  if(!phrase&&!slots)return null;
  push({who:'user',text:shown||phrase});setText('');setCursor(-1);setBusy('ask');
  if(!slots&&phrase&&!dialog?.missing)setHistory(list=>remember(list,phrase));
  try{
   const body:Obj={text:phrase,context:{page:location.pathname}};
   if(dialog)body.dialog={intent:dialog.intent,slots:{...dialog.slots,...(slots||{}),...(slots?{answer_slot:Object.keys(slots)[0]}:dialog.missing?{answer_slot:dialog.missing}:{})}};
   const r:Obj=await api('/assistant/interpret','POST',body);
   const question=r.missing?.[0];
   push({who:'assistant',text:r.preview||'Готово.',candidates:r.candidates?.length?r.candidates:undefined,options:question?.options?.length?{slot:question.slot,options:question.options}:undefined,confirm:r.confirm_required?{intent:r.intent,slots:r.slots,token:r.confirm_token}:undefined,links:r.links?.length?r.links:undefined});
   if(finish(r.action))return r;
   if(r.candidates?.length||question||r.confirm_required){if(!dialog)origin.current=phrase;setDialog({intent:r.intent,slots:DIALOG_INTENTS.includes(r.intent)?r.slots:{},missing:question?.slot});}
   else setDialog(null);
   return r;
  }catch(e:any){push({who:'assistant',text:e.message,error:true});return null;}
  finally{setBusy('');focus();}
 };
 /** Recognised speech: short answers close an open confirmation card, anything else is sent as a command;
  *  an unrecognised command stays in the field for editing instead of doing anything. */
 const heardText=async(spoken:string)=>{
  const phrase=spoken.trim();
  setListening('');setHeard(phrase);
  const {messages:log,dialog:form}=latest.current;
  const card=log[log.length-1]?.confirm;
  if(card&&form){
   if(VOICE_YES.test(phrase)){run(card,card.intent==='save_ticket'?'Сохранить':'Выполнить');return;}
   if(VOICE_NO.test(phrase)){cancel();return;}
  }
  if(phrase.length<3){setHeard('');push({who:'assistant',text:'Речь не распознана, повторите.',error:true});return;}
  const r=await send(phrase);
  if(r&&r.intent==='unknown'){setText(phrase);push({who:'assistant',text:'Команда оставлена в поле: поправьте текст и отправьте.'});}
 };
 /** Release of the button or keys: the recording is sent for recognition; a press shorter than MIN_HOLD_MS is discarded. */
 const finishRecording=()=>{
  holding.current=false;
  const stop=stopRecording.current;
  if(!stop)return;
  stopRecording.current=undefined;setRecording(false);
  // Measured from the moment the microphone actually started, not from the press: the permission prompt can eat the first seconds.
  if(Date.now()-startedAt.current<MIN_HOLD_MS){stop(true);setListening('Запись не успела начаться. Удерживайте кнопку и говорите после слова «Говорите».');return;}
  stop();setListening('Распознаём…');
 };
 /** Press of the button or keys: records until release (or 15 seconds). `holding` is set by the caller before this runs. */
 const startRecording=async()=>{
  if(recording||stopRecording.current||busy||voice==='none'||voice==='checking'){holding.current=false;return;}
  startedAt.current=Date.now();
  setHeard('');setListening('Включаем микрофон…');
  const stop=await record(spoken=>{stopRecording.current=undefined;setRecording(false);heardText(spoken);},problem=>{stopRecording.current=undefined;setRecording(false);setListening('');push({who:'assistant',text:problem,error:true});},voice==='server'?serverTranscribe:undefined);
  if(!stop){holding.current=false;setListening('');return;}
  startedAt.current=Date.now();
  stopRecording.current=stop;setRecording(true);setListening('Говорите. Отпустите кнопку, чтобы отправить.');
  // The microphone can take a moment to start; if the button was already released, finish at once.
  if(!holding.current)finishRecording();
 };
 const voiceStart=useRef(startRecording);voiceStart.current=startRecording;
 const voiceStop=useRef(finishRecording);voiceStop.current=finishRecording;
 useEffect(()=>{const start=()=>{voiceStart.current();},stop=()=>{voiceStop.current();};window.addEventListener(VOICE_START,start);window.addEventListener(VOICE_STOP,stop);return()=>{window.removeEventListener(VOICE_START,start);window.removeEventListener(VOICE_STOP,stop);};},[]);
 useEffect(()=>{if(autoRecord.current&&voice!=='checking'){autoRecord.current=false;if(voice!=='none'&&holding.current)voiceStart.current();else holding.current=false;}},[voice]);
 useEffect(()=>()=>{stopRecording.current?.(true);},[]);
 // Ask for the microphone when the window opens, so the browser's permission prompt does not fall into the first held recording.
 useEffect(()=>{if(voice!=='server'&&voice!=='bridge')return;navigator.mediaDevices?.getUserMedia?.({audio:true}).then(stream=>stream.getTracks().forEach(track=>track.stop())).catch(()=>{});},[voice]);
 const micDisabled=!recording&&(!!busy||voice==='none'||voice==='checking');
 const micTitle=voice==='none'?VOICE_HINT:voice==='checking'?'Проверяем голосовой модуль…':recording?'Отпустите, чтобы отправить':'Удерживайте и говорите (Ctrl+Space)';
 const press=(e:React.PointerEvent<HTMLButtonElement>)=>{if(micDisabled||e.button!==0)return;e.preventDefault();try{e.currentTarget.setPointerCapture(e.pointerId);}catch{}holding.current=true;startRecording();};
 const release=()=>{if(holding.current||stopRecording.current)finishRecording();};
 const micKey=(e:React.KeyboardEvent<HTMLButtonElement>)=>{if(e.key!==' '&&e.key!=='Enter')return;e.preventDefault();if(e.type==='keydown'){if(e.repeat||holding.current||micDisabled)return;holding.current=true;startRecording();}else release();};
 /** Runs a confirmed command. A new ticket answers with its draft and a second confirmation («Сохранить»). */
 const run=async(confirm:Confirm,label='Выполнить')=>{
  if(busy)return;
  push({who:'user',text:label});setBusy(confirm.intent==='create_ticket'?'generate':'run');
  if(confirm.intent==='create_ticket')creation.current=confirm;
  try{
   const r:Obj=await api('/assistant/execute','POST',{intent:confirm.intent,slots:confirm.slots,confirm_token:confirm.token});
   const next=r.confirm_required?{intent:r.intent,slots:r.slots,token:r.confirm_token}:undefined;
   push({who:'assistant',text:r.preview||'Выполнено.',confirm:next,links:r.links?.length?r.links:undefined});
   if(next)setDialog({intent:r.intent,slots:r.slots});
   else{setDialog(null);creation.current=null;finish(r.action);}
  }catch(e:any){
   // 409: the token or draft is older than ten minutes, so the command has to be composed again; anything else can simply be retried.
   const expired=e.status===409;
   push({who:'assistant',text:e.message,error:true,retry:expired?{origin:origin.current}:{confirm}});
  }
  finally{setBusy('');focus();}
 };
 const recompose=(phrase:string)=>{setDialog(null);if(phrase)send(phrase);else focus();};
 const submit=(e:React.FormEvent)=>{e.preventDefault();if(!busy)send(text);};
 /** Enter sends, Shift+Enter adds a line; ↑/↓ walk the history when the field holds no edited text. */
 const keys=(e:React.KeyboardEvent<HTMLTextAreaElement>)=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();if(!busy)send(text);return;}
  if((e.key==='ArrowUp'||e.key==='ArrowDown')&&history.length&&(cursor>=0||!text.trim())){
   e.preventDefault();
   const next=e.key==='ArrowUp'?Math.min(cursor+1,history.length-1):cursor-1;
   setCursor(next);setText(next<0?'':history[next]);
  }
 };
 const choose=(candidate:Obj)=>{if(busy)return;send(candidate.label,{[candidate.slot||'student_id']:candidate.id},candidate.label);};
 const pick=(slot:string,option:Obj)=>{if(busy)return;send(option.label,{[slot]:option.value},option.label);};
 const cancel=()=>{setDialog(null);creation.current=null;push({who:'assistant',text:'Отменено. Ничего не изменено.'});focus();};
 const clear=()=>{setMessages([WELCOME]);setDialog(null);creation.current=null;focus();};
 const adjust=()=>{push({who:'assistant',text:'Напишите, что поменять: например «сложность 4», «режим 112» или «без пострадавших».'});focus();};
 const openWizard=(slots:Obj)=>{navigate('/tickets',{state:{wizard:{own_service:slots.own_service,services:slots.services,incident_type:slots.incident_type,mode:slots.mode,difficulty_stars:slots.difficulty,victims_state:slots.victims,victims_count:slots.victims_count||1,traits:slots.traits||[]}}});focus();};
 const last=messages.length-1;
 const busyText=busy==='generate'?'Создаю черновик… Модель работает локально, это может занять до минуты.':busy==='run'?'Выполняю…':'Разбираю команду…';
 return <ArmDialog title="Ассистент" className="assistant-shade" modal={false} onClose={onClose}>
  <div className="assistant-log" ref={log} aria-live="polite">
   {messages.map((message,index)=><div key={index} className={'assistant-message '+message.who+(message.error?' error':'')}>
    <p>{message.text}</p>
    {message.links&&<div className="assistant-links">{message.links.map(link=><button type="button" key={link.to+link.label} disabled={!!busy} onClick={()=>go(link.to)}>{link.label} →</button>)}</div>}
    {message.candidates&&index===last&&<div className="assistant-candidates">{message.candidates.map((candidate:Obj)=><button type="button" key={candidate.id} disabled={!!busy} onClick={()=>choose(candidate)}>{candidate.label}</button>)}</div>}
    {message.options&&index===last&&<div className="assistant-candidates">{message.options.options.map((option:Obj)=><button type="button" key={String(option.value)} disabled={!!busy} onClick={()=>pick(message.options!.slot,option)}>{option.label}</button>)}</div>}
    {message.retry&&index===last&&<div className="assistant-confirm" role="group" aria-label="Повтор команды">
     {'confirm' in message.retry?<button type="button" className="primary" disabled={!!busy} onClick={()=>run((message.retry as {confirm:Confirm}).confirm,'Повторить')}>Повторить</button>
     :<button type="button" className="primary" disabled={!!busy} onClick={()=>recompose((message.retry as {origin:string}).origin)}>Составить заново</button>}
     <button type="button" disabled={!!busy} onClick={cancel}>Отмена</button>
    </div>}
    {message.confirm&&index===last&&dialog&&(message.confirm.intent==='save_ticket'
     ?<div className="assistant-confirm" role="group" aria-label="Сохранение черновика">
       <button type="button" className="primary" disabled={!!busy} onClick={()=>run(message.confirm!,'Сохранить')}>Сохранить</button>
       {creation.current&&<button type="button" disabled={!!busy} onClick={()=>run(creation.current!,'Сгенерировать заново')}>Сгенерировать заново</button>}
       <button type="button" disabled={!!busy} onClick={cancel}>Отмена</button>
      </div>
     :<div className="assistant-confirm" role="group" aria-label="Подтверждение команды">
       <button type="button" className="primary" disabled={!!busy} onClick={()=>run(message.confirm!)}>Выполнить</button>
       <button type="button" disabled={!!busy} onClick={adjust}>Изменить</button>
       {message.confirm.intent==='create_ticket'&&<button type="button" disabled={!!busy} onClick={()=>openWizard(message.confirm!.slots)}>Открыть в мастере</button>}
       <button type="button" disabled={!!busy} onClick={cancel}>Отмена</button>
      </div>)}
   </div>)}
   {busy&&<div className="assistant-message assistant"><p>{busyText}</p></div>}
  </div>
  <div className="assistant-hints">{HINTS.map(hint=><button type="button" key={hint} disabled={!!busy} onClick={()=>send(hint)}>{hint}</button>)}{dialog?<button type="button" className="assistant-cancel" disabled={!!busy} onClick={cancel}>Сбросить диалог</button>:messages.length>1&&<button type="button" className="assistant-cancel" disabled={!!busy} onClick={clear}>Очистить ленту</button>}</div>
  {history.length>0&&<div className="assistant-history"><button type="button" aria-expanded={historyOpen} onClick={()=>setHistoryOpen(v=>!v)}>История команд ({history.length}) {historyOpen?'▴':'▾'}</button>{historyOpen&&<ul>{history.map(item=><li key={item}><button type="button" disabled={!!busy} title="Повторить команду" onClick={()=>{setHistoryOpen(false);send(item);}}>{item}</button></li>)}</ul>}</div>}
  {(listening||heard)&&<div className="assistant-voice-status" role="status" aria-live="polite">{listening||('Распознано: '+heard)}</div>}
  <form className="assistant-input" onSubmit={submit}>
   <button type="button" className={'voice-mic assistant-mic '+(recording?'recording':micDisabled?'waiting':'ready')} disabled={micDisabled} title={micTitle} aria-label={micTitle} aria-pressed={recording} onPointerDown={press} onPointerUp={release} onPointerCancel={release} onKeyDown={micKey} onKeyUp={micKey} onContextMenu={e=>e.preventDefault()}>{recording?<Mic size={25}/>:<MicOff size={25}/>}</button>
   <textarea ref={input} aria-label="Команда ассистенту" rows={2} value={text} maxLength={500} placeholder={dialog?.missing==='student'?'Фамилия или имя ученика':dialog?.missing?'Ответ на вопрос ассистента':dialog?'Что изменить в команде?':'Команда, например «открой журнал». Enter — отправить, ↑ — предыдущая команда'} onChange={e=>{setText(e.target.value);setCursor(-1);}} onKeyDown={keys} disabled={!!busy}/>
   <button type="submit" disabled={!!busy||!text.trim()} title="Отправить"><Send size={16}/><span>отправить</span></button>
  </form>
  <small className="assistant-note">Чтение и переходы выполняются сразу. Создание и изменение билета выполняются только после кнопки «Выполнить», черновик показывается перед сохранением.{voice==='none'&&' '+VOICE_HINT}{voice==='server'&&' Распознавание речи выполняется на сервере.'}</small>
 </ArmDialog>;
}
