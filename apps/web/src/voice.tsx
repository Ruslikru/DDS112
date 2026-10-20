import {audioResource,releaseAudio} from './audio-resource';
import {AssistantMicrophoneSettings} from './assistant-microphone-settings';
import {selectedMicrophone,selectMicrophone,MICROPHONE_CHANGED} from './microphone-preference';
import './sound-settings.css';
import {CallAudioEngine} from './call-audio';
import React,{useEffect,useRef,useState} from 'react';
import {api,Notice,Obj,uuid} from './shared';
import './voice.css';
import {useHeldRecording} from './use-held-recording';
import {Phone,PhoneOff,Mic,MicOff} from 'lucide-react';

const bridge=()=> (window as any).pywebview?.api;
async function speechResource(id:string){
 const cached=await Promise.resolve(bridge()?.voice_cached?.(id)).catch(()=>null);
 return cached||audioResource('/api/media/'+id);
}
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
// One shared error is shown once above the list instead of in every row.
const sameError=(failed:Obj[])=>failed.length>1&&failed.every(j=>j.error===failed[0].error)?failed[0].error||'':'';
function RetryAll({failed,error,onDone}:{failed:Obj[],error:string,onDone:()=>Promise<void>}){
 if(failed.length<2)return null;
 return <><Notice>{error&&'Не удалось озвучить '+failed.length+' записей: '+error}</Notice><button onClick={async()=>{await api('/voice/jobs/retry-failed','POST');await onDone();}}>Повторить все ({failed.length})</button></>;
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
 const pending=jobs.some(j=>['pending','running'].includes(j.status)),failed=jobs.filter(j=>j.status==='failed'),common=sameError(failed);
 const reload=async()=>{setJobs(await api('/voice/jobs','POST',{keys:jobs.map(x=>x.id)}));setError('');};
 return <aside className="voice-draft" aria-live="polite"><details><summary>{pending?'Идёт генерация звуков для сообщений руководителей бригад':'Звуки сообщений бригад'} · {jobs.filter(j=>j.status==='ready').length}/{jobs.length}</summary><Notice>{error}</Notice><RetryAll failed={failed} error={common} onDone={reload}/>{jobs.map(j=><div key={j.id}><p>{j.text}</p>{j.audio_id?<audio controls preload="none" src={'/api/media/'+j.audio_id}/>:<span>{j.status==='failed'?common?'Не озвучено':j.error:'Готовится…'}</span>}{j.status==='failed'&&<button onClick={async()=>{await api('/voice/jobs/'+j.id+'/retry','POST');await reload();}}>Повторить</button>}</div>)}</details></aside>;
}

/** True when the native Windows bridge with speech recognition is present on this PC. */
export function hasVoiceBridge(){return !mobile()&&!!bridge()?.voice_transcribe;}
/** Speech recognition on the classroom server (for a browser without the native bridge). */
export const serverTranscribe=(audio:string):Promise<Obj>=>api('/voice/transcribe','POST',{audio});
/** Microphones the browser knows; labels are filled only after a microphone permission was granted. */
export async function listMicrophones():Promise<{id:string,label:string}[]>{
 try{const all=await navigator.mediaDevices?.enumerateDevices?.();return (all||[]).filter(d=>d.kind==='audioinput').map((d,i)=>({id:d.deviceId,label:d.label||`Микрофон ${i+1}`}));}
 catch{return [];}
}
/** Records up to 15 s and passes the audio to `transcribe` (the native bridge when omitted). Returns a stop function.
 *  `deviceId` picks a microphone; `onLevel` receives the input level (RMS, 0..1) about 20 times a second while recording. */
