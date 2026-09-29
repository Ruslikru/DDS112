import {createPortal} from 'react-dom';
import React,{useEffect,useState} from 'react';
import {X} from 'lucide-react';
export function StudentHint({target,children,onClose}:{target:string,children:React.ReactNode,onClose?:()=>void}){
 const [rect,setRect]=useState<DOMRect|null>(null),[hidden,setHidden]=useState(false);
 useEffect(()=>{let current:Element|null=null;const update=()=>{const el=hidden||document.querySelector('.teacher-broadcast')?null:Array.from(document.querySelectorAll(target)).find(x=>{const r=x.getBoundingClientRect();return r.width>0&&r.height>0;})||null;if(el!==current){current?.classList.remove('student-hint-target');current=el;el?.classList.add('student-hint-target');if(el){const r=el.getBoundingClientRect();if(r.top<0||r.bottom>innerHeight)el.scrollIntoView({block:'nearest'});}}setRect(el?.getBoundingClientRect()||null);};update();const timer=setInterval(update,250);return()=>{clearInterval(timer);current?.classList.remove('student-hint-target');};},[target,hidden]);
 if(hidden||!rect)return null;
 const width=Math.min(340,innerWidth-32),left=Math.max(16,Math.min(innerWidth-width-16,rect.left+rect.width/2-width/2)),below=rect.top<innerHeight/2;
 return createPortal(<aside className={'student-coach '+(below?'below':'above')} role="status" style={{position:'fixed',left,width,...(below?{top:rect.bottom+16}:{bottom:innerHeight-rect.top+16}),'--arrow-x':Math.max(18,Math.min(width-18,rect.left+rect.width/2-left))+'px'} as React.CSSProperties & {'--arrow-x':string}}><button className="coach-close" aria-label="Закрыть подсказку" onClick={()=>{setHidden(true);onClose?.();}}><X size={16}/></button>{children}</aside>,document.body);
}
