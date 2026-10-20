import React,{useEffect,useRef,useState} from 'react';
import {MicButton,record,serverTranscribe} from './voice';
import './intro-microphone-check.css';

export function IntroMicrophoneCheck({onRecognized}:{onRecognized:(text:string)=>void}){
 const [recording,setRecording]=useState(false),[busy,setBusy]=useState(false),[text,setText]=useState(''),[hint,setHint]=useState(''),[level,setLevel]=useState(0);
 const stop=useRef<((cancel?:boolean)=>void)|undefined>(undefined),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;stop.current?.(true);};},[]);
 async function start(){
  setHint('');setText('');setBusy(true);onRecognized('');
  const done=()=>{if(alive.current){setBusy(false);setRecording(false);setLevel(0);}};
  const finish=await record(value=>{if(alive.current){setText(value);onRecognized(value);done();}},message=>{if(alive.current){setHint(message);done();}},serverTranscribe,{onLevel:value=>{if(alive.current)setLevel(value);}});
  if(!alive.current){finish?.(true);return;}
  if(!finish){done();return;}
  setRecording(true);
  const release=(cancel=false)=>{finish(cancel);setRecording(false);setLevel(0);if(cancel)setBusy(false);};stop.current=release;return release;
 }
 return <div className="intro-microphone-check"><ol><li><b>Зажмите</b> кнопку микрофона.</li><li>Не отпуская, скажите: <b>«Диспетчер на связи».</b></li><li><b>Отпустите</b> кнопку и дождитесь текста.</li></ol><div className={'intro-mic-control'+(recording?' is-recording':'')}><MicButton recording={recording} disabled={busy&&!recording} onStart={start} title="Зажмите микрофон и удерживайте, пока говорите"/><div><strong>{recording?'Говорите, удерживая кнопку':busy?'Проверяем запись…':'Зажмите и говорите'}</strong><span>{recording?'Отпустите, когда закончите.':'Одного короткого нажатия недостаточно.'}</span></div></div><meter min={0} max={1} value={Math.min(1,level*6)} aria-label="Уровень звука микрофона"/>{hint&&<p className="intro-mic-feedback" role="status">{hint}</p>}{text&&<p className="intro-mic-feedback success" role="status"><b>Микрофон работает.</b><br/>Распознано: {text}</p>}</div>;
}