async function openCallMicrophone(deviceId?:string):Promise<MediaStream>{
  if(typeof bridge()?.allow_microphone==='function')await bridge().allow_microphone();
  if(!navigator.mediaDevices?.getUserMedia)throw Error('Микрофон в браузере доступен только по HTTPS или на адресе localhost.');
  let opened:MediaStream|undefined,problem:any;
  deviceId??=selectedMicrophone();
  const constraints:MediaStreamConstraints={audio:deviceId?{deviceId:{exact:deviceId}}:true};
  try{opened=await navigator.mediaDevices.getUserMedia(constraints);}
  catch(e:any){
   problem=e;
   // A remembered microphone may be unplugged: fall back to the default one.
   if(deviceId&&e?.name!=='NotAllowedError'){try{opened=await navigator.mediaDevices.getUserMedia({audio:true});}catch(e2:any){problem=e2;}}
  }
  if(!opened)throw Error(problem?.name==='NotAllowedError'?'Доступ к микрофону запрещён. Разрешите его в настройках браузера.':problem?.name==='NotFoundError'?'Микрофон не найден.':'Микрофон недоступен: '+(problem?.message||String(problem)));
  return opened;
}
export async function record(onDone:(text:string)=>void,onError:(text:string)=>void,transcribe?:(audio:string)=>Promise<Obj>,options:{deviceId?:string,stream?:MediaStream,onLevel?:(level:number)=>void}={}):Promise<((cancel?:boolean)=>void)|undefined>{
 try{
  let convert=transcribe;
  if(!convert){
   if(mobile()||!bridge())throw Error('Живой голос доступен в приложении Windows на этом ПК.');
   const native=await voiceBridge();
   // Older voice clients use WebView's own microphone permission prompt.
   convert=(audio:string)=>bridge().voice_transcribe(audio);
  }
  const stream=options.stream?.getAudioTracks().some(t=>t.readyState==='live')?options.stream:await openCallMicrophone(options.deviceId);
  let recorder:MediaRecorder;try{recorder=new MediaRecorder(stream);}catch(e){stream.getTracks().forEach(t=>t.stop());throw e;}const chunks:BlobPart[]=[];
  let cancelled=false;
  // Input level meter, so the speaker can see whether the microphone picks anything up.
  let meter:{context:AudioContext,timer:any}|undefined;
  if(options.onLevel){try{
   const context=new AudioContext(),analyser=context.createAnalyser();analyser.fftSize=1024;context.createMediaStreamSource(stream).connect(analyser);
   const buffer=new Float32Array(analyser.fftSize);
   meter={context,timer:setInterval(()=>{analyser.getFloatTimeDomainData(buffer);let sum=0;for(const v of buffer)sum+=v*v;options.onLevel!(Math.sqrt(sum/buffer.length));},50)};
  }catch{}}
  const stopMeter=()=>{if(!meter)return;clearInterval(meter.timer);meter.context.close().catch(()=>{});meter=undefined;};
  recorder.ondataavailable=e=>chunks.push(e.data);
  let started=0;
  recorder.onstop=async()=>{stopMeter();stream.getTracks().forEach(t=>t.stop());if(cancelled)return;if(performance.now()-started<350){onError('Кнопку нужно удерживать. Зажмите микрофон, произнесите фразу и затем отпустите.');return;}try{const blob=new Blob(chunks);if(!blob.size)throw Error('Запись пустая. Удерживайте микрофон, пока говорите.');const bytes=new Uint8Array(await blob.arrayBuffer());let raw='';bytes.forEach(b=>raw+=String.fromCharCode(b));const value=await convert!(btoa(raw));onDone(value.text+'');}catch(e:any){onError(e.message||String(e));}};
  recorder.start();started=performance.now();const limit=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},24000);
  // stop(true) discards the recording: nothing is transcribed and neither callback fires.
  return (cancel=false)=>{clearTimeout(limit);cancelled=cancel;if(recorder.state==='recording')recorder.stop();};
 }catch(e:any){onError(e.message||String(e));return undefined;}
}

