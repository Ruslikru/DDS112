import {VoiceSettings,LiveVoice} from './voice';
import React, {useState} from 'react';
import {api, type Obj, useLoad, useOperator112, Notice, uuid} from './shared';
import {useNavigate} from 'react-router-dom';

/** Where the server sends class AI requests: its own model or the admitted PCs selected here. Admin-only API. */
export function AIExecution(){
  const {data,error,setData}=useLoad('/ai/status',4000),[err,setErr]=useState(''),[busy,setBusy]=useState(false);
  const {data:workers,error:workersError,load:reloadWorkers}=useLoad('/ai/workers',4000);
  async function execution(value:string, ids:string[]){setBusy(true);setErr('');try{setData(await api('/ai/execution','POST',{execution:value,worker_ids:ids}));await reloadWorkers();}catch(x:any){setErr(x.message);}finally{setBusy(false);}}
  const enabled=(workers||[]).filter((w:Obj)=>w.enabled&&w.approved).map((w:Obj)=>w.id);
  return <>
    <label>Где выполнять запросы класса <select aria-label="Где выполнять запросы класса" disabled={!data||!workers||busy} value={data?.execution||'server'} onChange={e=>execution(e.target.value,enabled)}><option value="server">На учебном сервере</option><option value="workstations">На выбранных ПК класса</option></select></label>
    {data?.execution==='workstations'&&<div className="ai-execution-workers"><p>Отметьте доверенные ПК с запущенным приложением. Они считают разборы, тексты и эталоны проверки своей локальной моделью (ЦП или ГПУ — по настройке ПК ниже; режим «Сервер» отключает вычисления на ПК). Если свободных ПК нет или вычисление не удалось, запрос выполнит сервер.</p>
      {workers?.map((w:Obj)=><label className="check-line" key={w.id}><input type="checkbox" disabled={busy||!w.approved} checked={w.enabled&&w.approved} onChange={e=>execution('workstations',e.target.checked?[...enabled,w.id]:enabled.filter((id:string)=>id!==w.id))}/> ПК {w.number} · {!w.approved?'ожидает допуска':w.busy?'вычисляет':w.online&&w.available?'готов к вычислениям':'локальная модель не подключена'}</label>)}
      {!workers?.length&&<p>Сначала подключите и допустите рабочие места.</p>}</div>}
    <Notice>{error||workersError||err}</Notice>
  </>;
}

export function AISettings(){
  const {data,error,setData}=useLoad('/ai/status',4000),[err,setErr]=useState(''),[busy,setBusy]=useState(false);
  return <><VoiceSettings/><section className="panel form-panel"><h2>Локальная текстовая нейросеть</h2><p><strong>География сценариев: Москва.</strong> Районы, округа и улицы выбираются из московского справочника. Обстоятельства и заявители создаются для учебного сценария.</p><Notice>{error||err}</Notice>
    <p>{data?.available?'Установлена':'Файлы модели не найдены'} · {data?.busy?'Обрабатывает запрос':data?.running?'Готова':'Запустится при первом запросе'}</p>
    <label>Вычисления на сервере <select disabled={!data||busy} value={data?.mode||'cpu'} onChange={async e=>{setBusy(true);setErr('');try{setData(await api('/ai/mode','POST',{mode:e.target.value}));}catch(x:any){setErr(x.message);}finally{setBusy(false);}}}>
      <option value="cpu">CPU — процессор</option><option value="gpu" disabled={!data?.gpu_available}>GPU — видеокарта Vulkan</option></select></label>
    <AIExecution/>
    <p>Телефоны используют вычисления класса. Для GPU нужен драйвер с поддержкой Vulkan. Обе модели работают без интернета; итоговую оценку подтверждает преподаватель.</p>
  </section></>;
}

