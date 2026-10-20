import React,{useEffect,useState,useRef,useMemo} from 'react';
import {Phone,PhoneOff,MessageSquare} from 'lucide-react';
import {Obj,api,uuid} from './shared';
import {CallAudioEngine} from './call-audio';
import {BrigadeAudio,DDSVoiceCall,LiveVoice,useVoiceChat} from './voice';
import {AIQuestion,AIContact} from './ai';

/** The handset stays visible; long conversations  open above it. */
export function PhoneDock({p,owner,busy,contactId,setContactId,contactText,setContactText,cmd,onUpdate,onOpen}:{p:Obj,owner:boolean,busy:boolean,contactId:string,setContactId:(s:string)=>void,contactText:string,setContactText:(s:string)=>void,cmd:(type:string,payload?:Obj)=>Promise<any>,onUpdate:(p:Obj)=>void,onOpen:()=>void}){
 const engine=useMemo(()=>({current:new CallAudioEngine()}),[p.id]);
 const session=useRef(uuid()),line=useRef(false),cooldown=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
 const [outgoing,setOutgoing]=useState(false),[cooling,setCooling]=useState(false),[audioError,setAudioError]=useState('');
 async function startLine(){line.current=true;setOutgoing(true);try{await api('/call-audio/attempts/'+p.id+'/line','POST',{session:session.current,active:true});}catch(e){line.current=false;setOutgoing(false);throw e;}}
 function endLine(){if(!line.current)return;line.current=false;setOutgoing(false);setCooling(true);void api('/call-audio/attempts/'+p.id+'/line','POST',{session:session.current,active:false}).catch(e=>setAudioError(e.message));clearTimeout(cooldown.current);cooldown.current=setTimeout(()=>setCooling(false),2500);}
 useEffect(()=>{const timer=setInterval(()=>{if(line.current)void api('/call-audio/attempts/'+p.id+'/line','POST',{session:session.current,active:true}).catch(e=>setAudioError(e.message));},20000);return()=>{clearInterval(timer);clearTimeout(cooldown.current);engine.current?.dispose();if(line.current)void api('/call-audio/attempts/'+p.id+'/line','POST',{session:session.current,active:false}).catch(()=>{});};},[p.id]);
 const [incomingPlaying,setIncomingPlaying]=useState(false),[callEnded,setCallEnded]=useState(false);
 const [history,setHistory]=useState(false),[chat,setChat]=useState(false);
 const textOnly=!!p.state.text_only,allowChat=useVoiceChat()||textOnly,dds=p.task.mode==='dds',done=['completed','aborted'].includes(p.status),active=owner&&!done&&p.status!=='paused',incoming=p.state.incoming_calls||[];
 const messages=dds?p.state.messages:p.state.dialogue,contact=p.task.contacts?.find((c:Obj)=>c.id===contactId);
 useEffect(()=>{setCallEnded(false);},[messages.length]);
 function ended(){
  setIncomingPlaying(false);setCallEnded(true);engine.current?.hangup();endLine();
 }
 const ringing=dds?incoming.length>0&&!outgoing&&!incomingPlaying&&!cooling:p.state.call==='ringing';
 useEffect(()=>{if(!ringing||!owner)return;let live=true;
  engine.current!.prepare(dds?incoming[0]?.call_audio:{}).then(()=>{if(live)return engine.current!.signal('ring',true);}).catch(e=>{if(live)setAudioError(e.message);});
  return()=>{live=false;engine.current?.stop();};
 },[ringing,owner]);
 async function accept(){
  onOpen();setAudioError('');
  // The ticket was not voiced when the attempt started: the brigade's report arrives as text.
  if(textOnly){const result=await cmd('accept_dds_call',{id:incoming[0].id});if(result){setCallEnded(true);setHistory(true);}return;}
  try{await startLine();engine.current?.stop();await engine.current?.connect(incoming[0].call_audio);setIncomingPlaying(true);const result=await cmd('accept_dds_call',{id:incoming[0].id});if(!result)throw Error('Не удалось принять звонок');
   if(!result.state?.messages?.filter((m:Obj)=>m.direction==='incoming').at(-1)?.audio){ended();setHistory(true);}}
  catch(e:any){setAudioError(e.message);ended();}
 }
 return <section data-guide="phone" className={"phone-dock"+(ringing?" is-ringing":"")} aria-label="Учебная связь">
  {audioError&&<p role="alert">{audioError}</p>}{textOnly&&<p className="phone-text-only">Без звука: сообщения — текстом, связь через чат.</p>}<div className="phone-dock-tools"><button title="История связи" onClick={()=>{setHistory(!history);onOpen();}}>История связи</button>{allowChat&&<button aria-pressed={chat} onClick={()=>{setChat(!chat);onOpen();}}><MessageSquare size={14}/> Использовать чат</button>}</div>
  {(history||chat)&&<div className="phone-dock-popover"><button onClick={()=>{setHistory(false);setChat(false);}}>Закрыть {chat?'чат':'историю'}</button><div className="phone-transcript">{messages.map((m:Obj,i:number)=><div key={i}><small>{m.who}</small><p>{m.text||m.message}</p></div>)}{!messages.length&&<p>Разговор ещё не начат.</p>}</div>{chat&&allowChat&&active&&(dds?<><textarea aria-label="Сообщение абоненту" value={contactText} onChange={e=>setContactText(e.target.value)}/><button data-guide="contact" disabled={busy||!contactId||contactText.trim().length<3} onClick={()=>cmd('contact',{id:contactId,text:contactText})}>Связаться и передать</button>{contactId&&<AIContact p={p} contactId={contactId} text={contactText} onUpdate={onUpdate}/>}</>:p.state.call==='connected'&&<AIQuestion p={p} onUpdate={onUpdate} textOnly/>)}</div>}
  <div className="phone-dock-line">{(!dds||ringing)&&<div><b>{ringing?(dds?incoming[0].who:'Входящий вызов'):dds?(contact?.name||'Бригада / служба'):p.state.call==='connected'?'Заявитель':'Разговор завершён'}</b><small>{dds?contact?.phone:p.task.phone}</small></div>}
   {dds?(ringing?<button data-guide="accept" className="handset answer" title="Принять звонок" aria-label="Принять звонок" disabled={!active||busy} onClick={accept}><Phone size={24}/></button>:active&&<DDSVoiceCall key={p.id} engine={engine.current} onStart={startLine} onEnd={endLine} incomingState={incomingPlaying?'Бригада сообщает. Слушайте…':callEnded?'Абонент завершил звонок':undefined} disabled={busy||incomingPlaying} contacts={p.task.contacts||[]} service={p.task.own_service} textOnly={textOnly||chat&&allowChat} contactId={contactId} onSelect={id=>{setCallEnded(false);setContactId(id);if(textOnly)setChat(true);onOpen();}} onSend={async(text,id)=>{setContactText(text);const result=await cmd('contact',{id,text});if(!result)throw Error('Не удалось передать сообщение. Проверьте связь и повторите звонок.');return result;}}/>):ringing?<button data-guide="accept" className="handset answer" title="Принять звонок" aria-label="Принять звонок" disabled={!owner||busy} onClick={()=>{onOpen();cmd('accept_call');}}><Phone size={24}/></button>:p.state.call==='connected'&&active&&<button data-guide="end-call" className="handset hangup" title="Завершить разговор" aria-label="Завершить разговор" disabled={busy} onClick={()=>cmd('end_call')}><PhoneOff size={24}/></button>}
  </div>
  {!dds&&p.state.call==='connected'&&active&&<><LiveVoice key={p.id} p={p} onUpdate={onUpdate}/><details className="question-list"><summary>Готовые вопросы</summary><div>{p.task.questions.map((q:Obj)=><button key={q.id} data-question={q.id} disabled={busy} onClick={()=>cmd('question',{id:q.id})}>{q.question}</button>)}</div></details></>}

  <div className="phone-audio-replies">{messages.filter((m:Obj)=>m.audio).slice(-1).map((m:Obj)=><BrigadeAudio key={m.event_id||m.at||m.audio} id={m.audio} playKey={`${p.id}:${m.event_id||m.at||m.audio}`} autoPlay={owner&&!done&&(!dds||m.direction==='incoming')} hidden beforePlay={async player=>{engine.current?.attach(player);}} onError={message=>{setAudioError(message);if(m.direction==='incoming')ended();}} onPlaying={m.direction==='incoming'?()=>{setIncomingPlaying(true);setCallEnded(false);}:undefined} onEnded={()=>{engine.current?.replyEnded();if(m.direction==='incoming')ended();}}/>)}</div>
 </section>;
}