export function VoiceSettings(_props:{localOnly?:boolean}={}){
 const nativeReady=useNativeReady(),chat=useVoiceChat();
 const [local,setLocal]=useState<Obj>(),[saving,setSaving]=useState(false),[error,setError]=useState('');
 const [mic,setMic]=useState(selectedMicrophone),[recording,setRecording]=useState(false),[testing,setTesting]=useState(false),[level,setLevel]=useState(0),[result,setResult]=useState('');
 const stop=useRef<((cancel?:boolean)=>void)|undefined>(undefined),generation=useRef(0);
 useEffect(()=>{let active=true;if(bridge()?.voice_status)bridge().voice_status().then((value:Obj)=>{if(active)setLocal(value);}).catch((e:any)=>{if(active)setError(e.message||String(e));});return()=>{active=false;};},[nativeReady]);
 useEffect(()=>{const changed=()=>setMic(selectedMicrophone());window.addEventListener(MICROPHONE_CHANGED,changed);return()=>window.removeEventListener(MICROPHONE_CHANGED,changed);},[]);
 useEffect(()=>()=>{generation.current++;stop.current?.(true);},[]);
 async function changeChat(value:boolean){
  setSaving(true);setError('');
  try{await bridge().voice_settings({...local?.settings.live,chat_enabled:value});setLocal(await bridge().voice_status());window.dispatchEvent(new Event('voice-chat-settings'));}
  catch(e:any){setError(e.message||String(e));}finally{setSaving(false);}
 }
 async function testMicrophone(){
  const run=++generation.current;setError('');setResult('');setLevel(0);setTesting(true);
  const finish=()=>{if(run===generation.current){setRecording(false);setTesting(false);setLevel(0);stop.current=undefined;}};
  const end=await record(text=>{if(run===generation.current){setResult('Распознано: '+text);finish();}},message=>{if(run===generation.current){setError(message);finish();}},serverTranscribe,{deviceId:mic,onLevel:value=>{if(run===generation.current)setLevel(value);}});
  if(run!==generation.current){end?.(true);return undefined;}
  if(!end){finish();return undefined;}
  setRecording(true);
  const release=(cancel=false)=>{setRecording(false);setLevel(0);if(cancel){generation.current++;setTesting(false);}end(cancel);};
  stop.current=release;return release;
 }
 return <section className="panel form-panel voice-settings minimal-sound-settings"><h2 className="section-title-bar">Настройки звука</h2><div className="sound-settings-content">
  <div className={'sound-chat-row'+(chat?' is-enabled':'')}>
   <div><h3 id="sound-chat-label">Текстовый чат</h3><p id="sound-chat-help">Разрешить ввод ответов с клавиатуры на этом ПК.</p></div>
   <button type="button" role="switch" aria-checked={chat} aria-labelledby="sound-chat-label" aria-describedby="sound-chat-help" className="sound-chat-switch" disabled={saving||!local?.settings||!bridge()?.voice_settings} onClick={()=>void changeChat(!chat)}><span className="sound-switch-track" aria-hidden="true"><span/></span><span>{chat?'Включён':'Выключен'}</span></button>
  </div>
  {!nativeReady&&<p className="sound-native-note">Для настройки текстового чата откройте приложение Windows на этом ПК.</p>}
  <div className="sound-microphone-section"><h3>Микрофон</h3><AssistantMicrophoneSettings inline value={mic} disabled={testing} onChange={value=>{setMic(value);selectMicrophone(value);setResult('');}}/>
   <div className="sound-microphone-test"><MicButton recording={recording} disabled={testing&&!recording} onStart={testMicrophone} title="Удерживайте для проверки микрофона"/><div><strong>{recording?'Говорите — запись идёт':testing?'Распознаю запись…':'Проверка микрофона'}</strong><p>{recording?'Отпустите кнопку, чтобы проверить запись.':'Удерживайте кнопку и произнесите короткую фразу.'}</p></div><meter min={0} max={1} value={Math.min(1,level*6)} aria-label="Уровень микрофона"/></div>
  </div>{!_props.localOnly&&<DialogueThreads/>}<Notice>{error}</Notice>{result&&<p className="sound-test-result" role="status">{result}</p>}
 </div></section>;
}

function DialogueThreads(){
 const [value,setValue]=useState<Obj>(),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 useEffect(()=>{let live=true;api('/voice/dialogue-settings').then(v=>{if(live)setValue(v);}).catch(()=>{});return()=>{live=false;};},[]);
 if(!value)return null;
 return <fieldset disabled={busy||!value.editable}><legend>Звонки ДДС · потоки процессора сервера</legend><p>Отдельно для ответа, распознавания и озвучки. Новые значения применятся к следующему запросу.</p>{[['dialogue_threads','Ответ абонента'],['stt_threads','Распознавание GigaAM'],['tts_threads','Озвучка']].map(([key,label])=><label key={key}>{label}<input aria-label={label+' — потоки'} type="number" min={1} max={16} value={value[key]} onChange={e=>setValue({...value,[key]:Number(e.target.value)})}/></label>)}<button onClick={async()=>{setBusy(true);setMessage('');try{const {editable,...settings}=value;setValue(await api('/voice/dialogue-settings','POST',settings));setMessage('Настройки сохранены');}catch(e:any){setMessage(e.message);}finally{setBusy(false);}}}>Сохранить потоки</button><p role="status">{message}</p></fieldset>;
}