export function AIDraft(){
  const operator112=useOperator112();
  const nav=useNavigate(),[topic,setTopic]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [mode,setMode]=useState('dds'),[query,setQuery]=useState(''),[incident,setIncident]=useState(''),[ownService,setOwnService]=useState('ДДС района'),[recipients,setRecipients]=useState(''),[district,setDistrict]=useState(''),[affiliation,setAffiliation]=useState('');
  const {data:types}=useLoad('/classifier?q='+encodeURIComponent(query));
  return <details className="panel form-panel"><summary>Создать ситуацию с нейросетью</summary>
    <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{const draft=await api('/ai/generate','POST',{topic,mode:operator112?mode:'dds',incident_type:incident,own_service:ownService,services:recipients.split('\n').filter(Boolean),district,affiliation});const saved=await api('/tickets','POST',draft.data);nav('/tickets/'+saved.id);}catch(x:any){setError(x.message);}finally{setBusy(false);}}}>
      <p>ДДС: заполненная карточка, контакты, доклады бригады и критерии. Преподаватель проверяет согласованность и утверждает черновик перед назначением.</p>
      {operator112&&<label>Режим обучения<select value={mode} onChange={e=>setMode(e.target.value)}><option value="dds">Диспетчер ДДС — реагирование</option><option value="112">Оператор 112 — опрос и заполнение</option></select></label>}
      {(!operator112||mode==='dds')&&<div className="form-grid"><label>Поиск типа происшествия<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Например: вода"/></label>
        <label>Тип из классификатора<select required value={incident} onChange={e=>setIncident(e.target.value)}><option value="">Выберите тип</option>{incident&&!types?.some((t:Obj)=>t.title===incident)&&<option>{incident}</option>}{types?.map((t:Obj)=><option key={t.code} value={t.title}>{t.title}</option>)}</select></label>
        <label>Своя ДДС<input required value={ownService} onChange={e=>setOwnService(e.target.value)}/></label><label>Район обслуживания<input required value={district} onChange={e=>setDistrict(e.target.value)} placeholder="Щукино"/></label>
        <label>Подчинённость объекта<input value={affiliation} onChange={e=>setAffiliation(e.target.value)} placeholder="Например: Департамент образования"/></label><label>Другие получатели карточки<textarea value={recipients} onChange={e=>setRecipients(e.target.value)} placeholder="По одной службе на строку; определяет преподаватель"/></label></div>}
      <label>Какая ситуация нужна?<textarea value={topic} onChange={e=>setTopic(e.target.value)} minLength={5} maxLength={600} required placeholder="ДТП во дворе, один пострадавший; заявитель растерян" /></label>
      <Notice>{error}</Notice><button disabled={busy} className="primary">{busy?'Создание черновика…':'Подготовить черновик'}</button>
      {busy&&<span role="status"> На CPU это может занять около минуты.</span>}
    </form></details>;
}

export function AIContact({p,contactId,text,onUpdate}:{p:Obj,contactId:string,text:string,onUpdate:(p:Obj)=>void}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 return <div><button disabled={busy||text.trim().length<3||p.status==='paused'} onClick={async()=>{setBusy(true);setError('');try{
   const latest=await api('/attempts/'+p.id);
   onUpdate(await api(`/ai/attempts/${p.id}/contact`,'POST',{text,contact_id:contactId,revision:latest.revision,command_id:uuid()}));
 }catch(e:any){setError(e.message);}finally{setBusy(false);}}}>{busy?'Обработка вопроса…':'Спросить своими словами · ИИ'}</button><Notice>{error}</Notice></div>;
}

export function AIQuestion({p,onUpdate,textOnly=false}:{p:Obj,onUpdate:(p:Obj)=>void,textOnly?:boolean}){
  const [text,setText]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  return <>{!textOnly&&<LiveVoice key={p.id} p={p} onUpdate={onUpdate}/>}<form className="ai-question" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{
    const latest=await api('/attempts/'+p.id);
    onUpdate(await api(`/ai/attempts/${p.id}/question`,'POST',{text,revision:latest.revision,command_id:uuid()}));setText('');
  }catch(x:any){setError(x.message);}finally{setBusy(false);}}}>
    <label>Спросить своими словами<textarea required minLength={3} maxLength={500} value={text} onChange={e=>setText(e.target.value)} placeholder="Как я могу к вам обращаться?" disabled={busy||p.status==='paused'} /></label>
    <button disabled={busy||p.status==='paused'}>{busy?'Обработка вопроса…':'Спросить заявителя'}</button><Notice>{error}</Notice>
  </form></>;
}

export function AIReview({p,onUpdate}:{p:Obj,onUpdate?:(p:Obj)=>void}){
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<Obj|null>(null);
  const review=result?.assessment?.ai_review||p.assessment?.ai_review;
  return <section className="ai-review"><h3>Разбор нейросети</h3><p>Рекомендация для преподавателя. Итоговый балл не меняется автоматически.</p>
    <button disabled={busy||p.assessment?.report_job?.status==='running'} onClick={async()=>{setBusy(true);setError('');try{const next=await api(`/ai/attempts/${p.id}/review`,'POST');setResult(next);onUpdate?.(next);}catch(x:any){setError(x.message);}finally{setBusy(false);}}}>{busy?'Анализ результата…':review?'Обновить разбор':'Запустить анализ'}</button>
    <Notice>{error}</Notice>{review&&<><p>{review.summary}</p><p>{review.recommendation}</p></>}
  </section>;
}
