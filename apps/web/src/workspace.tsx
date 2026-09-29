import {submitAttempt} from './network-queue';
import {PhoneDock} from './phone-dock';
import {StudentPanel} from './student-panel';
import {TutorialCoach} from './tutorials';
import {BrigadeAudio,DDSVoiceCall} from './voice';
import {StudentHint} from './student-hint';
import {MiniDrill} from './training-tools';
import { TextCheck } from './shared';
import { AIQuestion, AIContact } from './ai';
import { DDSQueue } from './dds-queue';
import React, { useEffect, useState, useRef } from "react";

import {
  BrowserRouter,
  Routes,
  Route,
  Link,
  useNavigate,
  useParams,
  useLocation,
} from "react-router-dom";
import {
  LayoutDashboard,
  ClipboardList,
  Users,
  BarChart3,
  ShieldCheck,
  Settings,
  LogOut,
  Phone,
  PhoneOff,
  Play,
  Pause,
  Plus,
  Search,
  Check,
  ChevronRight,
  ArrowLeft,
  Bell,
  Save,
  HelpCircle,
  Radio, Pencil, X, ChevronUp, MessageSquare, Timer, List,
  FileText,
} from "lucide-react";

import {
  type Obj,
  uuid,
  api,
  UserContext,
  roleNames,
  statusNames,
  services,
  labels,
  useLoad,
  Notice,
  Badge,
  Field,
  Empty,
  Heading,
} from "./shared";
import {ArmDialog,TraitButtons} from './arm-ui';
import { Assessment } from "./results";
export function Workspace() {
  const nav=useNavigate();
  const { id } = useParams(),
    u = React.useContext(UserContext),
    { data: p, error, setData } = useLoad("/attempts/" + id, 2000);
  const [card, setCard] = useState<Obj>({}),
    [dirty, setDirty] = useState(false),
    [err, setErr] = useState(""),
    [busy, setBusy] = useState(false),
    [contactId, setContactId] = useState(""),
    [contactText, setContactText] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [service, setService] = useState(""),
    [tab, setTab] = useState("card"),
    [showEvents, setShowEvents] = useState(false),
    [phoneCollapsed, setPhoneCollapsed] = useState(false),
    [editingStatus,setEditingStatus]=useState(false),[addingService,setAddingService]=useState(false),[trainingMenu,setTrainingMenu]=useState(false);
  const {data:catalog}=useLoad('/learning/services');
  const dirtyRef = useRef(false);
  const dialogueRef = useRef<HTMLDivElement>(null);
  useEffect(()=>{const node=dialogueRef.current;if(node)node.scrollTop=node.scrollHeight;},[p?.state?.dialogue?.length]);
  const draftKey=`training112:draft:${u.id}:${id}`;
  const [savedDraft,setSavedDraft]=useState<Obj|null>(null);
  useEffect(()=>{dirtyRef.current=false;setDirty(false);setContactId('');setContactText('');setTab('card');setService('');setPhoneCollapsed(false);setEditingStatus(false);setSelected([]);try{setSavedDraft(JSON.parse(localStorage.getItem(draftKey)||'null'));}catch{setSavedDraft(null);}},[draftKey]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);
  useEffect(() => {
    if (p && !dirtyRef.current) setCard(p.card);
  }, [p?.revision, p?.id]);
  useEffect(()=>{if(!p||p.task.mode!=='112'||p.student_id!==u.id)return;let active=true;const t=setTimeout(()=>api('/attempts/'+p.id+'/routing-preview','POST',{incident_type:card.incident_type,traits:card.traits,victims:card.victims,description:card.description,object:card.object,district:card.district}).then(r=>{if(active)setSelected(r.services.filter((s:string)=>!p.state.services[s]));}).catch(()=>{}),180);return()=>{active=false;clearTimeout(t);};},[p?.id,card.incident_type,JSON.stringify(card.traits),card.victims,card.description,card.object,card.district]);
  const owner = p?.student_id === u.id,
    done = p && ["completed", "aborted"].includes(p.status);
  async function cmd(type: string, payload: Obj = {}, saveFirst = false) {
    if (!p) return;
    setBusy(true);
    setErr("");
    try {
      const next=await submitAttempt(u.id,id!,type,payload,saveFirst&&dirtyRef.current?card:undefined);
      if(!next)return;
      if(saveFirst&&dirtyRef.current){dirtyRef.current=false;setDirty(false);localStorage.removeItem(draftKey);setSavedDraft(null);}
      setData(next);
      if(type==='status'||type==='worklog')setEditingStatus(false);
      if(type==='notify')setSelected([]);
      if(type==='finish'&&next.state.lesson_id){const following=await api(`/lessons/${next.state.lesson_id}/next`,'POST');if(following.queue)nav('/lessons/'+following.lesson_id+'/queue');else if(following.finished)nav('/lessons');else nav('/attempts/'+following.id);}
      if (type === "draft") {
        dirtyRef.current = false;
        setDirty(false);
        localStorage.removeItem(draftKey);setSavedDraft(null);
      }
      return next;
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }
  function change(k: string, v: any) {
    setCard((c) => {const next={...c,[k]:v};try{localStorage.setItem(draftKey,JSON.stringify(next));}catch{setErr('Локальное сохранение недоступно. Сохраните карточку на сервер.');}return next;});
    dirtyRef.current = true;
    setDirty(true);
  }
  useEffect(()=>{const key=(e:KeyboardEvent)=>{if(document.querySelector('.mini-drill,.intro-gate'))return;if(e.ctrlKey&&e.key==='Enter'&&p?.state?.call==='ringing'&&owner&&!done){e.preventDefault();cmd('accept_call');}if(e.key==='Alt'){e.preventDefault();setTrainingMenu(true);}};document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key);});
  if (!p)
    return (
      <div className="page">
        <Notice>{error}</Notice>
        <p>Загрузка карточки…</p>
      </div>
    );
  const dds = p.task.mode === "dds",
    readOnly =
      dds || !owner || done || p.status === "ringing" || p.status === "paused";
  const field = (k: string, wide = false) => (
    <label className={"card-field " + (wide ? "span-all" : "")} key={k}>
      <span>{labels[k]}</span>
      <input
        data-field={k} value={card[k] || ""}
        disabled={readOnly}
        onChange={(e) => change(k, e.target.value)}
      />
    </label>
  );

  const address=[card.country,card.city,card.district&&`(${card.district}${card.area?', '+card.area:''})`,card.street,card.house,card.building&&'к. '+card.building,card.entrance&&'под. '+card.entrance].filter(Boolean).join(', ');
  const activeServices=dds?Object.keys(p.state.services):[...new Set([...Object.keys(p.state.services),...selected])];
  const time=(value:string)=>new Date(value).toLocaleTimeString('ru',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  const closeCard=()=>{if(!dirty||confirm('В карточке есть несохранённые изменения. Вернуться к списку? Локальный черновик сохранён.'))nav(u.role==='teacher'?'/journal':p.state.flow==='dds_stream'?'/lessons/'+p.state.lesson_id+'/queue':'/registry');};
  return <div className="student-station"><div className={'arm-work '+(dds?'arm-dds':'arm-112')}>
    <div className="arm-phone-row">
      <div className="arm-connection"><button className={(p.state.call==='ringing'||p.state.incoming_calls?.length)?'arm-ringing':''} title="Учебный телефон" onClick={()=>setPhoneCollapsed(false)}><Phone size={25}/>{p.state.incoming_calls?.length>0&&<sup>{p.state.incoming_calls.length}</sup>}</button><div><span>{p.state.call==='connected'?'соединение установлено':p.state.call==='ringing'?'входящий вызов':p.state.incoming_calls?.length?'входящий вызов':'не подключен'}</span><div><button onClick={()=>setPhoneCollapsed(false)}>история связи</button><button title="SMS не используются в текущих учебных сценариях" disabled>список SMS</button></div></div></div>
      {['phone','contact_phone','site_phone'].map((k,i)=><div className="arm-phone-cell" key={k}><div className="arm-phone-actions"><button title={'Связь: '+['АОН','предоставленный телефон','телефон на место'][i]} onClick={()=>{if(dds){const contact=p.task.contacts?.find((c:Obj)=>c.kind==='caller');if(contact)setContactId(contact.id);}setPhoneCollapsed(false);}}><Phone size={22}/></button><button disabled title="Сообщения по номеру: функция оригинального АРМ недоступна в тренажёре"><MessageSquare size={15}/></button></div><label><span>{['АОН','предоставленный','телефон на место'][i]}</span><input aria-label={labels[k]} value={card[k]||''} placeholder="+7 (   )   -  -" disabled={readOnly} onChange={e=>change(k,e.target.value)}/></label></div>)}
      <div className="arm-incident-meta"><b>Происшествие {p.id}</b><small>Сохр. {new Date(p.started_at).toLocaleString('ru')}</small><small>Опер. {p.state.operator_id||(!dds?p.student_id:'не указан')} · АРМ {p.state.arm_number||'не указан'}</small></div>
      {dds?<div className="arm-view-tabs"><button className={tab==='card'?'active':''} onClick={()=>setTab('card')}>просмотр</button><button className={tab==='journal'?'active':''} onClick={()=>setTab('journal')}>дополнение</button></div>:<div className="arm-clock">{Math.floor(p.duration/60).toString().padStart(2,'0')}:{(p.duration%60).toString().padStart(2,'0')}<small>минут　секунд</small></div>}
    </div>
    <Notice>{error||err}</Notice>{p.state.hint&&<StudentHint key={p.state.hints} target={'[data-guide="training"]'}><h2>Подсказка</h2><p>{p.state.hint}</p></StudentHint>}
    <div className="arm-card-body">
      <div className="arm-left-column">
        <div className="arm-caller-strip">{dds?<><b>{card.name||'Заявитель не указан'}</b><span>{card.caller_status}</span></>:<><input aria-label="Фамилия и имя заявителя" placeholder="Фамилия и имя заявителя" disabled={readOnly} value={card.name||''} onChange={e=>change('name',e.target.value)}/><select aria-label="Статус заявителя" disabled={readOnly} value={card.caller_status||''} onChange={e=>change('caller_status',e.target.value)}><option value="">выберите статус</option>{['очевидец','пострадавший','со слов третьих лиц','представитель организации'].map(s=><option key={s}>{s}</option>)}</select></>}</div>
        {dds?<div className="arm-address-read"><b>{address||'Адрес не указан'}</b>{card.address_note&&<p>{card.address_note}</p>}</div>:<div className="arm-address-edit"><div className="arm-address-summary"><small>Адрес:</small><div>{address||'Укажите адрес происшествия'}</div></div><div className="arm-address-fields">{['country','region','city','object','district','area','street','house','building','structure','apartment','entrance','floor','code','address_note'].map(k=>field(k,k==='address_note'))}</div><button className="arm-clear-address" disabled={readOnly} onClick={()=>{for(const k of ['country','region','city','object','district','area','street','house','building','structure','apartment','entrance','floor','code','address_note'])change(k,'');}}>очистить адрес</button></div>}
        <div className="arm-description">{dds?<p>{card.description}</p>:<label><span>Описание со слов заявителя</span><textarea aria-label="Описание со слов заявителя" placeholder="введите" maxLength={1999} disabled={readOnly} value={card.description||''} onChange={e=>change('description',e.target.value)}/><small>{(card.description||'').length} / 1999</small></label>}</div>
      </div>
      <div className="arm-right-column">
        <div className="arm-victim-strip">{dds?<span>Пострадавшие: <b>{{yes:'да',no:'нет',unknown:'неизвестно'}[card.victims as string]||'неизвестно'}</b></span>:<label>Пострадавшие<select aria-label="Пострадавшие" disabled={readOnly} value={card.victims||'unknown'} onChange={e=>change('victims',e.target.value)}><option value="unknown">нет данных</option><option value="yes">да</option><option value="no">нет</option></select></label>}{!dds&&card.victims==='yes'&&field('victims_count')}{dds?<><span>Отказ от скорой: {card.medical_refusal==='yes'?'да':'нет'}</span><span>Заблокированные: {card.blocked==='yes'?'да':'нет'}</span></>:<><button disabled={readOnly} aria-pressed={card.medical_refusal==='yes'} className={card.medical_refusal==='yes'?'active':''} onClick={()=>change('medical_refusal',card.medical_refusal==='yes'?'no':'yes')}>Нет на месте/<br/>Отказ от скорой</button><button disabled={readOnly} aria-pressed={card.blocked==='yes'} className={card.blocked==='yes'?'active':''} onClick={()=>change('blocked',card.blocked==='yes'?'no':'yes')}>Нет доступа/<br/>Заблокированные</button></>}</div>
        {!dds&&<div className="arm-call-flags">{[['no_contact','нет контакта'],['call_lost','срыв звонка']].map(([key,label])=><button key={key} disabled={readOnly} className={card[key]==='yes'?'active':''} aria-pressed={card[key]==='yes'} onClick={()=>change(key,card[key]==='yes'?'no':'yes')}>{label}</button>)}</div>}{!dds&&<div className="arm-type-picker"><select aria-label="Тип происшествия" disabled={readOnly} value={card.incident_type||''} onChange={e=>change('incident_type',e.target.value)}><option value="">добавить тип происшествия</option>{[...new Set([...(p.task.type_options||[]),...(card.incident_type?[card.incident_type]:[])])].map((v:any)=><option key={v}>{v}</option>)}</select></div>}
        <div className="arm-incident-block"><h3>{card.incident_type||'Тип происшествия не выбран'}</h3>{dds?<p><b>{card.traits?.join('. ')||card.description||'Дополнительные признаки не указаны'}</b></p>:<TraitButtons traits={p.task.traits||[]} value={card.traits||[]} disabled={readOnly} onChange={v=>change('traits',v)}/>}</div>
        {dds&&<><div className="arm-class-strip">Класс: <b>{card.incident_type||''}</b></div><div className="arm-class-strip">[ВИС] Класс: <b>{card.vis_class||''}</b></div></>}
      </div>
    </div>
    {tab==='journal'&&<div className="arm-communications"><b>Дополнения и история связи</b>{p.state.messages?.length?p.state.messages.map((m:Obj,i:number)=><div key={i}><time>{time(m.at)}</time><b>{m.who}</b><span>{m.text||m.message}</span></div>):<p>Дополнений пока нет.</p>}</div>}

    <div className={'arm-services '+(!dds?'orange':'')}>
      <span>Службы:</span><div className="arm-service-tiles">{activeServices.map((s:string)=><div className={'arm-service-tile '+(service===s?'active':'')} key={s}>
        <div className="arm-tile-tools"><button title={'История службы '+s} aria-expanded={service===s} onClick={()=>{setService(service===s?'':s);setEditingStatus(false);}}><ChevronUp size={15}/></button>{dds&&s===p.task.own_service&&owner&&!done&&<button title="Изменить статус своей службы" disabled={busy||p.status==='paused'} onClick={()=>{setService(s);setEditingStatus(true);}}><Pencil size={16}/></button>}{!dds&&!p.state.services[s]&&<button title={'Убрать службу '+s} onClick={()=>setSelected(selected.filter(v=>v!==s))}><X size={14}/></button>}</div>
        <button className="arm-tile-body" onClick={()=>{setService(service===s?'':s);setEditingStatus(false);}}><b>{s}</b><small>{p.state.services[s]?.at(-1)?time(p.state.services[s].at(-1).at)+' '+p.state.services[s].at(-1).status:'Не оповещена'}</small></button>
      </div>)}</div>
      {!dds&&owner&&!done&&<button className="arm-bar-icon" title="Добавить службу" disabled={readOnly} onClick={()=>setAddingService(true)}><Plus/></button>}
      <div className="arm-footer-actions">{!dds&&owner&&!done&&<button className="arm-save" disabled={busy||readOnly} onClick={()=>selected.length?cmd('notify',{services:selected},true):cmd('draft',card)}>СОХРАНИТЬ</button>}<button className="arm-bar-icon" title="Журнал реагирования" onClick={()=>{setShowEvents(true);}}><List/></button><button className="arm-bar-icon" title="Закрыть карточку" onClick={closeCard}><X size={28}/></button></div>
      {service&&!editingStatus&&<div className="arm-service-history">{catalog?.find((entry:Obj)=>entry.name===service)?.questions?.map((q:string,i:number)=><p key={i}>Уточните: {q}</p>)}<header><b>{service}</b><button title="Закрыть историю службы" onClick={()=>setService('')}><X size={17}/></button></header>{p.state.services[service]?.map((h:Obj,i:number)=><div key={i}><span>оп. {h.operator_id||'—'}　›　{time(h.at)}</span><b>{h.status}</b>{(h.unit||h.comment)&&<p>{h.unit} {h.comment}</p>}</div>)}{!p.state.services[service]?.length&&<p>Служба будет оповещена после сохранения карточки.</p>}</div>}
    </div>
    {editingStatus&&<ArmDialog title={'Статус реагирования · '+service} className="arm-status-shade" onClose={()=>setEditingStatus(false)}><form className="arm-status-form" onSubmit={async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.currentTarget));await cmd(data.status==='comment'?'worklog':'status',data);}}><select name="status" aria-label="Новый статус" required><option value="comment">Добавить комментарий · статус не меняется</option>{p.allowed_statuses.map((s:string)=><option key={s}>{s}</option>)}</select><input name="unit" aria-label="Номер наряда" placeholder="Номер наряда"/><input name="comment" aria-label="Комментарий" placeholder="Комментарий / причина отказа"/><button title="Сохранить статус" disabled={busy||!p.allowed_statuses.length}><Check/></button></form><Notice>{err}</Notice>{!p.allowed_statuses.length&&<p>Работа службы завершена.</p>}</ArmDialog>}
    {addingService&&<ArmDialog title="Добавить службу" onClose={()=>setAddingService(false)}><div className="arm-service-options">{[...new Set([...(catalog||[]).filter((s:Obj)=>s.active).map((s:Obj)=>s.name),...p.task.services])].map(s=><button key={s} disabled={!!p.state.services[s]} className={selected.includes(s)||p.state.services[s]?'active':''} onClick={()=>setSelected(selected.includes(s)?selected.filter(x=>x!==s):[...selected,s])}>{s}</button>)}</div><footer><button data-guide="apply-services" onClick={()=>setAddingService(false)}>применить</button></footer></ArmDialog>}
    {trainingMenu&&<ArmDialog title="Управление обучением" onClose={()=>setTrainingMenu(false)}><p>{p.task.title}</p><p>Роль: <b>{dds?'ДДС · '+p.task.own_service:'Оператор 112'}</b> · {statusNames[p.status]} · {p.duration} с</p><div className="arm-training-actions">{owner&&!done&&<>{p.state.training&&<><button onClick={()=>cmd('hint')}>Подсказка</button>{p.state.flow!=='dds_stream'&&<button onClick={()=>cmd(p.status==='paused'?'resume':'pause')}>{p.status==='paused'?'Продолжить':'Пауза'}</button>}</>}<button data-guide="finish" disabled={busy||p.status==='paused'} onClick={()=>cmd('finish',{},!dds)}>Завершить работу</button><button onClick={()=>{if(confirm('Прервать попытку? Она сохранится без оценки.'))cmd('abort');}}>Прервать попытку</button></>}{p.assessment&&<button onClick={()=>{setTrainingMenu(false);setTab('result');}}>Результат</button>}<button onClick={closeCard}>К списку происшествий</button></div><Notice>{err||p.state.hint}</Notice></ArmDialog>}
    {tab==='result'&&p.assessment&&<ArmDialog className="assessment-modal" title="Результат обучения" onClose={()=>setTab('card')}><Assessment p={p} onUpdate={setData}/></ArmDialog>}
    {showEvents&&<ArmDialog title="Журнал реагирования" onClose={()=>setShowEvents(false)}><table><thead><tr><th>Служба</th><th>Время</th><th>Статус</th><th>Наряд / комментарий</th></tr></thead><tbody>{Object.entries(p.state.services).flatMap(([s,h]:any)=>h.map((v:Obj,i:number)=><tr key={s+i}><td>{s}</td><td>{time(v.at)}</td><td>{v.status}</td><td>{v.unit} {v.comment}</td></tr>))}</tbody></table>{u.audit_access&&<AttemptEvents id={p.id}/>}</ArmDialog>}
  </div><aside className="student-side"><div className="student-side-scroll"><StudentPanel/>    {savedDraft&&owner&&!done&&!dds&&<div className="arm-draft">Есть локальный черновик. <button onClick={()=>{setCard(savedDraft);dirtyRef.current=true;setDirty(true);setSavedDraft(null);}}>Восстановить</button><button onClick={()=>{localStorage.removeItem(draftKey);setSavedDraft(null);}}>Удалить черновик</button></div>}
    {p.status==='paused'&&<div className="arm-draft">Тренировка приостановлена. <button onClick={()=>cmd('resume')}>Продолжить</button></div>}
    {p.state.stopped_by_teacher&&<div className="arm-draft">Занятие завершено преподавателем.</div>}
{p.state.preview&&<p className="preview-note">Самостоятельное прохождение преподавателя. Пока озвучка готовится, сообщения доступны текстом.</p>}<div className="arm-training-strip"><button data-guide="training" onClick={()=>setTrainingMenu(true)}>Обучение · {dds?'ДДС: '+p.task.own_service:'оператор 112'}</button><span>{p.task.title} · {statusNames[p.status]}{dirty?' · есть несохранённые изменения':''}</span>{p.state.flow==='dds_stream'&&<Link to={'/lessons/'+p.state.lesson_id+'/queue'}>Список происшествий</Link>}</div><div id="student-side-panels"/>{p.task.onboarding&&owner&&<TutorialCoach key={p.id} p={p} card={card} phoneOpen={!phoneCollapsed} editingStatus={editingStatus} contactId={contactId} contactText={contactText} selected={selected} trainingMenu={trainingMenu}/>}</div><PhoneDock key={p.id} p={p} owner={owner} busy={busy} contactId={contactId} setContactId={setContactId} contactText={contactText} setContactText={setContactText} cmd={cmd} onUpdate={setData} onOpen={()=>setPhoneCollapsed(false)}/></aside>{owner&&!done&&!p.task.onboarding&&!p.state.preview&&<MiniDrill attemptId={p.id}/>}</div>;
}
function AttemptEvents({ id }: { id: number }) {
  const { data } = useLoad(`/attempts/${id}/events`, 3000);
  return (
    <div className="panel events">
      <table>
        <thead>
          <tr>
            <th>Время</th>
            <th>Событие</th>
            <th>Данные</th>
          </tr>
        </thead>
        <tbody>
          {data?.map((e: Obj) => (
            <tr key={e.id}>
              <td>{new Date(e.at).toLocaleTimeString("ru")}</td>
              <td>{e.kind}</td>
              <td>
                <code>{JSON.stringify(e.data)}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
