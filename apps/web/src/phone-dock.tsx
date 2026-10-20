import {AvayaPhone} from './avaya-phone';
import React,{useEffect,useState,useRef,useMemo} from 'react';
import {Phone,PhoneOff,MessageSquare,X} from 'lucide-react';
import {Obj,api,uuid} from './shared';
import {CallAudioEngine} from './call-audio';
import {BrigadeAudio,DDSVoiceCall,LiveVoice,useVoiceChat} from './voice';
import {AIQuestion,AIContact} from './ai';

/** The handset stays visible; long conversations  open above it. */
export function PhoneDock({p,owner,busy,contactId,setContactId,contactText,setContactText,cmd,onUpdate,onOpen}:{p:Obj,owner:boolean,busy:boolean,contactId:string,setContactId:(s:string)=>void,contactText:string,setContactText:(s:string)=>void,cmd:(type:string,payload?:Obj)=>Promise<any>,onUpdate:(p:Obj)=>void,onOpen:()=>void}){
 const engine=useMemo(()=>({current:new CallAudioEngine()}),[p.id]);
 const session=useRef(uuid()),line=useRef(false),cooldown=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
 const [outgoing,setOutgoing]=useState(false),[cooling,setCooling]=useState(false),[audioError,setAudioError]=useState('');
 useEffect(()=>{const release=()=>{if(!line.current)return;line.current=false;engine.current?.stop();void fetch('/api/call-audio/attempts/'+p.id+'/line',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json','X-Requested-With':'Training112','X-Workstation':localStorage.getItem('training112:station-token')||''},body:JSON.stringify({session:session.current,active:false})}).catch(()=>{});};window.addEventListener('pagehide',release);return()=>window.removeEventListener('pagehide',release);},[p.id]);
 async function startLine(){session.current=uuid();line.current=true;setOutgoing(true);try{await api('/call-audio/attempts/'+p.id+'/line','POST',{session:session.current,active:true});}catch(e){line.current=false;setOutgoing(false);throw e;}}
 function endLine(){setIncomingReady(undefined);setIncomingPlaying(false);setCallEnded(true);if(!line.current)return;line.current=false;setOutgoing(false);setCooling(true);void api('/call-audio/attempts/'+p.id+'/line','POST',{session:session.current,active:false}).catch(e=>setAudioError(e.message));clearTimeout(cooldown.current);cooldown.current=setTimeout(()=>setCooling(false),2500);}
 useEffect(()=>{const timer=setInterval(()=>{if(line.current)void api('/call-audio/attempts/'+p.id+'/line','POST',{session:session.current,active:true}).catch(e=>setAudioError(e.message));},20000);return()=>{clearInterval(timer);clearTimeout(cooldown.current);engine.current?.dispose();if(line.current)void api('/call-audio/attempts/'+p.id+'/line','POST',{session:session.current,active:false}).catch(()=>{});};},[p.id]);
 const [incomingPlaying,setIncomingPlaying]=useState(false),[callEnded,setCallEnded]=useState(false),[incomingReady,setIncomingReady]=useState<string>();
 const [phoneConnected,setPhoneConnected]=useState(false);
 const [history,setHistory]=useState(false),[chat,setChat]=useState(false),[liveSpeech,setLiveSpeech]=useState('');
 const transcript=useRef<HTMLDivElement>(null);
 const textOnly=!!p.state.text_only,allowChat=useVoiceChat()||textOnly,dds=p.task.mode==='dds',done=['completed','aborted'].includes(p.status),active=owner&&!done&&p.status!=='paused',incoming=p.state.incoming_calls||[];
 const messages=dds?p.state.messages:p.state.dialogue,contact=p.task.contacts?.find((c:Obj)=>c.id===contactId);
 useEffect(()=>{if(dds&&phoneConnected&&messages.length)setHistory(true);},[dds,messages.length,phoneConnected]);
 useEffect(()=>{const view=transcript.current;if(view)view.scrollTop=view.scrollHeight;},[messages.length,messages.at(-1)?.text,messages.at(-1)?.message,liveSpeech,history,chat]);
 useEffect(()=>{setLiveSpeech('');},[p.id]);
 useEffect(()=>{setCallEnded(false);},[messages.length]);
 useEffect(()=>{if(!active&&line.current){engine.current?.hangup();endLine();}},[active]);
 function ended(){
  setIncomingPlaying(false);setCallEnded(true);engine.current?.hangup();endLine();
 }
 const ringing=dds?incoming.length>0&&!outgoing&&!incomingPlaying&&!cooling:p.state.call==='ringing';
 useEffect(()=>{if(dds||!ringing||!owner)return;let live=true;
  engine.current!.prepare(dds?incoming[0]?.call_audio:{}).then(()=>{if(live)return engine.current!.signal('ring',true);}).catch(e=>{if(live)setAudioError(e.message);});
  return()=>{live=false;engine.current?.stop();};
 },[ringing,owner]);
 async function accept(){
  onOpen();setAudioError('');
  if(textOnly){const result=await cmd('accept_dds_call',{id:incoming[0].id});if(result){setContactId(incoming[0].contact_id||contactId);setCallEnded(false);setHistory(true);}return;}
  try{await Promise.all([engine.current?.unlock(),startLine()]);engine.current?.stop();await engine.current?.connect(incoming[0].call_audio);setIncomingPlaying(true);const result=await cmd('accept_dds_call',{id:incoming[0].id});if(!result)throw Error('Не удалось принять звонок');if(!result.state?.messages?.filter((m:Obj)=>m.direction==='incoming').at(-1)?.audio){continueIncoming(result.state.messages.at(-1));setHistory(true);}}
  catch(e:any){setAudioError(e.message);ended();}
 }
 async function sendContact(text:string,id:string){
  const latest=await api('/attempts/'+p.id);
  const result=await api('/ai/attempts/'+p.id+'/contact','POST',{text,contact_id:id,revision:latest.revision,command_id:uuid(),...(line.current?{session:session.current}:{})});onUpdate(result);return result;
 }
 function continueIncoming(m:Obj){setIncomingPlaying(false);if(!active||!m.contact_id||!p.task.contacts?.some((c:Obj)=>c.id===m.contact_id)){ended();return;}setContactId(m.contact_id);setIncomingReady(String(m.event_id));}
 return <section data-guide="phone" className={"phone-dock"+(ringing?" is-ringing":"")} aria-label="Учебная связь">
  {audioError&&<p role="alert">{audioError}</p>}{textOnly&&<p className="phone-text-only">Без звука: сообщения — текстом, связь через чат.</p>}<div className="phone-dock-tools"><button title="История связи" onClick={()=>{setHistory(!history);onOpen();}}>Расшифровка</button>{allowChat&&<button aria-pressed={chat} onClick={()=>{setChat(!chat);onOpen();}}><MessageSquare size={14}/> Использовать чат</button>}</div>
  {(history||chat)&&<div className="phone-dock-popover" role="dialog" aria-label={chat?'Чат':'Расшифровка разговора'}><header><strong>{chat?'Чат':'Расшифровка разговора'}</strong><button aria-label="Закрыть расшифровку" title="Закрыть" onClick={()=>{setHistory(false);setChat(false);}}><X size={16}/></button></header><div className="phone-transcript" ref={transcript}>{messages.map((m:Obj,i:number)=><div key={i}><small>{m.who}</small><p>{m.text||m.message}</p></div>)}{liveSpeech&&!messages.some((m:Obj)=>(m.text||m.message)===liveSpeech)&&<div><small>Вы · распознано</small><p>{liveSpeech}</p></div>}{!messages.length&&!liveSpeech&&<p>Разговор ещё не начат.</p>}</div>{chat&&allowChat&&active&&(dds?<><textarea aria-label="Сообщение абоненту" value={contactText} onChange={e=>setContactText(e.target.value)}/><button data-guide="contact" disabled={busy||!contactId||contactText.trim().length<3} onClick={()=>void sendContact(contactText,contactId).catch(e=>setAudioError(e.message))}>Связаться и передать</button>{contactId&&<AIContact p={p} contactId={contactId} text={contactText} onUpdate={onUpdate}/>}</>:p.state.call==='connected'&&<AIQuestion p={p} onUpdate={onUpdate} textOnly/>)}</div>}
  {dds?<AvayaPhone key={p.id} onCallStart={()=>setPhoneConnected(true)} onCallEnd={()=>{setPhoneConnected(false);setHistory(false);setChat(false);setLiveSpeech('');}} onTranscript={text=>{setLiveSpeech(text);setHistory(true);}} p={p} active={active} busy={busy} textOnly={textOnly||chat&&allowChat} onSelect={id=>{setContactId(id);if(textOnly)setChat(true);onOpen();}} onUpdate={onUpdate} cmd={cmd} onOpen={onOpen}/>:<div className="phone-dock-line"><div><b>{ringing?'Входящий вызов':p.state.call==='connected'?'Заявитель':'Разговор завершён'}</b><small>{p.task.phone}</small></div>{ringing?<button data-guide="accept" className="handset answer" title="Принять звонок" aria-label="Принять звонок" disabled={!owner||busy} onClick={()=>{onOpen();cmd('accept_call');}}><Phone size={24}/></button>:p.state.call==='connected'&&active&&<button data-guide="end-call" className="handset hangup" title="Завершить разговор" aria-label="Завершить разговор" disabled={busy} onClick={()=>cmd('end_call')}><PhoneOff size={24}/></button>}</div>}


  {!dds&&p.state.call==='connected'&&active&&<><LiveVoice key={p.id} p={p} onUpdate={onUpdate}/><details className="question-list"><summary>Готовые вопросы</summary><div>{p.task.questions.map((q:Obj)=><button key={q.id} data-question={q.id} disabled={busy} onClick={()=>cmd('question',{id:q.id})}>{q.question}</button>)}</div></details></>}

  <div className="phone-audio-replies">{(!dds?messages:[]).slice(-1).filter((m:Obj)=>m.audio).map((m:Obj)=><BrigadeAudio key={m.event_id||m.at||m.audio} id={m.audio} playKey={`${p.id}:${m.event_id||m.at||m.audio}`} autoPlay={owner&&!done&&p.status!=='paused'&&(!dds||m.direction==='incoming')} hidden beforePlay={async player=>{engine.current?.attach(player);}} onError={message=>{setAudioError(message);if(m.direction==='incoming')ended();}} onPlaying={m.direction==='incoming'?()=>{setIncomingPlaying(true);setCallEnded(false);}:undefined} onEnded={async()=>{await engine.current?.replyEnded();if(m.direction==='incoming')continueIncoming(m);}}/>)}</div>
 </section>;
}
