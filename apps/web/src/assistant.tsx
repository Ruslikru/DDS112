import {selectedMicrophone,selectMicrophone,MICROPHONE_CHANGED} from './microphone-preference';
import React,{useContext,useEffect,useRef,useState} from 'react';
import {useLocation,useNavigate} from 'react-router-dom';
import {Sparkles,Send,Mic,MicOff,History,Trash2} from 'lucide-react';
import {api,UserContext,type Obj} from './shared';
import {ArmDialog} from './arm-ui';
import {record,hasVoiceBridge,serverTranscribe} from './voice';
import {AssistantMicrophoneSettings} from './assistant-microphone-settings';

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
const HOLD_HINT='Удерживайте микрофон или Ctrl+Space и говорите. Отпустите, и фраза отправится.';
/** Below this input level (RMS) the whole recording counts as silence: the microphone gave no sound. */
const SILENT_LEVEL=0.004;
const SILENT_HINT='Микрофон не передал звук. Проверьте, что он включён и не заглушён, или выберите другой микрофон через шестерёнку вверху ассистента.';

/** Lines like «Страницы: …» get a bold label; the rest of the text is shown as written. */
function Text({text}:{text:string}){
 return <p>{text.split('\n').map((line,i)=>{const m=/^([А-ЯЁ][а-яё]+):\s(.+)$/.exec(line);return <React.Fragment key={i}>{i>0&&<br/>}{m?<><b>{m[1]}:</b> {m[2]}</>:line}</React.Fragment>;})}</p>;
}
/** Spoken answers to an open confirmation card are handled on the client, without the server. JS \b ignores Cyrillic, hence the lookahead. */
const VOICE_YES=/^(создай|создать|отправь|отправить|опубликуй|да|ага|выполняй|выполни|выполнить|подтверждаю|подтверди|давай|сохрани|сохранить|ок|окей|хорошо)(?=[\s.,!?]|$)/i;
const VOICE_NO=/^(нет|отмена|отмени|отменить|не надо|не нужно|стоп|не выполняй)(?=[\s.,!?]|$)/i;
const HINTS=['Что умеешь?','Журнал','Проверить работы','Кто сейчас в классе?','Новый билет'];
const DIALOG_INTENTS=['create_ticket','edit_ticket','save_ticket','create_group','open_group','create_question','edit_question','create_student','assign_ticket','publish_ticket'];
const HISTORY_KEY='training112:assistant-history';
const HISTORY_SIZE=10;
const WELCOME:Message={who:'assistant',text:'Напишите или скажите команду: «открой журнал», «где сидит Кузнецов», «создай билет про пожар на 3 звезды». Переходы выполняются сразу, билеты создаются и меняются только после вашего подтверждения.'};
/** Last typed commands, newest first; kept per browser only as a convenience. */
function readHistory():string[]{try{const list=JSON.parse(localStorage.getItem(HISTORY_KEY)||'[]');return Array.isArray(list)?list.filter(x=>typeof x==='string').slice(0,HISTORY_SIZE):[];}catch{return [];}}
function remember(list:string[],phrase:string):string[]{const next=[phrase,...list.filter(x=>x!==phrase)].slice(0,HISTORY_SIZE);try{localStorage.setItem(HISTORY_KEY,JSON.stringify(next));}catch{}return next;}
const allowed=(role:string)=>role==='teacher';
/** What the ticket slot form has collected so far, shown above the next question. */
function collected(slots:Obj):string[]{
 const out:string[]=[];
 if(slots.own_service)out.push(String(slots.own_service));
 if(slots.incident_type)out.push(String(slots.incident_type));
 if(slots.mode)out.push(slots.mode==='dds'?'диспетчер ДДС':'оператор 112');
 if(slots.difficulty)out.push('★'.repeat(Number(slots.difficulty))+'☆'.repeat(5-Number(slots.difficulty)));
 if(slots.victims==='no')out.push('без пострадавших');
 else if(slots.victims==='unknown')out.push('пострадавшие неизвестны');
 else if(slots.victims==='yes')out.push(slots.victims_count?`пострадавших: ${slots.victims_count}`:'есть пострадавшие');
 if(Array.isArray(slots.traits)&&slots.traits.length)out.push(slots.traits.join(', '));
 if(slots.address)out.push(String(slots.address));
 return out;
}

