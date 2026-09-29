import React,{useEffect,useRef,useState} from 'react';
import {api,Notice,Obj,uuid} from './shared';
import './voice.css';
import {Phone,PhoneOff,Mic,MicOff} from 'lucide-react';

const bridge=()=> (window as any).pywebview?.api;
const mobile=()=>/Android|iPhone|iPad|Mobile/i.test(navigator.userAgent);
function useNativeReady(){
 const [ready,setReady]=useState(!!bridge()?.voice_speak);
 useEffect(()=>{const update=()=>setReady(!!bridge()?.voice_speak);window.addEventListener('pywebviewready',update);const t=setInterval(update,300);return()=>{clearInterval(t);window.removeEventListener('pywebviewready',update);};},[]);return ready;
}
export function useVoiceChat(){
 const ready=useNativeReady(),[value,setValue]=useState(false);
 useEffect(()=>{let alive=true;const update=()=>{bridge()?.voice_status?.().then((v:Obj)=>{if(alive)setValue(v.settings?.live?.chat_enabled===true);}).catch(()=>{});};update();window.addEventListener('voice-chat-settings',update);return()=>{alive=false;window.removeEventListener('voice-chat-settings',update);};},[ready]);return value;
}
async function voiceBridge(){
 // The UI may arrive from a newer classroom server than the native client.
 for(let i=0;i<20&&!bridge()?.voice_transcribe;i++)await new Promise(r=>setTimeout(r,100));
 const native=bridge();
 if(!native?.voice_transcribe||!native?.voice_speak)throw Error('На этом ПК запущена старая версия приложения без голосового модуля. Откройте актуальную сборку на этом рабочем месте.');
 return native;
}
export function VoiceDraft({data}:{data:Obj}){
 const [jobs,setJobs]=useState<Obj[]>([]),[error,setError]=useState('');
 const signature=JSON.stringify(data);
 useEffect(()=>{let closed=false,timer:any;const start=setTimeout(async()=>{try{
   const prepared=await api('/voice/prepare','POST',JSON.parse(signature));
   const poll=async()=>{try{const list=await api('/voice/jobs','POST',{keys:prepared.keys});if(!closed){setJobs(list);timer=setTimeout(poll,3000);}}catch(e:any){if(!closed)setError(e.message);}};
   if(!closed){setError('');poll();}
 }catch(e:any){if(!closed)setError(e.message);}},2500);return()=>{closed=true;clearTimeout(start);clearTimeout(timer);};},[signature]);
 if(!jobs.length&&!error)return null;
 const pending=jobs.some(j=>['pending','running'].includes(j.status));
 return <aside className="voice-draft" aria-live="polite"><details><summary>{pending?'Идёт генерация звуков для сообщений руководителей бригад':'Звуки сообщений бригад'} · {jobs.filter(j=>j.status==='ready').length}/{jobs.length}</summary><Notice>{error}</Notice>{jobs.map(j=><div key={j.id}><p>{j.text}</p>{j.audio_id?<audio controls preload="none" src={'/api/media/'+j.audio_id}/>:<span>{j.status==='failed'?j.error:'Готовится…'}</span>}{j.status==='failed'&&<button onClick={async()=>{await api('/voice/jobs/'+j.id+'/retry','POST');setJobs(await api('/voice/jobs','POST',{keys:jobs.map(x=>x.id)}));setError('');}}>Повторить</button>}</div>)}</details></aside>;
}

async function record(onDone:(text:string)=>void,onError:(text:string)=>void){
 try{
  if(mobile()||!bridge())throw Error('Живой голос доступен в приложении Windows на этом ПК.');
  const native=await voiceBridge();
  // Older voice clients use WebView's own microphone permission prompt.
  if(typeof native.allow_microphone==='function')await native.allow_microphone();
  const stream=await navigator.mediaDevices.getUserMedia({audio:true});
  let recorder:MediaRecorder;try{recorder=new MediaRecorder(stream);}catch(e){stream.getTracks().forEach(t=>t.stop());throw e;}const chunks:BlobPart[]=[];
  recorder.ondataavailable=e=>chunks.push(e.data);
  recorder.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());try{const bytes=new Uint8Array(await new Blob(chunks).arrayBuffer());let raw='';bytes.forEach(b=>raw+=String.fromCharCode(b));const value=await bridge().voice_transcribe(btoa(raw));onDone(value.text+'');}catch(e:any){onError(e.message||String(e));}};
  recorder.start();const limit=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},15000);
  return ()=>{clearTimeout(limit);if(recorder.state==='recording')recorder.stop();};
 }catch(e:any){onError(e.message||String(e));return undefined;}
}

