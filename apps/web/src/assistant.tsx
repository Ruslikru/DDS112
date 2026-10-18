import React,{useContext,useEffect,useRef,useState} from 'react';
import {useLocation,useNavigate} from 'react-router-dom';
import {Sparkles,Send} from 'lucide-react';
import {api,UserContext,type Obj} from './shared';
import {ArmDialog} from './arm-ui';

/** Teacher assistant: text commands parsed by server rules. Reading and navigation run at once,
 *  changing commands (tickets) go through a slot form and a confirmation card with a server token. */
const TOGGLE='training112:assistant-toggle';
const HINTS=['Что умеешь?','Журнал','Проверить работы','Кто сейчас в классе?','Новый билет'];
const DIALOG_INTENTS=['create_ticket','edit_ticket'];
const HISTORY_KEY='training112:assistant-history';
const HISTORY_SIZE=10;
/** Last typed commands, newest first; kept per browser only as a convenience. */
function readHistory():string[]{try{const list=JSON.parse(localStorage.getItem(HISTORY_KEY)||'[]');return Array.isArray(list)?list.filter(x=>typeof x==='string').slice(0,HISTORY_SIZE):[];}catch{return [];}}
function remember(list:string[],phrase:string):string[]{const next=[phrase,...list.filter(x=>x!==phrase)].slice(0,HISTORY_SIZE);try{localStorage.setItem(HISTORY_KEY,JSON.stringify(next));}catch{}return next;}
const allowed=(role:string)=>role==='teacher'||role==='admin';

type Message={who:'user'|'assistant',text:string,candidates?:Obj[],options?:{slot:string,options:Obj[]},confirm?:{intent:string,slots:Obj,token:string},error?:boolean};
/** The open slot form: intent, accumulated slots and the question waiting for an answer. */
type Dialog={intent:string,slots:Obj,missing?:string}|null;

/** Header button: the window itself is mounted once in App, so the shortcut is registered once. */
export function AssistantButton(){
 const u=useContext(UserContext);
 if(!allowed(u.role))return null;
 return <button type="button" className="assistant-button" title="Ассистент преподавателя (Ctrl+Space)" onClick={()=>window.dispatchEvent(new Event(TOGGLE))}><Sparkles size={17}/><span>ассистент</span></button>;
}

export function TeacherAssistant(){
 const u=useContext(UserContext),[open,setOpen]=useState(false);
 useEffect(()=>{
  if(!allowed(u.role))return;
  const toggle=()=>setOpen(value=>!value);
  const key=(e:KeyboardEvent)=>{if(e.ctrlKey&&!e.altKey&&!e.metaKey&&e.code==='Space'){e.preventDefault();toggle();}};
  window.addEventListener(TOGGLE,toggle);document.addEventListener('keydown',key);
  return()=>{window.removeEventListener(TOGGLE,toggle);document.removeEventListener('keydown',key);};
 },[u.role]);
 if(!allowed(u.role)||!open)return null;
 return <AssistantDialog onClose={()=>setOpen(false)}/>;
}