type Confirm={intent:string,slots:Obj,token:string};
type Link={label:string,to:string};
/** `done` marks a card (question, candidates, confirmation) that has been answered; cards that are no longer last are shown muted. */
type Message={who:'user'|'assistant',text:string,candidates?:Obj[],options?:{slot:string,options:Obj[]},confirm?:Confirm,links?:Link[],error?:boolean,retry?:{confirm:Confirm}|{origin:string},collected?:string[],done?:string};
const isCard=(m:Message)=>!!(m.candidates||m.options||m.confirm||m.retry);
/** The open slot form: intent, accumulated slots and the question waiting for an answer. */
type Dialog={intent:string,slots:Obj,missing?:string}|null;
type Store={messages:Message[],setMessages:React.Dispatch<React.SetStateAction<Message[]>>,dialog:Dialog,setDialog:(d:Dialog)=>void,origin:React.MutableRefObject<string>,creation:React.MutableRefObject<Confirm|null>,autoRecord:React.MutableRefObject<boolean>,holding:React.MutableRefObject<boolean>};
type VoiceSource='checking'|'bridge'|'server'|'none';

/** Header button: the window itself is mounted once in App, so the shortcut is registered once. */
export function AssistantButton(){
 const u=useContext(UserContext);
 if(!allowed(u.role))return null;
 return <button type="button" className="assistant-button" title="Ассистент преподавателя (Ctrl+Space)" aria-label="Открыть AI ассистента" onClick={()=>window.dispatchEvent(new Event(TOGGLE))}><Sparkles size={24}/><span>AI</span></button>;
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
 /** Input level while recording and the loudest moment of the last recording (to tell a silent microphone from unclear speech). */
 const [level,setLevel]=useState(0),peak=useRef(0);
 const [mic,setMic]=useState(selectedMicrophone);
 useEffect(()=>{const changed=()=>setMic(selectedMicrophone());window.addEventListener(MICROPHONE_CHANGED,changed);return()=>window.removeEventListener(MICROPHONE_CHANGED,changed);},[]);
 const chooseMic=(id:string)=>{setMic(id);selectMicrophone(id);};
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
 /** The panel has no shade, so the wheel over it should still scroll the page unless the log, the history or the field itself can scroll. */
 useEffect(()=>{
  const panel=log.current?.closest('.arm-dialog') as HTMLElement|null;
  if(!panel)return;
  const scrollable=(el:HTMLElement|null,stop:HTMLElement|null,delta:number):HTMLElement|null=>{
   for(let node=el;node&&node!==stop;node=node.parentElement){
    const style=getComputedStyle(node);
    if(/(auto|scroll)/.test(style.overflowY)&&node.scrollHeight>node.clientHeight+1){
     const atTop=node.scrollTop<=0,atBottom=node.scrollTop+node.clientHeight>=node.scrollHeight-1;
     if((delta<0&&!atTop)||(delta>0&&!atBottom))return node;
    }
   }
   return null;
  };
  const wheel=(e:WheelEvent)=>{
   if(!e.deltaY||e.ctrlKey)return;
   if(scrollable(e.target as HTMLElement,panel.parentElement,e.deltaY))return;
   const below=document.elementsFromPoint(e.clientX,e.clientY).find(el=>!panel.contains(el)) as HTMLElement|undefined;
   const target=scrollable(below||null,null,e.deltaY)||document.scrollingElement as HTMLElement|null;
   if(!target)return;
   e.preventDefault();target.scrollBy({top:e.deltaY});
  };
  panel.addEventListener('wheel',wheel,{passive:false});
  return()=>panel.removeEventListener('wheel',wheel);
 },[]);
 useEffect(()=>{log.current?.scrollTo({top:log.current.scrollHeight});},[messages,busy]);
 const push=(message:Message)=>setMessages(list=>[...list,message]);
 /** Marks the pending card (the last message with buttons) as answered, so it is shown muted with the outcome. */
 const settle=(outcome:string)=>setMessages(list=>{const i=list.length-1;return i>=0&&isCard(list[i])&&!list[i].done?[...list.slice(0,i),{...list[i],done:outcome}]:list;});
 const focus=()=>setTimeout(()=>input.current?.focus(),0);
 /** Navigation keeps the panel open: the page changes behind it and the answer stays in the log. */
 const go=(to:string)=>{navigate(to);focus();};
 const finish=(action:Obj|undefined)=>{
  if(action?.kind==='navigate'){setDialog(null);go(action.to);return true;}
  if(action?.kind==='close'){onClose();return true;}
  if(action?.kind==='logout'){api('/logout','POST').finally(()=>{window.dispatchEvent(new Event('auth-expired'));navigate('/');});onClose();return true;}
  return false;
 };
 /** Sends a phrase; `slots` carries an answer given with a button, `shown` is what the log displays. */
 const send=async(command:string,slots?:Obj,shown?:string):Promise<Obj|null>=>{
  const phrase=command.trim();
  if(!phrase&&!slots)return null;
  const pending=latest.current.messages.at(-1)?.confirm;
  if(/^(?:да[, ]+)?подтвер(?:ди|дить|ждаю)(?:\s+оценку)?[.!]?$/i.test(phrase)&&document.querySelector('[data-review-open]')){window.dispatchEvent(new CustomEvent('training112:review-command',{detail:{command:/^да/i.test(phrase)?'confirm':'request'}}));return null;}
  if(pending&&VOICE_YES.test(phrase)&&!slots){run(pending,phrase);return null;}
  if(dialog?.intent==='save_ticket'&&pending?.intent==='save_ticket'&&(/^(?:сохрани|сохранить)$/i.test(phrase)||/(?:открой|открыть|покажи|сохрани).*редактор/i.test(phrase))){
   run(pending,'Сохранить и открыть');return null;
  }
  if(dialog&&!slots)settle(dialog.missing?'отвечено':'уточнено');
  push({who:'user',text:shown||phrase});setText('');setCursor(-1);setBusy('ask');
  if(!slots&&phrase&&!dialog?.missing)setHistory(list=>remember(list,phrase));
  try{
   const body:Obj={text:phrase,context:{page:location.pathname,version_id:sessionStorage.getItem('assistant:last-version')?Number(sessionStorage.getItem('assistant:last-version')):undefined}};
   if(dialog)body.dialog={intent:dialog.intent,slots:{...dialog.slots,...(slots||{}),...(slots?{answer_slot:Object.keys(slots)[0]}:dialog.missing?{answer_slot:dialog.missing}:{})}};
   const r:Obj=await api('/assistant/interpret','POST',body);
   const question=r.missing?.[0];
   const gathered=r.intent==='create_ticket'&&(question||r.candidates?.length)?collected(r.slots||{}):[];
   push({who:'assistant',text:r.preview||'Готово.',candidates:r.candidates?.length?r.candidates:undefined,options:question?.options?.length?{slot:question.slot,options:question.options}:undefined,confirm:r.confirm_required?{intent:r.intent,slots:r.slots,token:r.confirm_token}:undefined,links:r.links?.length?r.links:undefined,collected:gathered.length?gathered:undefined});
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
  if(/^(?:да[, ]+)?подтвер(?:ди|дить|ждаю)(?:\s+оценку)?[.!]?$/i.test(phrase)&&document.querySelector('[data-review-open]')){await send(phrase);return;}
  const {messages:log,dialog:form}=latest.current;
  const card=log[log.length-1]?.confirm;
  if(card&&form){
   if(VOICE_YES.test(phrase)||card.intent==='save_ticket'&&/(?:открой|покажи).*редактор/i.test(phrase)){run(card,card.intent==='save_ticket'?'Сохранить и открыть':'Выполнить');return;}
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
  setHeard('');setListening('Включаем микрофон…');peak.current=0;setLevel(0);
  const stop=await record(spoken=>{stopRecording.current=undefined;setRecording(false);setLevel(0);heardText(spoken);},problem=>{
   stopRecording.current=undefined;setRecording(false);setLevel(0);setListening('');
   // «Речь не распознана» after a recording with no input level means the microphone gave nothing, not that the speech was unclear.
   push({who:'assistant',text:/не распознана/i.test(problem)&&peak.current<SILENT_LEVEL?SILENT_HINT:problem,error:true});
  },voice==='server'?serverTranscribe:undefined,{deviceId:mic||undefined,onLevel:value=>{if(value>peak.current)peak.current=value;setLevel(value);}});
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
 const micDisabled=!recording&&(!!busy||voice==='none'||voice==='checking');
 const micTitle=voice==='none'?VOICE_HINT:voice==='checking'?'Проверяем голосовой модуль…':recording?'Отпустите, чтобы отправить':'Удерживайте и говорите (Ctrl+Space)'+(voice==='server'?'. Распознавание на сервере':'');
 /** The line under the log always says what the microphone will do, not only while it is busy. */
 const voiceStatus=listening||(heard?'Распознано: '+heard:voice==='none'?VOICE_HINT:voice==='checking'?'Проверяем голосовой модуль…':HOLD_HINT);
 const press=(e:React.PointerEvent<HTMLButtonElement>)=>{if(micDisabled||e.button!==0)return;e.preventDefault();try{e.currentTarget.setPointerCapture(e.pointerId);}catch{}holding.current=true;startRecording();};
 const release=()=>{if(holding.current||stopRecording.current)finishRecording();};
 const micKey=(e:React.KeyboardEvent<HTMLButtonElement>)=>{if(e.key!==' '&&e.key!=='Enter')return;e.preventDefault();if(e.type==='keydown'){if(e.repeat||holding.current||micDisabled)return;holding.current=true;startRecording();}else release();};
 /** Runs a confirmed command. A new ticket answers with its draft and a second confirmation («Сохранить»). */
 const run=async(confirm:Confirm,label='Выполнить')=>{
  if(busy)return;
  settle('подтверждено: '+label.toLowerCase());
  push({who:'user',text:label});setBusy(confirm.intent==='create_ticket'?'generate':'run');
  if(confirm.intent==='create_ticket')creation.current=confirm;
  try{
   const r:Obj=await api('/assistant/execute','POST',{intent:confirm.intent,slots:confirm.slots,confirm_token:confirm.token});
   if(r.slots?.version_id)sessionStorage.setItem('assistant:last-version',String(r.slots.version_id));
   if(r.action?.to?.match(/^\/tickets\/\d+$/))sessionStorage.setItem('assistant:last-version',r.action.to.split('/').at(-1));
   const next=r.confirm_required?{intent:r.intent,slots:r.slots,token:r.confirm_token}:undefined;
   push({who:'assistant',text:r.preview||'Выполнено.',confirm:next,links:r.links?.length?r.links:undefined});
   if(next)setDialog({intent:r.intent,slots:r.slots});
   else{setDialog(null);creation.current=null;finish(r.action);}
  }catch(e:any){
   // 409: the token or draft has expired; other errors can be retried with the same confirmation.
   const expired=e.status===409;
   push({who:'assistant',text:e.message,error:true,retry:expired?{origin:origin.current}:{confirm}});
  }
  finally{setBusy('');focus();}
 };
 const recompose=(phrase:string)=>{settle('составить заново');setDialog(null);if(phrase)send(phrase);else focus();};
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
 const choose=(candidate:Obj)=>{if(busy)return;settle('выбрано: '+candidate.label);send(candidate.label,{[candidate.slot||'student_id']:candidate.id},candidate.label);};
 const pick=(slot:string,option:Obj)=>{if(busy)return;settle('выбрано: '+option.label);send(option.label,{[slot]:option.value},option.label);};
 const cancel=()=>{settle('отменено');setDialog(null);creation.current=null;push({who:'assistant',text:'Отменено. Ничего не изменено.'});focus();};
 const clear=()=>{setMessages([WELCOME]);setDialog(null);creation.current=null;focus();};
 const adjust=()=>{settle('уточнение');push({who:'assistant',text:dialog?.intent==='create_group'?'Напишите новое название или состав группы.':dialog?.intent?.includes('question')?'Напишите, какой текст вопроса, ответа или озвучки изменить.':'Напишите, что поменять: например «сложность 4» или «без пострадавших».'});focus();};
 const openWizard=(slots:Obj)=>{settle('открыто в мастере');setDialog(null);creation.current=null;navigate('/tickets',{state:{wizard:{own_service:slots.own_service,services:slots.services,incident_type:slots.incident_type,mode:slots.mode,difficulty_stars:slots.difficulty,victims_state:slots.victims,victims_count:slots.victims_count||1,traits:slots.traits||[]}}});focus();};
 const last=messages.length-1;
  const busyText=busy==='generate'?'Создаю черновик: собираю историю, звонки и проверочные факты. Обычно это занимает около минуты.':busy==='run'?'Сохраняю изменения…':'Разбираю команду…';
 const cancelButton=<button type="button" disabled={!!busy} onClick={cancel}>Отмена</button>;
 return <ArmDialog title="Ассистент" className="assistant-shade" modal={false} onClose={onClose} headerActions={<AssistantMicrophoneSettings value={mic} onChange={chooseMic} disabled={recording||!!stopRecording.current}/> }>
  <div className="assistant-log" ref={log} aria-live="polite">
   {messages.map((message,index)=>{
    const card=isCard(message),active=card&&index===last&&!message.done&&(!!dialog||!!message.retry);
    return <div key={index} className={'assistant-message '+message.who+(message.error?' error':'')+(card?' card':'')+(card&&!active?' settled':'')}>
    {message.collected&&<div className="assistant-collected" aria-label="Уже собрано">{message.collected.map(item=><span key={item}>{item}</span>)}</div>}
    <Text text={message.text}/>
    {message.links&&<div className="assistant-links">{message.links.map(link=><button type="button" key={link.to+link.label} disabled={!!busy} onClick={()=>go(link.to)}>{link.label} →</button>)}</div>}
    {message.candidates&&active&&<div className="assistant-candidates">{message.candidates.map((candidate:Obj)=><button type="button" key={candidate.id} disabled={!!busy} onClick={()=>choose(candidate)}>{candidate.label}</button>)}{cancelButton}</div>}
    {message.options&&active&&<div className="assistant-candidates">{message.options.options.map((option:Obj)=><button type="button" key={String(option.value)} disabled={!!busy} onClick={()=>pick(message.options!.slot,option)}>{option.label}</button>)}{cancelButton}</div>}
    {message.retry&&active&&<div className="assistant-confirm" role="group" aria-label="Повтор команды">
     {'confirm' in message.retry?<button type="button" className="primary" disabled={!!busy} onClick={()=>run((message.retry as {confirm:Confirm}).confirm,'Повторить')}>Повторить</button>
     :<button type="button" className="primary" disabled={!!busy} onClick={()=>recompose((message.retry as {origin:string}).origin)}>Составить заново</button>}
     {cancelButton}
    </div>}
    {message.confirm&&active&&(message.confirm.intent==='save_ticket'
     ?<div className="assistant-confirm" role="group" aria-label="Сохранение черновика">
       <button type="button" className="primary" disabled={!!busy} onClick={()=>run(message.confirm!,'Сохранить')}>Сохранить</button>
       {creation.current&&<button type="button" disabled={!!busy} onClick={()=>run(creation.current!,'Сгенерировать заново')}>Сгенерировать заново</button>}
       {cancelButton}
      </div>
     :<div className="assistant-confirm" role="group" aria-label="Подтверждение команды">
       <button type="button" className="primary" disabled={!!busy} onClick={()=>run(message.confirm!)}>Выполнить</button>
       <button type="button" disabled={!!busy} onClick={message.confirm.intent==='create_group'||message.confirm.intent.includes('question')?()=>recompose(origin.current):adjust}>{message.confirm.intent==='create_group'||message.confirm.intent.includes('question')?'Составить заново':'Изменить'}</button>
       {message.confirm.intent==='create_ticket'&&<button type="button" disabled={!!busy} onClick={()=>openWizard(message.confirm!.slots)}>Открыть в мастере</button>}
       {cancelButton}
      </div>)}
    {card&&!active&&<small className="assistant-done">{message.done||'без ответа'}</small>}
   </div>;})}
    {busy&&<div className="assistant-message assistant busy" role="status"><p>{busyText}</p>{busy==='generate'&&<div className="assistant-progress" aria-label="Создание черновика выполняется"><span/></div>}</div>}
  </div>
  <div className="assistant-hints">
   {HINTS.map(hint=><button type="button" key={hint} disabled={!!busy} onClick={()=>send(hint)}>{hint}</button>)}
   {history.length>0&&<button type="button" className="assistant-tool" aria-expanded={historyOpen} title="История команд" onClick={()=>setHistoryOpen(v=>!v)}><History size={14}/><span>{history.length}</span></button>}
   {messages.length>1&&<button type="button" className="assistant-tool" disabled={!!busy} title="Очистить ленту" aria-label="Очистить ленту" onClick={clear}><Trash2 size={14}/></button>}
  </div>
  {historyOpen&&history.length>0&&<ul className="assistant-history" aria-label="История команд">{history.map(item=><li key={item}><button type="button" disabled={!!busy} title="Повторить команду" onClick={()=>{setHistoryOpen(false);send(item);}}>{item}</button></li>)}</ul>}
  <div className={'assistant-voice-status'+(listening||heard?' active':'')} role="status" aria-live="polite">
   {recording&&<span className="assistant-level" aria-hidden="true"><i style={{width:Math.min(100,Math.round(level*400))+'%'}}/></span>}
   {voiceStatus}
  </div>
  <form className="assistant-input" onSubmit={submit}>
   <button type="button" className={'voice-mic assistant-mic '+(recording?'recording':micDisabled?'waiting':'ready')} style={{['--level' as any]:Math.min(1,level*8)}} disabled={micDisabled} title={micTitle} aria-label={micTitle} aria-pressed={recording} onPointerDown={press} onPointerUp={release} onPointerCancel={release} onKeyDown={micKey} onKeyUp={micKey} onContextMenu={e=>e.preventDefault()}>{voice==='none'?<MicOff size={24}/>:<Mic size={24}/>}</button>
   <textarea ref={input} aria-label="Команда ассистенту" rows={2} value={text} maxLength={500} placeholder={dialog?.missing==='student'?'Фамилия или имя ученика':dialog?.missing?'Ответ на вопрос ассистента':dialog?'Что изменить в команде?':'Команда ассистенту. Enter отправит, стрелка вверх повторит прошлую'} onChange={e=>{setText(e.target.value);setCursor(-1);}} onKeyDown={keys} disabled={!!busy}/>
   <button type="submit" className="assistant-send" disabled={!!busy||!text.trim()} title="Отправить (Enter)" aria-label="Отправить"><Send size={20}/></button>
  </form>
 </ArmDialog>;
}
