import {VoiceDraft} from './voice';
import React, {useEffect, useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {X} from 'lucide-react';
import {api, Notice, Badge, useOperator112, type Obj} from './shared';
import {ticketStars, starLabel} from './ticket-difficulty';
import './tickets.css';

const EXAMPLES=[
  'Пожар в школе на улице Хачатуряна, дом 7. Из окон второго этажа идёт дым, двое пострадавших. Для оператора 112, сложность 4.',
  'Застрял лифт в жилом доме, внутри двое взрослых, пострадавших нет. Для диспетчера ДДС, 2 звезды.',
  'Запах газа в подъезде, жильцы жалуются на головную боль.',
];
const SOURCES:Record<string,[string,string]>={
  prompt:['из описания','green'],chosen:['выбрано вами','blue'],nearest:['ближайший тип','amber'],random:['случайно','amber'],default:['по умолчанию','light'],
  computed:['подобрано','blue'],generated:['написано моделью','blue'],template:['шаблон','amber'],
};
const MODES:Record<string,string>={dds:'Диспетчер службы',112:'Оператор 112'};
const VICTIMS:Record<string,string>={yes:'Есть',no:'Нет',unknown:'Пока неизвестно'};

function Source({kind}:{kind?:string}){
  const [label,tone]=SOURCES[kind||'']||['',''];
  return label?<Badge tone={tone}>{label}</Badge>:null;
}

/** Simplified authoring: one description → the server reads stated facts, fills the rest, the teacher reviews the preview. */
export function PromptDraft({onClose,onWizard}:{onClose:()=>void,onWizard:(initial:Obj)=>void}){
  const operator112=useOperator112();
  const nav=useNavigate();
  const [prompt,setPrompt]=useState('');
  const [result,setResult]=useState<Obj|null>(null);
  const [draft,setDraft]=useState<Obj|null>(null);
  const [busy,setBusy]=useState<''|'generate'|'save'>('');
  const [progress,setProgress]=useState(0);
  const [error,setError]=useState('');
  const [confirmClose,setConfirmClose]=useState(false);
  // A type picked among the nearest ones survives «Сгенерировать заново»; the list stays from the first answer.
  const [chosenType,setChosenType]=useState('');
  const [candidates,setCandidates]=useState<string[]>([]);
  const dirty=!!prompt.trim()||!!draft;
  const close=()=>{if(busy)return;if(dirty)setConfirmClose(true);else onClose();};
  useEffect(()=>{const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')close();};document.addEventListener('keydown',escape);return()=>document.removeEventListener('keydown',escape);},[busy,dirty]);
  useEffect(()=>{if(busy!=='generate'){setProgress(0);return;}const timer=window.setInterval(()=>setProgress(value=>(value+1)%3),4500);return()=>window.clearInterval(timer);},[busy]);
  const generate=async(incident_type='')=>{
    setBusy('generate');setError('');setChosenType(incident_type);
    try{const response=await api('/ai/prompt','POST',{prompt,incident_type});setResult(response);setDraft(response.data);if(!incident_type)setCandidates(response.meta?.candidates||[]);}
    catch(problem:any){setError(problem.message);}
    finally{setBusy('');}
  };
  const save=async()=>{
    if(!draft)return;
    setBusy('save');setError('');
    try{const saved=await api('/tickets','POST',draft);onClose();nav('/tickets/'+saved.id);}
    catch(problem:any){setError(problem.message);}
    finally{setBusy('');}
  };
  const meta=result?.meta||{},sources=meta.sources||{},slots=meta.slots||{};
  const task=draft?.tasks?.[0]||{};
  const card=task.mode==='112'?task.expected_card||{}:task.initial_card||{};
  const address=[card.city,card.street,card.house&&'дом '+card.house].filter(Boolean).join(', ')||'Уточняется в сценарии';
  const story=task.mode==='112'?task.intro:card.description;
  const rows:[string,React.ReactNode,string|undefined][]=draft?[
    ['Происшествие',(candidates.length>1||chosenType)?<select aria-label="Тип происшествия" value={slots.incident_type} disabled={!!busy} onChange={event=>void generate(event.target.value)}>{Array.from(new Set([slots.incident_type,...candidates])).map(title=><option key={title} value={title}>{title}</option>)}</select>:slots.incident_type,sources.incident_type],
    ...(operator112?[['Кого обучаем',MODES[task.mode]||task.mode,sources.mode] as [string,React.ReactNode,string|undefined]]:[]),
    ['Своя служба',task.own_service,sources.own_service],
    ['Получатели',(task.services||[]).join(' · '),sources.services],
    ['Сложность',<span><span className="ticket-difficulty">{starLabel(ticketStars(draft))}</span>{draft.difficulty_reason&&<small>{draft.difficulty_reason}</small>}</span>,sources.difficulty],
    ['Пострадавшие',VICTIMS[slots.victims_state]+(slots.victims_state==='yes'?`, ${slots.victims_count} чел.`:'')+(slots.animals?' · есть пострадавшие животные':''),slots.victims_state==='yes'&&sources.victims_count==='random'?'random':sources.victims],
    ['Адрес',address,sources.address],
    ['Объект',card.object,sources.object],
    ['Заявитель',card.name,sources.caller_name],
  ]:[];
  return <div className="ticket-wizard-overlay" role="presentation">
    {draft&&<VoiceDraft data={draft}/>}<section className="ticket-wizard prompt-draft" role="dialog" aria-modal="true" aria-labelledby="prompt-draft-title">
      <header><div><small>ИИ ассистент · билет по описанию</small><h2 id="prompt-draft-title">{draft?'Проверьте черновик':'Опишите происшествие'}</h2></div><button type="button" className="ticket-wizard-close" aria-label="Закрыть" onClick={close} disabled={!!busy}><X size={18}/></button></header>
      <div className="ticket-wizard-progress prompt-draft-progress" aria-hidden="true"><span className="active"/><span className={draft?'active':''}/></div>
      <div className="ticket-wizard-body"><Notice>{error}</Notice>
        {busy==='generate'&&<div className="ticket-wizard-working" role="status" aria-live="polite"><strong>Создаём учебную карточку</strong><p>{['Читаем описание происшествия…','Подбираем тип, службы и недостающие сведения…','Готовим доклады бригады и критерии…'][progress]}</p><div className="ticket-wizard-loading-track" aria-hidden="true"><span/></div><small>Модель работает локально. Это может занять до минуты.</small></div>}
        {confirmClose&&<div className="ticket-wizard-confirm" role="alertdialog" aria-label="Закрыть без сохранения?"><strong>Закрыть и потерять описание{draft?' и черновик':''}?</strong><div><button type="button" onClick={()=>setConfirmClose(false)} autoFocus>Нет, продолжить</button><button type="button" onClick={onClose}>Да, закрыть</button></div></div>}
        {!draft&&<>
          <label className="ticket-wizard-field">Что произошло?<textarea className="prompt-draft-input" value={prompt} maxLength={2000} rows={6} disabled={!!busy} autoFocus
            placeholder="Например: пожар в школе, двое пострадавших, сложность 4"
            onChange={event=>setPrompt(event.target.value)}
            onKeyDown={event=>{if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)&&prompt.trim().length>=5&&!busy){event.preventDefault();void generate();}}}/>
            <small className="prompt-draft-hint">Опишите своими словами: происшествие, место, пострадавших и сложность (1–5 звёзд). Что не указано, подберётся автоматически.</small></label>
          <div className="ticket-wizard-field"><span>Примеры</span><div className="prompt-draft-examples">{EXAMPLES.filter(example=>operator112||!example.includes('112')).map(example=><button type="button" key={example} disabled={!!busy} onClick={()=>setPrompt(example)}>{example}</button>)}</div></div>
        </>}
        {draft&&<>
          {(meta.warnings||[]).map((warning:string)=><p key={warning} className="prompt-draft-warning">{warning}</p>)}
          <label className="ticket-wizard-field">Название<input value={draft.title} maxLength={200} disabled={!!busy} onChange={event=>setDraft({...draft,title:event.target.value})}/></label>
          <dl className="prompt-draft-facts">{rows.map(([label,value,source])=><div key={label}><dt>{label}</dt><dd><span>{value||'—'}</span><Source kind={source}/></dd></div>)}</dl>
          <div className="ticket-wizard-preview"><strong>Сообщение</strong> <Source kind={sources.description}/><p>{story}</p></div>
          <p className="prompt-draft-request"><strong>Ваше описание:</strong> {prompt}</p>
          <p>Сохранится черновик. Перед публикацией проверьте его в редакторе.</p>
        </>}
      </div>
      <footer>{!draft?<>
        <button type="button" onClick={close} disabled={!!busy}>Отмена</button>
        <button type="button" className="primary" disabled={!!busy||prompt.trim().length<5} onClick={()=>void generate()}>{busy?'Создаём…':'Создать черновик'}</button>
      </>:<>
        <button type="button" onClick={()=>{setDraft(null);setResult(null);setError('');setChosenType('');setCandidates([]);}} disabled={!!busy}>Изменить описание</button>
        <button type="button" onClick={()=>void generate(chosenType)} disabled={!!busy}>{busy==='generate'?'Создаём…':'Сгенерировать заново'}</button>
        <button type="button" onClick={()=>onWizard({own_service:slots.own_service,services:slots.services,incident_type:slots.incident_type,mode:slots.mode,difficulty_stars:slots.difficulty_stars,victims_state:slots.victims_state,victims_count:slots.victims_count||1,animals:slots.animals,traits:slots.traits,address:sources.address==='prompt'?slots.address:''})} disabled={!!busy}>Уточнить в мастере</button>
        <button type="button" className="primary" disabled={!!busy||!draft.title?.trim()} onClick={save}>{busy==='save'?'Сохраняем…':'Открыть в редакторе'}</button>
      </>}</footer>
    </section>
  </div>;
}