export function VoiceSettings({localOnly=false}:{localOnly?:boolean}){
 const nativeReady=useNativeReady();
 const chat=useVoiceChat();
 const [server,setServer]=useState<Obj>(),[local,setLocal]=useState<Obj>(),[error,setError]=useState(''),[result,setResult]=useState(''),[busy,setBusy]=useState(false);
 const stop=useRef<(()=>void)|undefined>(undefined),[recording,setRecording]=useState(false);
 useEffect(()=>{if(!localOnly)api('/voice/settings').then(setServer).catch(e=>setError(e.message));if(bridge()?.voice_status&&!mobile())bridge().voice_status().then(setLocal).catch((e:any)=>setError(String(e)));return()=>stop.current?.();},[nativeReady]);
 async function change(group:string,key:string,value:any){try{setBusy(true);if(group==='pre')setServer(await api('/voice/settings','POST',{pre:{[key]:value}}));else{await bridge().voice_settings({...local?.settings.live,[key]:value});setLocal(await bridge().voice_status());window.dispatchEvent(new Event('voice-chat-settings'));}}catch(e:any){setError(e.message||String(e));}finally{setBusy(false);}}
 return <section className="panel form-panel voice-settings"><h2 className="section-title-bar">Генерация звука</h2><Notice>{error}</Notice><label><input type="checkbox" checked={chat} disabled={busy||!local?.settings} onChange={e=>change('live','chat_enabled',e.target.checked)}/> Разрешить текстовый чат вместо микрофона на этом ПК</label>{(localOnly?['live']:['pre','live']).map(group=>{const source=group==='pre'?server:local,cfg=source?.settings?.[group];return <fieldset key={group}><legend>{group==='pre'?'Предгенерация для билетов · сервер':'Разговор 112 · этот рабочий ПК'}</legend>{group==='live'&&(mobile()||!bridge())?<p>{mobile()?'Генерация речи в реальном времени на мобильных устройствах не поддерживается':'Откройте приложение Windows для настройки голосового движка этого ПК.'}</p>:<><p>{source?.available?'Голосовой модуль установлен':source?.error||'Проверка голосового модуля…'}</p><div className="form-grid">{cfg&&Object.entries(cfg).filter(([key])=>key!=='chat_enabled').map(([key,value])=><label key={key}>{({llm:'Модель анализа',llm_device:'Анализ · устройство',tts:'Озвучка',tts_device:'Озвучка · устройство',stt:'Распознавание',stt_device:'Распознавание · устройство',fillers:'Готовые реплики ожидания',delay:'Пауза перед вставкой, сек.'} as Obj)[key]}{key==='fillers'?<input type="checkbox" checked={!!value} disabled={busy} onChange={e=>change(group,key,e.target.checked)}/>:key==='delay'?<input type="number" min="0.3" max="10" step="0.1" value={Number(value)} disabled={busy} onChange={e=>change(group,key,Number(e.target.value))}/>:<select value={String(value)} disabled={busy} onChange={e=>change(group,key,e.target.value)}>{(key.endsWith('device')?[['cpu','CPU'],['gpu','GPU · '+(key==='llm_device'?'Vulkan':'CUDA')]]:key==='llm'?[['models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf','Qwen3 4B Instruct · рекомендована'],['models/Qwen3-0.6B-Q4_K_M.gguf','Qwen3 0,6B · быстрее']]:key==='stt'?[['base','Whisper base · точнее'],['tiny','Whisper tiny · быстрее']]:[['silero','Silero v5 · быстро'],['qwen','Qwen3-TTS 1.7B · выразительнее']]).map(([id,label])=><option key={id} value={id} disabled={id==='gpu'&&!(key==='llm_device'?source?.llm_gpu:source?.gpu) || (key==='tts'||key==='stt')&&source?.models&&!source.models[id]}>{label}{(key==='tts'||key==='stt')&&source?.models&&!source.models[id]?' · не установлена':''}</option>)}</select>}</label>)}</div>{cfg?.tts==='qwen'&&group==='live'&&<p>Экспериментальный живой режим: ответ может готовиться заметно дольше Silero.</p>}{group==='live'&&<div className="voice-actions"><button disabled={busy&&!recording} onClick={async()=>{if(recording){stop.current?.();setRecording(false);return;}setBusy(true);setResult('Запись до 15 секунд. Нажмите ещё раз, чтобы закончить.');stop.current=await record(text=>{setResult('Распознано: '+text);setRecording(false);setBusy(false);},e=>{setError(e);setBusy(false);setRecording(false);});setRecording(!!stop.current);}}>{recording?'Закончить запись':'Проверить микрофон'}</button><button disabled={busy||!source?.available} onClick={async()=>{setBusy(true);try{const r=await bridge().voice_speak('Проверка звука. Бригада прибыла по указанному адресу.','male');setResult('Синтез: '+r.seconds+' с; запись: '+r.duration+' с.');new Audio(r.audio).play();}catch(e:any){setError(String(e));}finally{setBusy(false);}}}>Проверить озвучку</button><p aria-live="polite">{result}</p><small>Синхронизировано записей: {local?.sync?.ready||0}/{local?.sync?.total||0} {local?.sync?.error}</small></div>}</>}</fieldset>;})}</section>;
}

