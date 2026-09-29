import {X} from 'lucide-react';
import {ManagementConfirm} from './management';
import React,{createContext,useContext,useEffect,useRef,useState} from 'react';
import html2canvas from 'html2canvas';
import {api,Obj,UserContext,Notice} from './shared';

export const ClassroomContext=createContext<{links:Obj[],sharing:boolean,setSharing:(v:boolean)=>void,microphone:boolean,setMicrophone:(v:boolean)=>void}>({links:[],sharing:false,setSharing:()=>{},microphone:false,setMicrophone:()=>{}});

export function ClassroomClient({children}:React.PropsWithChildren){
 const user=useContext(UserContext),[links,setLinks]=useState<Obj[]>([]),[sharing,setSharing]=useState(()=>user.role==='student'||sessionStorage.getItem('training112:sharing:'+user.id)==='true'),[microphone,setMicrophone]=useState(false),[micPrompt,setMicPrompt]=useState(false),[error,setError]=useState(''),[registered,setRegistered]=useState(()=>!!localStorage.getItem('training112:station-token')&&(localStorage.getItem('training112:demo-role')!=='client'||localStorage.getItem('training112:station-configured')==='true'));
 useEffect(()=>{sessionStorage.setItem('training112:sharing:'+user.id,String(sharing));},[sharing,user.id]);
 useEffect(()=>{const update=()=>setRegistered(!!localStorage.getItem('training112:station-token')&&(localStorage.getItem('training112:demo-role')!=='client'||localStorage.getItem('training112:station-configured')==='true'));window.addEventListener('station-ready',update);return()=>window.removeEventListener('station-ready',update);},[]);
 const current=useRef({links,sharing,microphone});current.current={links,sharing,microphone};
 const peers=useRef(new Map<string,RTCPeerConnection>()),audios=useRef(new Map<string,HTMLAudioElement>()),stream=useRef<MediaStream|null>(null),pointer=useRef<HTMLDivElement>(null),ice=useRef(new Map<string,RTCIceCandidateInit[]>());
 const signal=(id:string,kind:string,payload:Obj)=>api(`/classroom/links/${id}/signal`,'POST',{kind,payload});
 useEffect(()=>{let active=true;
  if(microphone){navigator.mediaDevices?.getUserMedia({audio:true}).then(s=>{if(!active)s.getTracks().forEach(t=>t.stop());else stream.current=s;}).catch(e=>{setError('Микрофон: '+e.message);setMicrophone(false);});if(!navigator.mediaDevices){setError('Для микрофона запустите настольный клиент или откройте сервер по HTTPS.');setMicrophone(false);}}
  return()=>{active=false;stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;peers.current.forEach(p=>p.close());peers.current.clear();};
 },[microphone]);
 useEffect(()=>{let stop=false,busy=false;
  async function tick(){if(stop||busy||!registered)return;busy=true;
   try{let frame='';
    if(current.current.sharing){const canvas=await html2canvas(document.body,{scale:Math.min(1,1920/window.innerWidth),logging:false,ignoreElements:e=>e.hasAttribute('data-no-capture'),windowWidth:window.innerWidth,windowHeight:window.innerHeight,width:window.innerWidth,height:window.innerHeight,x:window.scrollX,y:window.scrollY,scrollX:window.scrollX,scrollY:window.scrollY});frame=canvas.toDataURL('image/jpeg',.65);}
    const incoming=await api('/classroom/presence','POST',{page:location.pathname,sharing:current.current.sharing,frame});if(!stop){setLinks(incoming);setError('');}
   }catch(e:any){if(!stop){setError(e.message);setLinks([]);}}finally{busy=false;}
  }tick();const timer=setInterval(tick,1800);return()=>{stop=true;clearInterval(timer);};
 },[registered,user.id]);
 useEffect(()=>{let stop=false,working=false;
  async function poll(){if(working)return;working=true;
   try{for(const link of current.current.links){let peer=peers.current.get(link.id);
    if(!peer && (link.student_id===user.id||current.current.microphone&&stream.current)){
      peer=new RTCPeerConnection({iceServers:[]});peers.current.set(link.id,peer);
      peer.onicecandidate=e=>{if(e.candidate)signal(link.id,'ice',e.candidate.toJSON()).catch(()=>{});};
      peer.ontrack=e=>{let audio=audios.current.get(link.id);if(!audio){audio=new Audio();audio.autoplay=true;audios.current.set(link.id,audio);}audio.srcObject=e.streams[0];audio.play().catch(()=>setError('Нажмите «Включить звук преподавателя».'));};
      if(link.teacher_id===user.id&&stream.current){stream.current.getTracks().forEach(t=>peer!.addTrack(t,stream.current!));const offer=await peer.createOffer();await peer.setLocalDescription(offer);await signal(link.id,'offer',{type:offer.type,sdp:offer.sdp});}
    }
    const messages=await api(`/classroom/links/${link.id}/signals`);
    for(const message of messages){const d=message.payload;
      if(message.kind==='offer'&&peer){if(peer.signalingState!=='stable')continue;await peer.setRemoteDescription(d);const answer=await peer.createAnswer();await peer.setLocalDescription(answer);await signal(link.id,'answer',{type:answer.type,sdp:answer.sdp});}
      else if(message.kind==='answer'&&peer)await peer.setRemoteDescription(d);
      else if(message.kind==='ice'&&peer){if(peer.remoteDescription)await peer.addIceCandidate(d);else ice.current.set(link.id,[...(ice.current.get(link.id)||[]),d]);}
      else if(link.student_id===user.id){const rect=link.mode==='demo'?document.querySelector('.teacher-broadcast img')?.getBoundingClientRect():null;const x=(rect?.left||0)+Math.max(0,Math.min(1,d.x||0))*(rect?.width||innerWidth),y=(rect?.top||0)+Math.max(0,Math.min(1,d.y||0))*(rect?.height||innerHeight);
        if(message.kind==='pointer'&&pointer.current){pointer.current.style.left=x+'px';pointer.current.style.top=y+'px';pointer.current.style.display='block';}
        if(link.mode==='help'&&current.current.sharing){const target=document.elementFromPoint(x,y) as HTMLElement;
          if(message.kind==='click'){target?.focus();target?.click();}
          if(message.kind==='scroll')window.scrollBy(0,Math.max(-600,Math.min(600,d.delta||0)));
          if(message.kind==='text'){const el=document.activeElement as HTMLInputElement;if(el&&['INPUT','TEXTAREA'].includes(el.tagName)&&el.type!=='password'&&!el.disabled){const setter=Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value')?.set;setter?.call(el,String(d.text||'').slice(0,5000));el.dispatchEvent(new Event('input',{bubbles:true}));}}
          if(message.kind==='key'&&['Enter','Escape','Tab','ArrowDown','ArrowUp'].includes(d.key))document.activeElement?.dispatchEvent(new KeyboardEvent('keydown',{key:d.key,bubbles:true}));
        }
      }
    }
    if(peer?.remoteDescription){for(const candidate of ice.current.get(link.id)||[])await peer.addIceCandidate(candidate);ice.current.delete(link.id);}
   }
   for(const [id,p] of peers.current)if(!current.current.links.some(l=>l.id===id)){p.close();peers.current.delete(id);audios.current.get(id)?.pause();audios.current.delete(id);}
   }catch(e:any){if(!stop)setError(e.message);}finally{working=false;}
  }const timer=setInterval(poll,300);return()=>{stop=true;clearInterval(timer);};
 },[user.id]);
 useEffect(()=>{let last=0;const move=(e:MouseEvent)=>{if(Date.now()-last<120)return;last=Date.now();for(const link of current.current.links)if(link.teacher_id===user.id&&link.mode==='demo')signal(link.id,'pointer',{x:e.clientX/innerWidth,y:e.clientY/innerHeight}).catch(()=>{});};document.addEventListener('mousemove',move);return()=>document.removeEventListener('mousemove',move);},[user.id]);
 useEffect(()=>{if(!links.length&&pointer.current)pointer.current.style.display='none';},[links.length]);
 const demo=links.find(l=>l.student_id===user.id&&l.mode==='demo');
 return <ClassroomContext.Provider value={{links,sharing,setSharing,microphone,setMicrophone:(v)=>v?setMicPrompt(true):setMicrophone(false)}}>{children}
  {user.role!=='student'&&(links.length>0||sharing||microphone)&&<div className="teacher-live-bar" data-no-capture><b>{sharing?'Трансляция экрана':microphone?'Микрофон включён':'Подключение к ученику'}</b><span>Получателей: {links.length}</span><button onClick={()=>microphone?setMicrophone(false):setMicPrompt(true)}>{microphone?'Выключить микрофон':'Включить микрофон'}</button><button onClick={async()=>{try{for(const l of links)await api('/classroom/links/'+l.id,'DELETE');setSharing(false);setMicrophone(false);setLinks([]);}catch(e:any){setError(e.message);}}}>Завершить показ · ученики повторяют</button>{error&&<span role="alert">{error}</span>}</div>}
  {user.role==='student'&&links.some(l=>l.student_id===user.id)&&<div className="classroom-connection" data-no-capture><b>Преподаватель подключён</b><button onClick={()=>audios.current.forEach(a=>a.play())}>Включить звук преподавателя</button><button onClick={()=>links.filter(l=>l.student_id===user.id).forEach(l=>api('/classroom/links/'+l.id,'DELETE'))}>Завершить подключение</button>{error&&<span role="status">{error}</span>}</div>}
  {micPrompt&&<ManagementConfirm title="Включить микрофон?" description="Ученики, подключённые к показу, будут слышать вас. Вы сможете выключить микрофон на панели трансляции." confirmLabel="Включить микрофон" onCancel={()=>setMicPrompt(false)} onConfirm={async()=>{const bridge=(window as any).pywebview?.api;if(bridge?.allow_microphone)await bridge.allow_microphone();setMicPrompt(false);setMicrophone(true);}}/>}
  {demo&&<div className="teacher-broadcast management-overlay" data-no-capture><section className="remote-dialog"><header><b>{demo.teacher} показывает работу</b> <button onClick={()=>api('/classroom/links/'+demo.id,'DELETE')} aria-label="Закрыть показ"><X size={20}/></button></header><div className="broadcast-screen">{demo.frame?<img src={demo.frame} alt="Экран преподавателя"/>:<p>Ожидаем изображение…</p>}</div></section></div>}
  <div ref={pointer} className="teacher-pointer" data-no-capture><svg width="24" height="30" viewBox="0 0 24 30"><path d="M2 2 L2 24 L8 18 L13 28 L17 26 L12 16 L21 16 Z" fill="#f36932" stroke="white" strokeWidth="2"/></svg><small>Преподаватель</small></div>
 </ClassroomContext.Provider>;
}