export function BrigadeAudio({id,autoPlay=false,playKey=id,hidden=false,onEnded,onPlaying,onError,beforePlay}:{id:string,autoPlay?:boolean,playKey?:string,hidden?:boolean,onEnded?:()=>void,onPlaying?:()=>void,onError?:(message:string)=>void,beforePlay?:(player:HTMLAudioElement)=>Promise<void>}){
 const [source,setSource]=useState<{id:string,url:string}|null>(null);const ref=useRef<HTMLAudioElement>(null);
 const url=source?.id===id?source.url:undefined;
 useEffect(()=>{let closed=false,url:string|undefined;const player=ref.current;setSource(null);speechResource(id).then(value=>{url=value;if(closed)releaseAudio(value);else setSource({id,url:value});}).catch(e=>onError?.(e.message));return()=>{closed=true;player?.pause();releaseAudio(url);};},[id]);
 useEffect(()=>{const key='voice-played:'+playKey;if(url&&autoPlay&&!sessionStorage.getItem(key)){document.querySelectorAll('audio').forEach(a=>{if(a!==ref.current)a.pause();});const player=ref.current;if(player)Promise.resolve(beforePlay?.(player)).then(()=>player.play()).then(()=>sessionStorage.setItem(key,'1')).catch(e=>onError?.(e.message||'Не удалось включить звук'));}},[url,autoPlay,playKey]);
 return <audio ref={ref} onEnded={onEnded} onPlaying={onPlaying} onError={()=>onError?.('Не удалось воспроизвести ответ. Проверьте связь с сервером.')} controls={!hidden} hidden={hidden} preload="none" src={url}/>;
}

export function MicButton({recording,disabled,onStart,title}:{recording:boolean,disabled:boolean,onStart:()=>Promise<((cancel?:boolean)=>void)|undefined>,title?:string}){
 const hold=useHeldRecording(onStart,!disabled&&!recording);
 const label=title||(recording?'Отпустите микрофон, чтобы отправить':disabled?'Дождитесь ответа':'Удерживайте и говорите (Ctrl+Space)');
 return <button type="button" className={'voice-mic '+(recording?'recording':disabled?'waiting':'ready')} disabled={disabled&&!hold.held} title={label} aria-label={label} aria-pressed={recording} onPointerDown={e=>{e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);void hold.press();}} onPointerUp={hold.release} onPointerCancel={hold.cancel} onKeyDown={e=>{if((e.code==='Space'||e.key==='Enter')&&!e.repeat){e.preventDefault();void hold.press();}}} onKeyUp={e=>{if(e.code==='Space'||e.key==='Enter'){e.preventDefault();hold.release();}}} onContextMenu={e=>e.preventDefault()}>{recording?<Mic size={25}/>:disabled?<MicOff size={24}/>:<MicOff size={25}/>}</button>;
}
async function playReply(player:HTMLAudioElement){await new Promise<void>((resolve,reject)=>{player.onended=()=>resolve();player.onerror=()=>reject(Error('Не удалось воспроизвести звук.'));player.onpause=()=>resolve();player.play().catch(reject);});}

export function LiveVoice({p,onUpdate}:{p:Obj,onUpdate:(p:Obj)=>void}){
 const nativeReady=useNativeReady();
 const [busy,setBusy]=useState(false),[recording,setRecording]=useState(false),[error,setError]=useState(''),[text,setText]=useState(''),[speaking,setSpeaking]=useState(false),[replyUrl,setReplyUrl]=useState('');
 const stop=useRef<((cancel?:boolean)=>void)|undefined>(undefined),audio=useRef<HTMLAudioElement|null>(null),generation=useRef(0),spokenCount=useRef(0);
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
 return <div className="live-voice"><div className="voice-microphone-row"><MicButton recording={recording} disabled={speaking||busy&&!recording||p.status!=='active'} onStart={async()=>{setError('');audio.current?.pause();setBusy(true);const start=generation.current;const finish=await record(q=>{if(start===generation.current)send(q);},e=>{setError(e);setBusy(false);setRecording(false);},serverTranscribe);stop.current=finish;setRecording(!!finish);return finish?(cancel=false)=>{finish(cancel);setRecording(false);if(cancel)setBusy(false);}:undefined;}}/><span role="status">{recording?'Говорите. Отпустите кнопку, чтобы отправить.':speaking||busy?'Слушайте ответ…':'Удерживайте микрофон, пока говорите.'}</span></div><small>{text}</small><Notice>{error}</Notice></div>;
}

