import {useEffect,useRef,useState} from 'react';

type StopRecording=(cancel?:boolean)=>void;

/** Запись существует только пока удерживается кнопка или Ctrl+Space. */
export function useHeldRecording(start:()=>Promise<StopRecording|undefined>,enabled:boolean){
 const [held,setHeld]=useState(false);
 const current=useRef({start,enabled});current.current={start,enabled};
 const pressed=useRef(false),starting=useRef(false),cancelled=useRef(false),stop=useRef<StopRecording|undefined>(undefined),alive=useRef(true);
 const release=useRef((cancel=false)=>{});
 release.current=(cancel=false)=>{
  if(cancel)cancelled.current=true;
  pressed.current=false;
  if(alive.current)setHeld(false);
  const finish=stop.current;stop.current=undefined;finish?.(cancel);
 };
 const press=async()=>{
  if(pressed.current||starting.current||!current.current.enabled)return;
  pressed.current=true;starting.current=true;cancelled.current=false;setHeld(true);
  try{
   const finish=await current.current.start();
   if(!alive.current){finish?.(true);return;}
   // Разрешение микрофона может появиться уже после отпускания кнопки.
   if(!pressed.current)finish?.(cancelled.current);else stop.current=finish;
  }finally{
   starting.current=false;
   if(!stop.current&&alive.current){pressed.current=false;setHeld(false);}
  }
 };
 const pressRef=useRef(press);pressRef.current=press;
 useEffect(()=>{
  alive.current=true;
  const up=()=>release.current(),blur=()=>release.current(true);
  const down=(event:KeyboardEvent)=>{if(event.ctrlKey&&event.code==='Space'&&!event.repeat&&current.current.enabled&&!document.querySelector('.assistant-mic')){event.preventDefault();void pressRef.current();}};
  const keyUp=(event:KeyboardEvent)=>{if(event.code==='Space'||event.key==='Control'){if(pressed.current)event.preventDefault();release.current();}};
  window.addEventListener('pointerup',up);window.addEventListener('pointercancel',blur);window.addEventListener('blur',blur);
  document.addEventListener('keydown',down);document.addEventListener('keyup',keyUp);
  return()=>{alive.current=false;release.current(true);window.removeEventListener('pointerup',up);window.removeEventListener('pointercancel',blur);window.removeEventListener('blur',blur);document.removeEventListener('keydown',down);document.removeEventListener('keyup',keyUp);};
 },[]);
 return {held,press,release:()=>release.current(),cancel:()=>release.current(true)};
}
