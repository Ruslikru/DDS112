import React,{useContext,useEffect,useRef,useState} from 'react';
import {useLocation,useNavigate} from 'react-router-dom';
import {Sparkles,Send} from 'lucide-react';
import {api,UserContext,type Obj} from './shared';
import {ArmDialog} from './arm-ui';

/** Stage 1 of the teacher assistant: text commands for navigation and reading, parsed by server rules. */
const TOGGLE='training112:assistant-toggle';
const HINTS=['Что умеешь?','Журнал','Проверить работы','Кто сейчас в классе?'];
const allowed=(role:string)=>role==='teacher'||role==='admin';

type Message={who:'user'|'assistant',text:string,candidates?:Obj[],error?:boolean};
type Pending={intent:string,text:string,missing?:string}|null;

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
 const [messages,setMessages]=useState<Message[]>([{who:'assistant',text:'Напишите команду: например, «открой журнал», «покажи, какие работы нужно проверить» или «где сидит Кузнецов».'}]);
 const [text,setText]=useState(''),[busy,setBusy]=useState(false),[pending,setPending]=useState<Pending>(null);
 const input=useRef<HTMLInputElement>(null),log=useRef<HTMLDivElement>(null);
 useEffect(()=>{const t=setTimeout(()=>input.current?.focus(),0);return()=>clearTimeout(t);},[]);
 useEffect(()=>{log.current?.scrollTo({top:log.current.scrollHeight});},[messages,busy]);
 const push=(message:Message)=>setMessages(list=>[...list,message]);
 const send=async(command:string,dialog?:Obj,shown?:string)=>{
  const phrase=command.trim();
  if(!phrase&&!dialog)return;
  push({who:'user',text:shown||phrase});setText('');setBusy(true);
  try{
   const r:Obj=await api('/assistant/interpret','POST',{text:phrase,context:{page:location.pathname},...(dialog?{dialog}:{})});
   push({who:'assistant',text:r.preview||'Готово.',candidates:r.candidates?.length?r.candidates:undefined});
   if(r.candidates?.length)setPending({intent:r.intent,text:phrase});
   else if(r.missing?.length)setPending({intent:r.intent,text:phrase,missing:r.missing[0].slot});
   else setPending(null);
   if(r.action?.kind==='navigate'){navigate(r.action.to);onClose();}
   else if(r.action?.kind==='close')onClose();
  }catch(e:any){push({who:'assistant',text:e.message,error:true});}
  finally{setBusy(false);setTimeout(()=>input.current?.focus(),0);}
 };
 const submit=(e:React.FormEvent)=>{
  e.preventDefault();
  if(busy)return;
  if(pending?.missing==='student'&&text.trim())send(pending.text,{intent:pending.intent,slots:{student_query:text.trim()}},text.trim());
  else send(text);
 };
 const choose=(candidate:Obj)=>{if(busy||!pending)return;send(pending.text,{intent:pending.intent,slots:{student_id:candidate.id}},candidate.label);};
 return <ArmDialog title="Ассистент" className="assistant-shade" onClose={onClose}>
  <div className="assistant-log" ref={log} aria-live="polite">
   {messages.map((message,index)=><div key={index} className={'assistant-message '+message.who+(message.error?' error':'')}>
    <p>{message.text}</p>
    {message.candidates&&index===messages.length-1&&<div className="assistant-candidates">{message.candidates.map((candidate:Obj)=><button type="button" key={candidate.id} disabled={busy} onClick={()=>choose(candidate)}>{candidate.label}</button>)}</div>}
   </div>)}
   {busy&&<div className="assistant-message assistant"><p>Разбираю команду…</p></div>}
  </div>
  <div className="assistant-hints">{HINTS.map(hint=><button type="button" key={hint} disabled={busy} onClick={()=>send(hint)}>{hint}</button>)}</div>
  <form className="assistant-input" onSubmit={submit}>
   <input ref={input} aria-label="Команда ассистенту" value={text} maxLength={500} placeholder={pending?.missing==='student'?'Фамилия или имя ученика':'Команда, например «открой журнал»'} onChange={e=>setText(e.target.value)} disabled={busy}/>
   <button type="submit" disabled={busy||!text.trim()} title="Отправить"><Send size={16}/><span>отправить</span></button>
  </form>
  <small className="assistant-note">Чтение и переходы выполняются сразу. Изменяющие команды появятся на следующих этапах и будут требовать подтверждения.</small>
 </ArmDialog>;
}
