import React,{useEffect,useRef} from 'react';
import {Headphones,Volume2} from 'lucide-react';
import {useHeldRecording} from './use-held-recording';

/** A tap routes/answers; a hold records. Releasing after a hold must never click or hang up. */
export function PhoneChannelButton({kind,selected,disabled,canTalk,recording,onActivate,onTalk}:{kind:'headset'|'speaker',selected:boolean,disabled:boolean,canTalk:boolean,recording:boolean,onActivate:()=>void,onTalk:()=>Promise<((cancel?:boolean)=>void)|undefined>}){
 const held=useHeldRecording(onTalk,canTalk,selected);
 const timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined),suppressClick=useRef(false);
 const clear=()=>{clearTimeout(timer.current);timer.current=undefined;};
 useEffect(()=>{window.addEventListener('pointerup',clear);window.addEventListener('blur',clear);return()=>{clear();window.removeEventListener('pointerup',clear);window.removeEventListener('blur',clear);};},[]);
 function press(){clear();suppressClick.current=false;if(canTalk)timer.current=setTimeout(()=>{suppressClick.current=true;void held.press();},200);}
 const label=kind==='headset'?'Гарнитура':'Громкая связь';
 return <button className="avaya-channel" data-guide="phone-channel" data-recording={recording} aria-label={label} aria-pressed={selected} disabled={disabled} title={label+': нажмите, чтобы ответить; удерживайте, чтобы говорить'}
  onPointerDown={e=>{if(e.button!==0)return;e.currentTarget.setPointerCapture(e.pointerId);press();}}
  onPointerUp={()=>{clear();held.release();}} onPointerCancel={()=>{clear();suppressClick.current=true;held.cancel();}}
  onKeyDown={e=>{if(e.code==='Space'&&!e.ctrlKey&&!e.repeat)press();}} onKeyUp={e=>{if(e.code==='Space'){clear();held.release();}}}
  onClick={()=>{if(suppressClick.current){suppressClick.current=false;return;}onActivate();}}>
  {kind==='headset'?<Headphones size={18}/>:<Volume2 size={16}/>}<i className={recording?'red':selected?'lit':''}/>
 </button>;
}
