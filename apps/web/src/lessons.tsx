import {ManagementConfirm} from './management';
import {ReportDownload} from './report-download';
import React, {useContext, useState} from 'react';
import {Link, useNavigate} from 'react-router-dom';
import {api, UserContext, useLoad, Heading, Notice, Badge, Field, type Obj, statusNames} from './shared';
export function Lessons(){
 const u=useContext(UserContext), {data,error,load}=useLoad('/lessons',3000), nav=useNavigate();
 const [ending,setEnding]=useState<number|null>(null);
 const [show,setShow]=useState(false), [err,setErr]=useState(''), [busy,setBusy]=useState(false);
 async function action(id:number,verb:string){setBusy(true);setErr('');try{const r=await api(`/lessons/${id}/${verb}`,'POST');if(verb==='next'){if(r.queue)nav('/lessons/'+r.lesson_id+'/queue');else if(r.finished)setErr('Все карточки выполнены. Ожидайте завершения занятия преподавателем.');else nav('/attempts/'+r.id);}load();}catch(e:any){setErr(e.message);}finally{setBusy(false);}}
 return <div className="page lessons-page"><Heading eyebrow="УПРАВЛЕНИЕ ОБУЧЕНИЕМ" title="Занятия">{u.role!=='student'&&<button className="primary" onClick={()=>u.role==='teacher'?nav('/classroom/modes'):setShow(!show)}>Подготовить занятие</button>}</Heading><Notice>{error||err}</Notice>
 {show&&<LessonForm done={()=>{setShow(false);load();}}/>}
 {!data?.length&&<div className="panel form-panel">Занятий пока нет. Отдельные билеты доступны в разделе «Назначения».</div>}
 {data?.map((l:Obj)=><section key={l.id} className="panel form-panel lesson-panel"><div className="section-title"><div><Badge tone={l.status==='active'?'green':''}>{{prepared:'Подготовлено',active:'Идёт занятие',ended:'Завершено'}[l.status as string]}</Badge><h2>{l.title}</h2><p>{l.training?'Тренировка':'Экзамен'} · {l.categories.join(', ')||'Все выбранные категории'}</p></div><div className="actions">
 {u.role==='student'?l.status==='active'&&<button disabled={busy} className="primary" onClick={()=>action(l.id,'next')}>Продолжить занятие</button>:<>{l.status==='prepared'&&<button disabled={busy} className="primary" onClick={()=>action(l.id,'start')}>Начать занятие</button>}{l.status==='active'&&<button disabled={busy} onClick={()=>setEnding(l.id)}>Завершить для всех</button>}<ReportDownload url={'/api/reports.csv?lesson_id='+l.id} name="training-report.csv">Отчёт CSV</ReportDownload></>}
 </div></div><table><thead><tr><th>Ученик</th><th>Выполнено</th><th>Карточки и наблюдение</th></tr></thead><tbody>{l.members.map((m:Obj)=><tr key={m.id}><td>{m.name}</td><td>{['adaptive','sprint'].includes(l.delivery_mode)?<>Готово: {m.completed}<small>В работе: {m.attempts.filter((p:Obj)=>!['completed','aborted'].includes(p.status)).length}</small></>:<>{m.completed} / {m.total}<progress max={m.total} value={m.completed}/></>}</td><td>{m.attempts.length?m.attempts.map((p:Obj)=><div className="lesson-attempt-row" key={p.id}><Link className="button" to={'/attempts/'+p.id}>{p.title}</Link> · {statusNames[p.status]}{p.score!==null&&` · ${p.score}%`}</div>):'Ожидает начала'}</td></tr>)}</tbody></table></section>)}
 {ending!==null&&<ManagementConfirm title="Завершить занятие?" description="Текущие карточки будут сохранены и оценены в их нынешнем состоянии." confirmLabel="Завершить занятие" onCancel={()=>setEnding(null)} onConfirm={()=>{action(ending,'stop');setEnding(null);}}/>}</div>;
}
function LessonForm({done}:{done:()=>void}){
 const {data:users}=useLoad('/users'),{data:tickets}=useLoad('/tickets');
 const [students,setStudents]=useState<number[]>([]),[versions,setVersions]=useState<number[]>([]),[categories,setCategories]=useState<string[]>([]),[title,setTitle]=useState('Практическое занятие'),[training,setTraining]=useState(true),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [delivery,setDelivery]=useState('dds_stream'),[interval,setInterval]=useState(60);
 const published=(tickets||[]).filter((v:Obj)=>v.published&&!v.archived);
 const allCategories=[...new Set(published.filter((v:Obj)=>versions.includes(v.id)).flatMap((v:Obj)=>v.data.tasks.map((t:Obj)=>t.category)))] as string[];
 function toggle<T,>(list:T[],value:T){return list.includes(value)?list.filter(x=>x!==value):[...list,value];}
 return <form className="panel form-panel" onSubmit={async e=>{e.preventDefault();setBusy(true);try{await api('/lessons','POST',{title,students,versions,categories:categories.filter(x=>allCategories.includes(x)),training,random_order:true,delivery_mode:delivery,arrival_interval_seconds:interval});done();}catch(e:any){setError(e.message);}finally{setBusy(false);}}}>
 <h2>Подготовка занятия</h2><p>Выберите учеников и утверждённые билеты. Для каждого ученика порядок карточек перемешивается и сохраняется. Начало и окончание контролирует преподаватель.</p><Notice>{error}</Notice>
 <Field label="Название занятия"><input required minLength={3} value={title} onChange={e=>setTitle(e.target.value)}/></Field>
 <div className="form-grid"><Field label="Поступление заданий"><select value={delivery} onChange={e=>setDelivery(e.target.value)}><option value="dds_stream">Поток карточек ДДС</option><option value="sequential">Последовательно — 112 или разбор ДДС</option></select></Field>{delivery==='dds_stream'&&<Field label="Интервал поступления, секунд"><input type="number" min={5} max={3600} required value={interval} onChange={e=>setInterval(Number(e.target.value))}/></Field>}</div>
 {delivery==='dds_stream'&&<p>Выбирайте только билеты ДДС. Первая карточка поступает при запуске занятия, остальные — с заданным интервалом. Норматив идёт и у карточек в очереди; индивидуальная пауза отключена.</p>}
 <div className="form-grid"><div><h3>Участники</h3>{users?.filter((s:Obj)=>s.role==='student'&&s.active).map((s:Obj)=><label className="choice-line" key={s.id}><input type="checkbox" checked={students.includes(s.id)} onChange={()=>setStudents(toggle(students,s.id))}/>{s.name}</label>)}</div>
 <div><h3>Билеты</h3>{published.map((v:Obj)=><label className="choice-line" key={v.id}><input type="checkbox" checked={versions.includes(v.id)} onChange={()=>setVersions(toggle(versions,v.id))}/>{v.data.title} · v{v.number} · {v.data.difficulty}</label>)}</div>
 <div><h3>Категории</h3><small>Без отметок — все категории выбранных билетов.</small>{allCategories.map(c=><label className="choice-line" key={c}><input type="checkbox" checked={categories.includes(c)} onChange={()=>setCategories(toggle(categories,c))}/>{c}</label>)}</div></div>
 <label className="choice-line"><input type="checkbox" checked={training} onChange={e=>setTraining(e.target.checked)}/>Тренировка с паузой и подсказками (снимите для экзамена)</label><button disabled={busy||!students.length||!versions.length} className="primary">Сохранить подготовку</button>
 </form>;
}
