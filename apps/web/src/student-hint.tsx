import {createPortal} from 'react-dom';
import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {X} from 'lucide-react';
import './student-hint-layout.css';

export function StudentHint({target,children,onClose,dismissible=true,centered=false}:{target:string,children:React.ReactNode,onClose?:()=>void,dismissible?:boolean,centered?:boolean}){
 const card=useRef<HTMLElement>(null);
 const [rect,setRect]=useState<DOMRect|null>(null),[hidden,setHidden]=useState(false),[size,setSize]=useState({width:340,height:180});
 useEffect(()=>{let current:Element|null=null;const update=()=>{const el=hidden||document.querySelector('.teacher-broadcast,.mini-drill-modal,.assessment-modal,.management-confirm-backdrop')?null:Array.from(document.querySelectorAll(target)).find(x=>{const r=x.getBoundingClientRect();return r.width>0&&r.height>0;})||null;if(el!==current){current?.classList.remove('student-hint-target');current=el;el?.classList.add('student-hint-target');if(el){const r=el.getBoundingClientRect();if(r.top<0||r.bottom>innerHeight)el.scrollIntoView({block:'nearest'});}}setRect(el?.getBoundingClientRect()||null);};update();const timer=setInterval(update,250);return()=>{clearInterval(timer);current?.classList.remove('student-hint-target');};},[target,hidden]);
 useLayoutEffect(()=>{const el=card.current;if(!el)return;const measure=()=>setSize({width:el.offsetWidth,height:el.offsetHeight});measure();const observer=new ResizeObserver(measure);observer.observe(el);return()=>observer.disconnect();},[!!rect,children]);
 if(hidden||!rect)return null;
 const width=Math.min(centered?380:340,innerWidth-32),height=size.height,margin=16;
 const clamp=(value:number,max:number)=>Math.max(margin,Math.min(max-margin,value));
 const protectedRects=Array.from(document.querySelectorAll('.arm-address-read,.arm-description>p,.arm-incident-block,.arm-person,.tutorial-catalog h2,.tutorial-catalog>p,.tutorial-catalog article b,.student-learning-panel,.side-dialog,.tutorial-progress,.phone-dock,.arm-status-shade .arm-dialog')).map(el=>el.getBoundingClientRect()).filter(r=>r.width&&r.height);
 const overlap=(x:number,y:number,r:DOMRect)=>Math.max(0,Math.min(x+width,r.right)-Math.max(x,r.left))*Math.max(0,Math.min(y+height,r.bottom)-Math.max(y,r.top));
 const candidates=[{x:rect.right+20,y:rect.top},{x:rect.left-width-20,y:rect.top},{x:rect.left+(rect.width-width)/2,y:rect.top-height-20},{x:rect.left+(rect.width-width)/2,y:rect.bottom+20}];
 for(let y=margin;y<=innerHeight-height-margin;y+=40)for(let x=margin;x<=innerWidth-width-margin;x+=80)candidates.push({x,y});
 const positions=candidates.map(({x,y})=>({x:clamp(x,innerWidth-width),y:clamp(y,innerHeight-height)}));
 const score=({x,y}:{x:number,y:number})=>overlap(x,y,rect)*20+protectedRects.reduce((sum,r)=>sum+overlap(x,y,r)*6,0)+Math.hypot(x+width/2-(rect.left+rect.width/2),y+height/2-(rect.top+rect.height/2));
 const position=positions.sort((a,b)=>score(a)-score(b))[0];
 return createPortal(<aside ref={card} className={'student-coach '+(centered?'centered':'placed')} role="status" style={{position:'fixed',width,left:centered?(innerWidth-width)/2:position.x,top:centered?Math.max(margin,(innerHeight-height)/2):position.y}}>{dismissible&&<button className="coach-close" aria-label="Закрыть подсказку" onClick={()=>{setHidden(true);onClose?.();}}><X size={16}/></button>}{children}</aside>,document.body);
}