export function VoiceQueue(){
 const [q,setQ]=useState<Obj|null>(null);
 useEffect(()=>{let live=true;const poll=()=>api('/voice/queue').then(v=>{if(live)setQ(v);}).catch(()=>{});poll();const timer=setInterval(poll,3000);return()=>{live=false;clearInterval(timer);};},[]);
 if(!q||!q.pending&&!q.failed.length)return null;
 const common=sameError(q.failed),reload=async()=>setQ(await api('/voice/queue'));
 return <aside className="voice-queue" role="status"><details><summary>{q.pending?'Генерируются голосовые сообщения':'Не удалось озвучить сообщения'} · готово {q.ready}/{q.total}</summary><p>Генерация продолжается после публикации. При следующем запуске готовые записи сохранятся, незавершённые будут продолжены.</p><RetryAll failed={q.failed} error={common} onDone={reload}/>{q.failed.map((j:Obj)=><div key={j.id}><p>{j.text}</p>{!common&&<small>{j.error}</small>}<button onClick={async()=>{await api('/voice/jobs/'+j.id+'/retry','POST');await reload();}}>Повторить</button></div>)}</details></aside>;
}

export function DDSVoiceCall({disabled,contacts,contactId,service,textOnly=false,incomingState,incomingReady,engine,onStart,onEnd,onSelect,onSend}:{disabled:boolean,contacts:Obj[],contactId:string,service:string,textOnly?:boolean,incomingState?:string,incomingReady?:string,engine?:CallAudioEngine,onStart?:()=>Promise<void>,onEnd?:()=>void,onSelect:(id:string)=>void,onSend:(text:string,id:string)=>Promise<any>}){
 useNativeReady();
 const [phase,setPhase]=useState('idle'),[error,setError]=useState(''),[heard,setHeard]=useState('');
 const resources=useRef(new Set<string>());
 const warmed=useRef<Promise<MediaStream|undefined>|undefined>(undefined),warmStream=useRef<MediaStream|undefined>(undefined);
 const closeMicrophone=()=>{warmStream.current?.getTracks().forEach(track=>track.stop());warmStream.current=undefined;warmed.current=undefined;};
 const primeMicrophone=(run:number)=>{warmed.current=openCallMicrophone().then(stream=>{if(run!==generation.current){stream.getTracks().forEach(track=>track.stop());return undefined;}warmStream.current=stream;return stream;}).catch(e=>{if(run===generation.current)setError(e.message);return undefined;});};
 const stop=useRef<((cancel?:boolean)=>void)|undefined>(undefined),audio=useRef<HTMLAudioElement|null>(null),tone=useRef<AudioContext|null>(null),generation=useRef(0),locked=useRef(false);
 const cancel=()=>{generation.current++;locked.current=false;stop.current?.(true);stop.current=undefined;audio.current?.pause();closeMicrophone();resources.current.forEach(releaseAudio);resources.current.clear();tone.current?.close().catch(()=>{});tone.current=null;engine?.hangup();onEnd?.();setPhase('idle');};
 useEffect(()=>()=>{generation.current++;stop.current?.(true);audio.current?.pause();closeMicrophone();resources.current.forEach(releaseAudio);resources.current.clear();tone.current?.close().catch(()=>{});onEnd?.();},[]);
 useEffect(()=>{if(!incomingReady)return;const run=++generation.current;locked.current=true;setError('');setHeard('');primeMicrophone(run);setPhase('ready');},[incomingReady]);
 async function call(c:Obj){
  if(locked.current||disabled)return;if(textOnly){onSelect(c.id);return;}document.querySelectorAll('audio').forEach(a=>a.pause());locked.current=true;const run=++generation.current;onSelect(c.id);setError('');setPhase('dialing');
  let timer:ReturnType<typeof setInterval>|undefined;
  try{
   setHeard('');primeMicrophone(run);
   await Promise.all([engine?.unlock(),onStart?.()]);await engine?.prepare(c.call_audio);if(run!==generation.current)return;
   if(!c.greeting_audio)throw Error('Запись приветствия недоступна. Обновите карточку; если ошибка повторяется, сообщите преподавателю.');
   if(run!==generation.current)return;
   await engine?.signal('ringback',true);
   const url=await speechResource(c.greeting_audio);resources.current.add(url);
   const reply={audio:url};
   await new Promise(resolve=>setTimeout(resolve,2200));
   if(run!==generation.current)return;await engine?.connect(c.call_audio);if(run!==generation.current)return;
   setPhase('greeting');const player=new Audio(reply.audio);audio.current=player;engine?.attach(player);
   await new Promise<void>((resolve,reject)=>{player.onended=()=>resolve();player.onerror=()=>reject(Error('Не удалось воспроизвести приветствие службы.'));player.play().catch(reject);});
   await warmed.current;if(run!==generation.current)return;setPhase('ready');
  }catch(e:any){if(run===generation.current){generation.current++;closeMicrophone();setError(e.message||String(e));engine?.hangup();onEnd?.();setPhase('idle');locked.current=false;}}
  finally{clearInterval(timer);if(tone.current&&run===generation.current){tone.current.close().catch(()=>{});tone.current=null;}}
 }
 async function microphone(){
  if(phase!=='ready')return;const run=generation.current;setPhase('starting');
  const prepared=await warmed.current;warmed.current=undefined;warmStream.current=undefined;
  if(run!==generation.current){prepared?.getTracks().forEach(track=>track.stop());return;}
  stop.current=await record(async text=>{if(run!==generation.current)return;setHeard(text);setPhase('sending');try{if(!/[а-яa-z0-9]/i.test(text))throw Error('Речь не распознана. Нажмите микрофон и повторите.');const result=await onSend(text,contactId);if(run!==generation.current)return;const reply=result?.state?.messages?.at(-1);if(reply?.direction!=='outgoing_answer'||reply.contact_id!==contactId)throw Error('Ответ абонента не получен. Повторите реплику.');if(reply.audio){const cached=await speechResource(reply.audio);resources.current.add(cached);if(run!==generation.current)return;await engine?.finishWaiting();if(run!==generation.current)return;const player=new Audio(cached);audio.current=player;engine?.attach(player);await playReply(player);if(run!==generation.current)return;if(reply.dispatch)await engine?.replyEnded();releaseAudio(cached);resources.current.delete(cached);}if(run===generation.current){if(reply.call_end)cancel();else primeMicrophone(run);}}catch(e:any){if(run===generation.current){setError(e.message||String(e));primeMicrophone(run);}}finally{await engine?.finishWaiting();if(run===generation.current)setPhase('ready');}},message=>{void engine?.finishWaiting();if(run===generation.current){setError(message);primeMicrophone(run);setPhase('ready');}},serverTranscribe,{stream:prepared});
  const finish=stop.current;
  if(run!==generation.current){finish?.(true);return;}
  if(finish)setPhase('recording');
  return finish?(cancel=false)=>{finish(cancel);if(run===generation.current){setPhase(cancel?'ready':'recognizing');if(!cancel){const c=contacts.find(c=>c.id===contactId);engine?.waitForReply(c?.voice_gender,c?.voice_tts);}}}:undefined;
 }
 const selected=contacts.find(c=>c.id===contactId),connected=phase!=='idle';
 return <div className="dds-voice-call" data-phase={phase}>
  <div className="phone-quick-contacts" aria-label="Быстрые контакты">{contacts.map(c=><button key={c.id} data-contact={c.id} data-guide="voice-contact" disabled={disabled||connected||!c.phone} title={'Позвонить: '+c.name+' · '+c.phone} onClick={()=>call(c)}><span><b>{c.name}</b><small>{c.phone}</small></span><span className="contact-call-action"><Phone size={14}/> Позвонить</span></button>)}</div>
  <div className="phone-call-panel">
   <div className="phone-party"><b>{connected?selected?.name:'Телефон ДДС'}</b><small>{connected?selected?.phone:'Выберите контакт выше'}</small></div>
   <div className="phone-phase" role="status">{incomingState||({idle:'Нет активного звонка',dialing:'Соединяем…',greeting:'Слушайте приветствие',ready:'Можно говорить',starting:'Включаем микрофон…',recording:'Говорите. Отпустите кнопку, чтобы отправить.',recognizing:'Распознаём речь…',sending:'Слушайте ответ…'}[phase])}</div>
   <div className="phone-controls"><div><MicButton recording={phase==='recording'} disabled={!['ready','recording'].includes(phase)||disabled} onStart={microphone}/><small>{phase==='recording'?'Отправить':'Микрофон'}</small></div><div><button className="handset hangup" disabled={!connected} aria-label="Завершить звонок" title="Завершить звонок" onClick={cancel}><PhoneOff size={24}/></button><small>Завершить</small></div></div>
  </div>{heard&&<p className="phone-recognized" role="status"><strong>Распознано:</strong> {heard}</p>}<Notice>{error}</Notice></div>;
}
