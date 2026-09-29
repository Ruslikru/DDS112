import {VoiceDraft} from './voice';
import React, {useEffect, useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {X} from 'lucide-react';
import {api, useLoad, Notice, type Obj} from './shared';
import {ticketStars,legacyDifficulty,starLabel} from './ticket-difficulty';
import './tickets.css';

const serviceLabels:Record<string,string>={
  'Служба 101':'Пожарная · 101',
  'Служба 102':'Полиция · 102',
  'Служба 103':'Скорая · 103',
  'ДДС района':'Районная ДДС',
};
const difficultyHints=['Все сведения сразу, больше времени','Адрес известен, остальные сведения нужно уточнить','Самостоятельный сбор сведений','Неполный адрес и дополнительные уточнения','Неполные сведения, задержка бригады и координация'];
const genericTopics=new Set(['пострадавшие','скорая помощь','полиция']);
function incidentSigns(title:string, source:string[]=[]):string[]{
  const topic=title.trim().toLocaleLowerCase();
  const result=source.filter(sign=>!new Set([topic,'дтп','дтп пострадавшие','сход трамвая с рельс','есть пострадавшие','нет пострадавших']).has(sign.trim().toLocaleLowerCase()));
  if(topic.includes('трамва'))result.push('Повреждены провода контактной сети','Вагон перекрыл проезжую часть');
  return Array.from(new Set(result));
}

export function DraftWizard({onClose}:{onClose:()=>void}){
  const nav=useNavigate();
  const [confirmClose,setConfirmClose]=useState(false);
  const [suggested,setSuggested]=useState<string[]>([]);
  const [step,setStep]=useState(0);
  const [query,setQuery]=useState('');
  const [searchOpen,setSearchOpen]=useState(false);
  const [busy,setBusy]=useState(false);
  const [progressStep,setProgressStep]=useState(0);
  const [error,setError]=useState('');
  const [availableTraits,setAvailableTraits]=useState<string[]>([]);
  const [draft,setDraft]=useState<Obj|null>(null);
  const [form,setForm]=useState<Obj>({difficulty_stars:3,mode:'dds',incident_type:'',victims_state:'unknown',victims_count:1,animals:false,own_service:'ДДС района',services:['ДДС района'],traits:[]});
  const {data:types}=useLoad('/classifier?q='+encodeURIComponent(query));
  const {data:catalog}=useLoad('/learning/services');
  const services=(catalog||[]).filter((item:Obj)=>item.active);
  const selected=services.find((item:Obj)=>item.name===form.own_service);
  const tags=Array.from(new Set((selected?.tags||[]).map((tag:string)=>tag.trim()).filter((tag:string)=>tag.length>=3&&!genericTopics.has(tag.toLocaleLowerCase())))) as string[];
  useEffect(()=>{if(services.length&&!selected)setForm(current=>({...current,own_service:services[0].name,services:[services[0].name],incident_type:''}));},[catalog]);
  useEffect(()=>{const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!busy)setConfirmClose(true);};document.addEventListener('keydown',escape);return()=>document.removeEventListener('keydown',escape);},[busy,onClose]);
  useEffect(()=>{if(!busy||step!==2){setProgressStep(0);return;}const timer=window.setInterval(()=>setProgressStep(value=>(value+1)%3),4500);return()=>window.clearInterval(timer);},[busy,step]);
  useEffect(()=>{let active=true;api('/learning/services/suggest','POST',{incident_type:form.incident_type,traits:form.traits,victims:form.victims_state}).then(result=>{if(active)setSuggested(result.services);}).catch(()=>{if(active)setError('Не удалось подобрать службы. Проверьте получателей перед созданием.');});return()=>{active=false;};},[form.incident_type,JSON.stringify(form.traits),form.victims_state]);
  const recipients=Array.from(new Set([...form.services,...suggested]));
  const field=(key:string,value:any)=>setForm(current=>({...current,[key]:value}));
  const chooseService=(name:string)=>{setAvailableTraits([]);setQuery('');setSearchOpen(false);setForm(current=>({...current,own_service:name,services:[name],incident_type:'',traits:[]}));};
  const chooseType=(title:string,traits:string[]=[])=>{setAvailableTraits(incidentSigns(title,traits));setQuery(title);setSearchOpen(false);setForm(current=>({...current,incident_type:title,traits:[]}));};
  useEffect(()=>{if(!form.incident_type)return;let active=true;api('/classifier?q='+encodeURIComponent(form.incident_type)).then(items=>{if(active){const exact=items.find((item:Obj)=>item.title.trim().toLocaleLowerCase()===form.incident_type.trim().toLocaleLowerCase());setAvailableTraits(incidentSigns(form.incident_type,exact?.traits||[]));}}).catch(()=>{});return()=>{active=false;};},[form.incident_type]);
  const generate=async()=>{
    setBusy(true);setError('');
    try{const result=await api('/ai/wizard','POST',{...form,services:recipients});setDraft(result.data);setStep(3);}
    catch(problem:any){setError(problem.message);}
    finally{setBusy(false);}
  };
  const save=async()=>{
    if(!draft)return;
    setBusy(true);setError('');
    try{const saved=await api('/tickets','POST',draft);onClose();nav('/tickets/'+saved.id);}
    catch(problem:any){setError(problem.message);}
    finally{setBusy(false);}
  };
  const titles=['Основа билета','Пострадавшие','Получатели карточки','Проверьте черновик'];
  return <div className="ticket-wizard-overlay" role="presentation">
    {draft&&<VoiceDraft data={draft}/>}<section className="ticket-wizard" role="dialog" aria-modal="true" aria-labelledby="ticket-wizard-title">
      <header><div><small>ИИ ассистент · шаг {step+1} из 4</small><h2 id="ticket-wizard-title">{titles[step]}</h2></div><button type="button" className="ticket-wizard-close" aria-label="Закрыть" onClick={()=>setConfirmClose(true)} disabled={busy}><X size={18}/></button></header>
      <div className="ticket-wizard-progress" aria-hidden="true">{titles.map((title,index)=><span key={title} className={index<=step?'active':''}/>)}</div>
      <div className="ticket-wizard-body"><Notice>{error}</Notice>{busy&&step===2&&<div className="ticket-wizard-working" role="status" aria-live="polite"><strong>Создаём учебную карточку</strong><p>{['Собираем обстоятельства происшествия…','Проверяем сведения и службы…','Готовим доклады бригады и критерии…'][progressStep]}</p><div className="ticket-wizard-loading-track" aria-hidden="true"><span/></div><small>Модель работает локально. Это может занять некоторое время.</small></div>}{confirmClose&&<div className="ticket-wizard-confirm" role="alertdialog" aria-label="Сбросить прогресс?"><strong>Закрыть создание билета и сбросить прогресс?</strong><div><button type="button" onClick={()=>setConfirmClose(false)} autoFocus>Нет, продолжить</button><button type="button" onClick={onClose}>Да, закрыть</button></div></div>}
        {step===0&&<>
          <label className="ticket-wizard-field">Для какой службы создаём билет?<select value={form.own_service} onChange={event=>chooseService(event.target.value)}>{services.map((item:Obj)=><option key={item.name} value={item.name}>{serviceLabels[item.name]||item.name}</option>)}</select></label>
          <div className="ticket-wizard-field"><span>Какое происшествие?</span>{tags.length>0&&<div className="ticket-wizard-tags">{tags.map(tag=><button type="button" key={tag} className={form.incident_type===tag?'selected':''} onClick={()=>chooseType(tag)}>{tag}</button>)}</div>}<div className="ticket-wizard-search"><input aria-label="Происшествие" placeholder="Или найдите происшествие по названию" value={query} onFocus={()=>setSearchOpen(true)} onChange={event=>{setQuery(event.target.value);setSearchOpen(true);setAvailableTraits([]);setForm(current=>({...current,incident_type:'',traits:[]}));}}/>{searchOpen&&query.trim().length>=2&&<div className="ticket-wizard-results">{types?.slice(0,8).map((item:Obj)=><button type="button" key={item.code} onClick={()=>chooseType(item.title,(item.traits||[]).filter(Boolean))}>{item.title}</button>)}{types?.length===0&&<p>Совпадений нет.</p>}</div>}</div></div>
          {availableTraits.length>0&&<div className="ticket-wizard-field"><span>Дополнительные признаки</span><div className="ticket-wizard-tags">{availableTraits.map(tag=><button type="button" key={tag} className={form.traits.includes(tag)?'selected':''} onClick={()=>field('traits',form.traits.includes(tag)?form.traits.filter((value:string)=>value!==tag):[...form.traits,tag])}>{tag}</button>)}</div></div>}
          <label className="ticket-wizard-field">Сложность будущего билета<select value={form.difficulty_stars} onChange={e=>field('difficulty_stars',Number(e.target.value))}>{[1,2,3,4,5].map(n=><option value={n} key={n}>{starLabel(n)}</option>)}</select><small>{difficultyHints[form.difficulty_stars-1]}</small></label>
          <label className="ticket-wizard-field">Кого обучаем?<select value={form.mode} onChange={event=>field('mode',event.target.value)}><option value="dds">Диспетчер службы</option><option value="112">Оператор 112</option></select></label>
        </>}
        {step===1&&<><p>Укажите только известные сведения. Остальное ученик уточнит в ходе сценария.</p><div className="ticket-wizard-tags">{[['unknown','Пока неизвестно'],['no','Нет'],['yes','Есть']].map(([value,label])=><button type="button" key={value} className={form.victims_state===value?'selected':''} onClick={()=>field('victims_state',value)}>{label}</button>)}</div>{form.victims_state==='yes'&&<label className="ticket-wizard-field">Сколько человек?<input type="number" min={1} max={10000} value={form.victims_count} onChange={event=>field('victims_count',Number(event.target.value))}/></label>}<label className="ticket-wizard-checkbox"><input type="checkbox" checked={form.animals} onChange={event=>field('animals',event.target.checked)}/>Есть пострадавшие животные</label></>}
        {step===2&&<><p>Адрес и район Москвы подставятся автоматически. Получатели подобраны по признакам происшествия и сведениям о пострадавших.</p><div className="ticket-wizard-field"><span>Получат учебную карточку</span><div className="ticket-wizard-chosen">{recipients.map((name:string)=><button type="button" key={name} disabled={busy||name===form.own_service||suggested.includes(name)} title={name===form.own_service||suggested.includes(name)?'Подобрана по фактам сценария':'Убрать службу'} onClick={()=>field('services',form.services.filter((value:string)=>value!==name))}>{serviceLabels[name]||name}{name!==form.own_service&&!suggested.includes(name)?' ×':''}</button>)}</div><select aria-label="Добавить службу" value="" disabled={busy} onChange={event=>{if(event.target.value)field('services',[...form.services,event.target.value]);}}><option value="">Добавить ещё службу…</option>{services.filter((item:Obj)=>!recipients.includes(item.name)).map((item:Obj)=><option key={item.name} value={item.name}>{serviceLabels[item.name]||item.name}</option>)}</select></div></>}
        {step===3&&draft&&<><label className="ticket-wizard-field">Название<input value={draft.title} maxLength={200} onChange={event=>setDraft({...draft,title:event.target.value})}/></label><div className="ticket-wizard-field"><span>Сложность</span><strong>{starLabel(ticketStars(draft))}</strong><small>{draft.difficulty_reason}</small><button type="button" onClick={()=>setStep(0)}>Изменить сложность и создать заново</button></div><div className="ticket-wizard-preview"><strong>Сообщение</strong><p>{draft.tasks[0].initial_card.description||draft.tasks[0].intro}</p><strong>Службы</strong><p>{draft.tasks[0].services.map((name:string)=>serviceLabels[name]||name).join(' · ')}</p></div><p>Сохранится черновик. Перед публикацией проверьте его в редакторе.</p></>}
      </div>
      <footer><button type="button" onClick={step===0?()=>setConfirmClose(true):()=>setStep(step-1)} disabled={busy}>{step===0?'Отмена':'Назад'}</button>{step<2?<button type="button" className="primary" disabled={step===0&&!form.incident_type||busy} onClick={()=>setStep(step+1)}>Далее</button>:step===2?<button type="button" className="primary" disabled={busy||!form.services.length} onClick={generate}>{busy?'Создаём…':'Создать черновик'}</button>:<button type="button" className="primary" disabled={busy||!draft?.title?.trim()} onClick={save}>{busy?'Сохраняем…':'Открыть в редакторе'}</button>}</footer>
    </section>
  </div>;
}
