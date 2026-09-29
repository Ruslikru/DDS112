import {createPortal} from 'react-dom';
import React, {useEffect, useRef} from 'react';
import {X} from 'lucide-react';

/** Keyboard focus stays inside an open ARM dialog, then returns to its trigger. */
export function ArmDialog({title,onClose,children,className='',modal=true}:React.PropsWithChildren<{title:string,onClose:()=>void,className?:string,modal?:boolean}>){
 const side=['Учебный телефон ДДС','Учебный телефон 112','Управление обучением'].includes(title)?document.getElementById('student-side-panels'):null;
 if(side)modal=false;
 const ref=useRef<HTMLDivElement>(null);
 const close=useRef(onClose);close.current=onClose;
 useEffect(()=>{const previous=document.activeElement as HTMLElement;const el=ref.current;if(!el)return;
  const focusable=()=>Array.from(el.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]'));
  (focusable()[0]||el).focus();
  const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.stopPropagation();close.current();}if(modal&&e.key==='Tab'){const all=focusable();const first=all[0],last=all.at(-1);if(!first){e.preventDefault();el.focus();}else if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}};
  el.addEventListener('keydown',key);return()=>{el.removeEventListener('keydown',key);previous?.focus();};
 },[]);
 const content=<div className={(side?'side-dialog ':'arm-shade ')+className}><div ref={ref} className="arm-dialog" role="dialog" aria-modal={modal} aria-label={title} tabIndex={-1}><header><h2>{title}</h2><button title="Закрыть окно" onClick={onClose}><X size={20}/></button></header>{children}</div></div>;
 return createPortal(content,side||document.body);
}
export function TraitButtons({traits,value,onChange,disabled=false}:{traits:string[],value:string[],onChange:(v:string[])=>void,disabled?:boolean}){
 const groups:Record<string,string[]>={};
 for(const t of traits){const group=/^(улица|транспорт|дом|здание|опасный объект)$/i.test(t)?'Где':/дым|пламя|гарь|гари|сигнализац/i.test(t)?'Признак пожара':/квартир|балкон|мусоропровод|подъезд|электр|подвал|чердак/i.test(t)?'Объект':'Признаки происшествия';(groups[group]??=[]).push(t);}
 return <div className="arm-trait-groups">{Object.entries(groups).map(([label,items])=><div className="arm-trait-row" key={label}><span>{label}</span><div>{items.map(t=><button type="button" disabled={disabled} aria-pressed={value.includes(t)} className={value.includes(t)?'active':''} key={t} onClick={()=>onChange(value.includes(t)?value.filter(x=>x!==t):[...value,t])}>{t}</button>)}</div></div>)}</div>;
}
