import React,{useEffect,useState} from 'react';
import {Phone,PhoneOff,MessageSquare} from 'lucide-react';
import {Obj} from './shared';
import {BrigadeAudio,DDSVoiceCall,LiveVoice,useVoiceChat} from './voice';
import {AIQuestion,AIContact} from './ai';

/** The handset stays visible; long conversations  open above it. */
export function PhoneDock({p,owner,busy,contactId,setContactId,contactText,setContactText,cmd,onUpdate,onOpen}:{p:Obj,owner:boolean,busy:boolean,contactId:string,setContactId:(s:string)=>void,contactText:string,setContactText:(s:string)=>void,cmd:(type:string,payload?:Obj)=>Promise<any>,onUpdate:(p:Obj)=>void,onOpen:()=>void}){
 const [incomingPlaying,setIncomingPlaying]=useState(false),[callEnded,setCallEnded]=useState(false);
 const [history,setHistory]=useState(false),[chat,setChat]=useState(false);
 const allowChat=useVoiceChat(),dds=p.task.mode==='dds',done=['completed','aborted'].includes(p.status),active=owner&&!done&&p.status!=='paused',incoming=p.state.incoming_calls||[];
 const messages=dds?p.state.messages:p.state.dialogue,contact=p.task.contacts?.find((c:Obj)=>c.id===contactId);
 useEffect(()=>{setCallEnded(false);},[messages.length]);
 function ended(){
  setIncomingPlaying(false);setCallEnded(true);
  try{const ctx=new AudioContext();void ctx.resume();for(let i=0;i<3;i++){const o=ctx.createOscillator(),g=ctx.createGain();o.frequency.value=425;const t=ctx.currentTime+i*.24;g.gain.setValueAtTime(.04,t);g.gain.setValueAtTime(0,t+.12);o.connect(g);g.connect(ctx.destination);o.start(t);o.stop(t+.13);}setTimeout(()=>void ctx.close(),900);}catch{}
 }
 const ringing=dds?incoming.length>0:p.state.call==='ringing';
 useEffect(()=>{if(!ringing||!owner)return;let ctx:AudioContext|undefined;
  const ring=()=>{try{
   ctx??=new AudioContext();if(ctx.state==='suspended')void ctx.resume();
   // Two bell bursts with a fast alternating pitch and a decaying envelope.
   for(const burst of [0,.7])for(let n=0;n<6;n++){
    const start=ctx.currentTime+burst+n*.075,o=ctx.createOscillator(),g=ctx.createGain();
    o.type='triangle';o.frequency.value=n%2?1480:1100;
    g.gain.setValueAtTime(0,start);g.gain.linearRampToValueAtTime(.08,start+.006);g.gain.exponentialRampToValueAtTime(.001,start+.07);
    o.connect(g);g.connect(ctx.destination);o.start(start);o.stop(start+.075);
   }
  }catch{}};
  ring();const t=setInterval(ring,3000);return()=>{clearInterval(t);ctx?.close();};
 },[ringing,owner]);
 return <section data-guide="phone" className={"phone-dock"+(ringing?" is-ringing":"")} aria-label="Учебная связь">
  <div className="phone-dock-tools"><button title="История связи" onClick={()=>{setHistory(!history);onOpen();}}>История связи</button>{allowChat&&<button aria-pressed={chat} onClick={()=>{setChat(!chat);onOpen();}}><MessageSquare size={14}/> Использовать чат</button>}</div>
  {(history||chat)&&<div className="phone-dock-popover"><button onClick={()=>{setHistory(false);setChat(false);}}>Закрыть {chat?'чат':'историю'}</button><div className="phone-transcript">{messages.map((m:Obj,i:number)=><div key={i}><small>{m.who}</small><p>{m.text||m.message}</p></div>)}{!messages.length&&<p>Разговор ещё не начат.</p>}</div>{chat&&allowChat&&active&&(dds?<><textarea aria-label="Сообщение абоненту" value={contactText} onChange={e=>setContactText(e.target.value)}/><button data-guide="contact" disabled={busy||!contactId||contactText.trim().length<3} onClick={()=>cmd('contact',{id:contactId,text:contactText})}>Связаться и передать</button>{contactId&&<AIContact p={p} contactId={contactId} text={contactText} onUpdate={onUpdate}/>}</>:p.state.call==='connected'&&<AIQuestion p={p} onUpdate={onUpdate} textOnly/>)}</div>}
  <div className="phone-dock-line">{(!dds||ringing)&&<div><b>{ringing?(dds?incoming[0].who:'Входящий вызов'):dds?(contact?.name||'Бригада / служба'):p.state.call==='connected'?'Заявитель':'Разговор завершён'}</b><small>{dds?contact?.phone:p.task.phone}</small></div>}
   {dds?(ringing?<button data-guide="accept" className="handset answer" title="Принять звонок" aria-label="Принять звонок" disabled={!active||busy} onClick={()=>{onOpen();cmd('accept_dds_call',{id:incoming[0].id});}}><Phone size={24}/></button>:active&&<DDSVoiceCall incomingState={incomingPlaying?'Бригада сообщает. Слушайте…':callEnded?'Абонент завершил звонок':undefined} disabled={busy||incomingPlaying} contacts={p.task.contacts||[]} service={p.task.own_service} textOnly={chat&&allowChat} contactId={contactId} onSelect={id=>{setCallEnded(false);setContactId(id);onOpen();}} onSend={async(text,id)=>{setContactText(text);const result=await cmd('contact',{id,text});if(!result)throw Error('Не удалось передать сообщение. Проверьте связь и повторите звонок.');}}/>):ringing?<button data-guide="accept" className="handset answer" title="Принять звонок" aria-label="Принять звонок" disabled={!owner||busy} onClick={()=>{onOpen();cmd('accept_call');}}><Phone size={24}/></button>:p.state.call==='connected'&&active&&<button data-guide="end-call" className="handset hangup" title="Завершить разговор" aria-label="Завершить разговор" disabled={busy} onClick={()=>cmd('end_call')}><PhoneOff size={24}/></button>}
  </div>
  {!dds&&p.state.call==='connected'&&active&&<><LiveVoice key={p.id} p={p} onUpdate={onUpdate}/><details className="question-list"><summary>Готовые вопросы</summary><div>{p.task.questions.map((q:Obj)=><button key={q.id} data-question={q.id} disabled={busy} onClick={()=>cmd('question',{id:q.id})}>{q.question}</button>)}</div></details></>}

  <div className="phone-audio-replies">{messages.filter((m:Obj)=>m.audio).slice(-1).map((m:Obj)=><BrigadeAudio key={m.event_id||m.at||m.audio} id={m.audio} playKey={`${p.id}:${m.event_id||m.at||m.audio}`} autoPlay hidden onPlaying={m.direction==='incoming'?()=>{setIncomingPlaying(true);setCallEnded(false);}:undefined} onEnded={m.direction==='incoming'?ended:undefined}/>)}</div>
 </section>;
}