function AssistantDialog({onClose}:{onClose:()=>void}){
 const navigate=useNavigate(),location=useLocation();
 const [messages,setMessages]=useState<Message[]>([{who:'assistant',text:'Напишите команду: например, «открой журнал», «покажи, какие работы нужно проверить», «где сидит Кузнецов» или «создай билет про пожар на 3 звезды».'}]);
 const [text,setText]=useState(''),[busy,setBusy]=useState<''|'ask'|'run'>(''),[dialog,setDialog]=useState<Dialog>(null);
 const [history,setHistory]=useState<string[]>(readHistory),[historyOpen,setHistoryOpen]=useState(false),[cursor,setCursor]=useState(-1);
 const input=useRef<HTMLTextAreaElement>(null),log=useRef<HTMLDivElement>(null);
 useEffect(()=>{const t=setTimeout(()=>input.current?.focus(),0);return()=>clearTimeout(t);},[]);
 useEffect(()=>{log.current?.scrollTo({top:log.current.scrollHeight});},[messages,busy]);
 const push=(message:Message)=>setMessages(list=>[...list,message]);
 const focus=()=>setTimeout(()=>input.current?.focus(),0);
 const finish=(action:Obj|undefined)=>{
  if(action?.kind==='navigate'){navigate(action.to);onClose();return true;}
  if(action?.kind==='close'){onClose();return true;}
  return false;
 };
 /** Sends a phrase; `slots` carries an answer given with a button, `shown` is what the log displays. */
 const send=async(command:string,slots?:Obj,shown?:string)=>{
  const phrase=command.trim();
  if(!phrase&&!slots)return;
  push({who:'user',text:shown||phrase});setText('');setCursor(-1);setBusy('ask');
  if(!slots&&phrase&&!dialog?.missing)setHistory(list=>remember(list,phrase));
  try{
   const body:Obj={text:phrase,context:{page:location.pathname}};
   if(dialog)body.dialog={intent:dialog.intent,slots:{...dialog.slots,...(slots||{}),...(slots?{answer_slot:Object.keys(slots)[0]}:dialog.missing?{answer_slot:dialog.missing}:{})}};
   const r:Obj=await api('/assistant/interpret','POST',body);
   const question=r.missing?.[0];
   push({who:'assistant',text:r.preview||'Готово.',candidates:r.candidates?.length?r.candidates:undefined,options:question?.options?.length?{slot:question.slot,options:question.options}:undefined,confirm:r.confirm_required?{intent:r.intent,slots:r.slots,token:r.confirm_token}:undefined});
   if(finish(r.action))return;
   if(r.candidates?.length||question||r.confirm_required)setDialog({intent:r.intent,slots:DIALOG_INTENTS.includes(r.intent)?r.slots:{},missing:question?.slot});
   else setDialog(null);
  }catch(e:any){push({who:'assistant',text:e.message,error:true});}
  finally{setBusy('');focus();}
 };
 const run=async(confirm:{intent:string,slots:Obj,token:string})=>{
  if(busy)return;
  push({who:'user',text:'Выполнить'});setBusy('run');
  try{
   const r:Obj=await api('/assistant/execute','POST',{intent:confirm.intent,slots:confirm.slots,confirm_token:confirm.token});
   push({who:'assistant',text:r.preview||'Выполнено.'});
   setDialog(null);
   finish(r.action);
  }catch(e:any){push({who:'assistant',text:e.message,error:true});}
  finally{setBusy('');focus();}
 };
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
 const cancel=()=>{setDialog(null);push({who:'assistant',text:'Отменено. Ничего не изменено.'});focus();};
 const adjust=()=>{push({who:'assistant',text:'Напишите, что поменять: например «сложность 4», «режим 112» или «без пострадавших».'});focus();};
 const openWizard=(slots:Obj)=>{navigate('/tickets',{state:{wizard:{own_service:slots.own_service,services:slots.services,incident_type:slots.incident_type,mode:slots.mode,difficulty_stars:slots.difficulty,victims_state:slots.victims,victims_count:slots.victims_count||1}}});onClose();};
 const last=messages.length-1;
 return <ArmDialog title="Ассистент" className="assistant-shade" onClose={onClose}>
  <div className="assistant-log" ref={log} aria-live="polite">
   {messages.map((message,index)=><div key={index} className={'assistant-message '+message.who+(message.error?' error':'')}>
    <p>{message.text}</p>
    {message.candidates&&index===last&&<div className="assistant-candidates">{message.candidates.map((candidate:Obj)=><button type="button" key={candidate.id} disabled={!!busy} onClick={()=>choose(candidate)}>{candidate.label}</button>)}</div>}
    {message.options&&index===last&&<div className="assistant-candidates">{message.options.options.map((option:Obj)=><button type="button" key={String(option.value)} disabled={!!busy} onClick={()=>pick(message.options!.slot,option)}>{option.label}</button>)}</div>}
    {message.confirm&&index===last&&dialog&&<div className="assistant-confirm" role="group" aria-label="Подтверждение команды">
     <button type="button" className="primary" disabled={!!busy} onClick={()=>run(message.confirm!)}>Выполнить</button>
     <button type="button" disabled={!!busy} onClick={adjust}>Изменить</button>
     {message.confirm.intent==='create_ticket'&&<button type="button" disabled={!!busy} onClick={()=>openWizard(message.confirm!.slots)}>Открыть в мастере</button>}
     <button type="button" disabled={!!busy} onClick={cancel}>Отмена</button>
    </div>}
   </div>)}
   {busy&&<div className="assistant-message assistant"><p>{busy==='run'?'Выполняю… Создание черновика занимает до минуты: модель работает локально.':'Разбираю команду…'}</p></div>}
  </div>
  <div className="assistant-hints">{HINTS.map(hint=><button type="button" key={hint} disabled={!!busy} onClick={()=>send(hint)}>{hint}</button>)}{dialog&&<button type="button" className="assistant-cancel" disabled={!!busy} onClick={cancel}>Сбросить диалог</button>}</div>
  {history.length>0&&<div className="assistant-history"><button type="button" aria-expanded={historyOpen} onClick={()=>setHistoryOpen(v=>!v)}>История команд ({history.length}) {historyOpen?'▴':'▾'}</button>{historyOpen&&<ul>{history.map(item=><li key={item}><button type="button" disabled={!!busy} title="Повторить команду" onClick={()=>{setHistoryOpen(false);send(item);}}>{item}</button></li>)}</ul>}</div>}
  <form className="assistant-input" onSubmit={submit}>
   <textarea ref={input} aria-label="Команда ассистенту" rows={2} value={text} maxLength={500} placeholder={dialog?.missing==='student'?'Фамилия или имя ученика':dialog?.missing?'Ответ на вопрос ассистента':dialog?'Что изменить в команде?':'Команда, например «открой журнал». Enter — отправить, ↑ — предыдущая команда'} onChange={e=>{setText(e.target.value);setCursor(-1);}} onKeyDown={keys} disabled={!!busy}/>
   <button type="submit" disabled={!!busy||!text.trim()} title="Отправить"><Send size={16}/><span>отправить</span></button>
  </form>
  <small className="assistant-note">Чтение и переходы выполняются сразу. Создание и изменение билета выполняются только после кнопки «Выполнить».</small>
 </ArmDialog>;
}