export function BrigadeAudio({id,autoPlay=false,playKey=id,hidden=false,onEnded,onPlaying}:{id:string,autoPlay?:boolean,playKey?:string,hidden?:boolean,onEnded?:()=>void,onPlaying?:()=>void}){
 const [source,setSource]=useState<{id:string,url:string}|null>(null);const ref=useRef<HTMLAudioElement>(null);
 const url=source?.id===id?source.url:undefined;
 useEffect(()=>{let closed=false;const player=ref.current;setSource(null);Promise.resolve(bridge()?.voice_cached?.(id)).catch(()=>null).then((cached:string)=>{if(!closed)setSource({id,url:cached||'/api/media/'+id});});return()=>{closed=true;player?.pause();};},[id]);
 useEffect(()=>{const key='voice-played:'+playKey;if(url&&autoPlay&&!sessionStorage.getItem(key)){document.querySelectorAll('audio').forEach(a=>{if(a!==ref.current)a.pause();});ref.current?.play().then(()=>sessionStorage.setItem(key,'1')).catch(()=>{});}},[url,autoPlay,playKey]);
 return <audio ref={ref} onEnded={onEnded} onPlaying={onPlaying} controls={!hidden} hidden={hidden} preload="none" src={url}/>;
}

function MicButton({recording,disabled,onClick}:{recording:boolean,disabled:boolean,onClick:()=>void}){
 const label=recording?'Закончить запись':disabled?'Дождитесь ответа':'Включить микрофон';
 return <button className={'voice-mic '+(recording?'recording':disabled?'waiting':'ready')} disabled={disabled} title={label} aria-label={label} aria-pressed={recording} onClick={onClick}>{recording?<Mic size={25}/>:disabled?<MicOff size={24}/>:<MicOff size={25}/>}</button>;
}
async function playReply(player:HTMLAudioElement){await new Promise<void>((resolve,reject)=>{player.onended=()=>resolve();player.onerror=()=>reject(Error('Не удалось воспроизвести звук.'));player.onpause=()=>resolve();player.play().catch(reject);});}

export function LiveVoice({p,onUpdate}:{p:Obj,onUpdate:(p:Obj)=>void}){
 const nativeReady=useNativeReady();
 const [busy,setBusy]=useState(false),[recording,setRecording]=useState(false),[error,setError]=useState(''),[text,setText]=useState(''),[speaking,setSpeaking]=useState(false),[replyUrl,setReplyUrl]=useState('');
 const stop=useRef<(()=>void)|undefined>(undefined),audio=useRef<HTMLAudioElement|null>(null),generation=useRef(0),spokenCount=useRef(0);
 useEffect(()=>()=>{generation.current++;stop.current?.();audio.current?.pause();bridge()?.voice_cancel?.()?.catch?.(()=>{});},[p.id,p.state.call]);
 useEffect(()=>{const count=p.state.dialogue?.length||0,key='voice-reply:'+p.id+':'+count;
  if(p.state.call!=='connected'||p.status!=='active'||!bridge()?.voice_speak||mobile()||spokenCount.current===count||sessionStorage.getItem(key))return;
  const line=p.state.dialogue?.at(-1);if(line?.who!=='Заявитель'||line.audio)return;
  let active=true;spokenCount.current=count;setSpeaking(true);setError('');
  bridge().voice_speak(line.text,p.state.voice_gender||'female').then(async(r:Obj)=>{if(active){setReplyUrl(r.audio);audio.current?.pause();audio.current=new Audio(r.audio);try{await playReply(audio.current);sessionStorage.setItem(key,'1');}catch{setError('Не удалось включить звук. Проверьте разрешение на воспроизведение и повторите вопрос.');}}}).catch((e:any)=>{if(active){spokenCount.current=0;setError(String(e));}}).finally(()=>{if(active)setSpeaking(false);});
  return()=>{active=false;};
 },[p.id,p.state.call,p.status,p.state.dialogue?.length,nativeReady]);
 if(mobile())return <small>Живая генерация голоса на мобильном устройстве не поддерживается.</small>;
 if(!nativeReady||!bridge()?.voice_speak)return <small>Для голосового разговора откройте актуальную сборку приложения Windows на этом ПК.</small>;
 async function send(question:string){const turn=++generation.current;let waiting:any;setRecording(false);setText(question);try{
   const filler=await bridge().voice_filler(p.state.voice_gender||'female');if(filler.enabled&&filler.audio)waiting=setTimeout(()=>{if(turn===generation.current){audio.current=new Audio(filler.audio);audio.current.play().catch(()=>{});}},filler.delay*1000);
   const catalog=await api('/voice/attempts/'+p.id+'/catalog');
   const result=await bridge().voice_classify(question,catalog);
   if(turn!==generation.current)return;
   const latest=await api('/attempts/'+p.id);
   const next=await api('/voice/attempts/'+p.id+'/question','POST',{id:result.id,reply:result.text,gender:result.gender,text:question,revision:latest.revision,command_id:uuid()});spokenCount.current=next.state.dialogue.length;onUpdate(next);
   const answer=next.state.dialogue.at(-1)?.text;
   if(answer){const r=await bridge().voice_speak(answer,next.state.voice_gender||p.state.voice_gender||'female');if(turn===generation.current){clearTimeout(waiting);setReplyUrl(r.audio);audio.current?.pause();audio.current=new Audio(r.audio);await playReply(audio.current);}}
 }catch(e:any){setError(e.message||String(e));}finally{clearTimeout(waiting);setBusy(false);}}
 return <div className="live-voice"><div className="voice-microphone-row"><MicButton recording={recording} disabled={speaking||busy&&!recording||p.status!=='active'} onClick={async()=>{if(recording){stop.current?.();setRecording(false);return;}setError('');audio.current?.pause();setBusy(true);const start=generation.current;stop.current=await record(q=>{if(start===generation.current)send(q);},e=>{setError(e);setBusy(false);setRecording(false);});setRecording(!!stop.current);}}/><span role="status">{recording?'Микрофон включён. Нажмите ещё раз, закончив вопрос.':speaking||busy?'Слушайте ответ…':'Микрофон выключен. Нажмите, чтобы говорить.'}</span></div><small>{text}</small><Notice>{error}</Notice></div>;
}

export function VoiceQueue(){
 const [q,setQ]=useState<Obj|null>(null);
 useEffect(()=>{let live=true;const poll=()=>api('/voice/queue').then(v=>{if(live)setQ(v);}).catch(()=>{});poll();const timer=setInterval(poll,3000);return()=>{live=false;clearInterval(timer);};},[]);
 if(!q||!q.pending&&!q.failed.length)return null;
 return <aside className="voice-queue" role="status"><details><summary>{q.pending?'Генерируются голосовые сообщения':'Не удалось озвучить сообщения'} · готово {q.ready}/{q.total}</summary><p>Генерация продолжается после публикации. При следующем запуске готовые записи сохранятся, незавершённые будут продолжены.</p>{q.failed.map((j:Obj)=><div key={j.id}><p>{j.text}</p><small>{j.error}</small><button onClick={async()=>{await api('/voice/jobs/'+j.id+'/retry','POST');setQ(await api('/voice/queue'));}}>Повторить</button></div>)}</details></aside>;
}

export function DDSVoiceCall({disabled,contacts,contactId,service,textOnly=false,incomingState,onSelect,onSend}:{disabled:boolean,contacts:Obj[],contactId:string,service:string,textOnly?:boolean,incomingState?:string,onSelect:(id:string)=>void,onSend:(text:string,id:string)=>Promise<any>}){
 useNativeReady();
 const [phase,setPhase]=useState('idle'),[error,setError]=useState('');
 const stop=useRef<(()=>void)|undefined>(undefined),audio=useRef<HTMLAudioElement|null>(null),tone=useRef<AudioContext|null>(null),generation=useRef(0),locked=useRef(false);
 const cancel=()=>{generation.current++;locked.current=false;stop.current?.();stop.current=undefined;audio.current?.pause();tone.current?.close().catch(()=>{});tone.current=null;setPhase('idle');};
 useEffect(()=>()=>{generation.current++;stop.current?.();audio.current?.pause();tone.current?.close().catch(()=>{});},[]);
 async function call(c:Obj){
  if(locked.current||disabled)return;if(textOnly){onSelect(c.id);return;}document.querySelectorAll('audio').forEach(a=>a.pause());locked.current=true;const run=++generation.current;onSelect(c.id);setError('');setPhase('dialing');
  let timer:ReturnType<typeof setInterval>|undefined;
  try{
   if(!c.greeting_audio)throw Error('Приветствие ещё генерируется. Дождитесь готовности записи.');
   if(run!==generation.current)return;
   const ctx=new AudioContext();tone.current=ctx;await ctx.resume();
   const beep=()=>{if(ctx.state==='closed')return;const oscillator=ctx.createOscillator(),gain=ctx.createGain();oscillator.frequency.value=425;gain.gain.value=.055;oscillator.connect(gain);gain.connect(ctx.destination);oscillator.start();oscillator.stop(ctx.currentTime+.8);};
   beep();timer=setInterval(beep,2200);
   const cached=await bridge()?.voice_cached?.(c.greeting_audio);
   const reply={audio:cached||'/api/media/'+c.greeting_audio};
   await new Promise(resolve=>setTimeout(resolve,1500));
   clearInterval(timer);await ctx.close();tone.current=null;if(run!==generation.current)return;
   setPhase('greeting');const player=new Audio(reply.audio);audio.current=player;
   await new Promise<void>((resolve,reject)=>{player.onended=()=>resolve();player.onerror=()=>reject(Error('Не удалось воспроизвести приветствие службы.'));player.play().catch(reject);});
   if(run!==generation.current)return;setPhase('ready');
  }catch(e:any){if(run===generation.current){setError(e.message||String(e));setPhase('idle');locked.current=false;}}
  finally{clearInterval(timer);if(tone.current&&run===generation.current){tone.current.close().catch(()=>{});tone.current=null;}}
 }
 async function microphone(){
  if(phase==='recording'){setPhase('sending');stop.current?.();return;}
  if(phase!=='ready')return;const run=generation.current;setPhase('starting');
  stop.current=await record(async text=>{if(run!==generation.current)return;setPhase('sending');try{if(text.trim().length<3)throw Error('Речь не распознана. Нажмите микрофон и повторите.');await onSend(text,contactId);await new Promise(r=>setTimeout(r,100));const reply=document.querySelector<HTMLAudioElement>('.phone-audio-replies audio');if(reply&&!reply.ended&&!reply.paused)await new Promise<void>(resolve=>{const t=setTimeout(resolve,90000);reply.addEventListener('ended',()=>{clearTimeout(t);resolve();},{once:true});});}catch(e:any){if(run===generation.current)setError(e.message||String(e));}finally{if(run===generation.current)setPhase('ready');}},message=>{if(run===generation.current){setError(message);setPhase('ready');}});
  if(run!==generation.current)stop.current?.();else if(stop.current)setPhase('recording');
 }
 const selected=contacts.find(c=>c.id===contactId),connected=phase!=='idle';
 return <div className="dds-voice-call">
  <div className="phone-quick-contacts" aria-label="Быстрые контакты">{contacts.map(c=><button key={c.id} data-contact={c.id} data-guide="voice-contact" disabled={disabled||connected||!c.phone} title={'Позвонить: '+c.name+' · '+c.phone} onClick={()=>call(c)}><span><b>{c.name}</b><small>{c.phone}</small></span><span className="contact-call-action"><Phone size={14}/> Позвонить</span></button>)}</div>
  <div className="phone-call-panel">
   <div className="phone-party"><b>{connected?selected?.name:'Телефон ДДС'}</b><small>{connected?selected?.phone:'Выберите контакт выше'}</small></div>
   <div className="phone-phase" role="status">{incomingState||({idle:'Нет активного звонка',dialing:'Соединяем…',greeting:'Слушайте приветствие',ready:'Можно говорить',starting:'Включаем микрофон…',recording:'Говорите. Нажмите микрофон, чтобы отправить.',sending:'Слушайте ответ…'}[phase])}</div>
   <div className="phone-controls"><div><MicButton recording={phase==='recording'} disabled={!['ready','recording'].includes(phase)||disabled} onClick={microphone}/><small>{phase==='recording'?'Отправить':'Микрофон'}</small></div><div><button className="handset hangup" disabled={!connected} aria-label="Завершить звонок" title="Завершить звонок" onClick={cancel}><PhoneOff size={24}/></button><small>Завершить</small></div></div>
  </div><Notice>{error}</Notice></div>;
}
