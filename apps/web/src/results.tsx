import {ArmDialog} from './arm-ui';
import React, { useEffect, useState, useRef } from "react";
import { AIReview } from './ai';

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
  Radio,
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
export function Assessment({
  p,
  onUpdate,
}: {
  p: Obj;
  onUpdate?: (p: Obj) => void;
}) {
  const u = React.useContext(UserContext),
    [review, setReview] = useState<Obj>({}),
    [reason, setReason] = useState(""),
    [error, setError] = useState("");
  const [confirming,setConfirming]=useState(false),[saved,setSaved]=useState(''),[saving,setSaving]=useState(false);
  const [elapsed,setElapsed]=useState(0);
  useEffect(()=>{const t=setInterval(()=>setElapsed(x=>x+1),1000);return()=>clearInterval(t);},[p.id]);
  const a = p.assessment;
  const semantic=a.semantic_review;
  const needsAI=a.criteria.some((c:Obj)=>c.kind==='manual'&&c.passed===null&&!c.teacher_reviewed);
  const reportJob=a.report_job;
  const reportWaiting=reportJob&&reportJob.status!=='done';
  const aiWaiting=(needsAI&&(!semantic||['queued','running'].includes(semantic.status)))||reportWaiting;
  useEffect(()=>{if(!aiWaiting||!onUpdate)return;const timer=setInterval(()=>api('/attempts/'+p.id).then(onUpdate).catch(()=>{}),1000);return()=>clearInterval(timer);},[p.id,aiWaiting,onUpdate]);
  if(reportWaiting)return <div className="panel assessment assessment-loading" role="status" aria-live="polite"><h2>{reportJob.status==='error'?'Не удалось подготовить отчёт ИИ':'Анализ данных ИИ…'}</h2><p>{reportJob.status==='error'?reportJob.error:'Проверяем карточку, действия и телефонные разговоры. Результат появится автоматически.'}</p>{reportJob.status!=='error'?<div className="analysis-progress"><div className="analysis-track" aria-label="Анализ данных ИИ"/><p>{semantic?.status==='running'?'Проверяем реплики и комментарии по эталону':reportJob.status==='running'?'Формируем итог и рекомендации':'Ожидаем свободный вычислительный модуль'} · {elapsed} с</p><small>Можно закрыть окно: проверка продолжится в фоне.</small></div>:u.role!=='student'?<button onClick={async()=>{try{onUpdate?.(await api(`/ai/attempts/${p.id}/review`,'POST'));}catch(e:any){setError(e.message);}}}>Повторить анализ</button>:<p>Обратитесь к преподавателю для повторного запуска анализа.</p>}<Notice>{error}</Notice></div>;
  return (
    <div className="panel assessment">
      <div className="assessment-top">
        <div className="score-ring">
          {a.score ?? "—"}
          <small>из 100</small>
        </div>
        <div>
          <Badge tone={a.pending ? "amber" : a.passed ? "green" : "red"}>
            {a.pending
              ? "Ожидает проверки"
              : a.ai_preliminary ? "Предварительно · ИИ" : a.passed
                ? "Зачтено"
                : "Требуется повторение"}
          </Badge>
          <h2>
            {a.pending
              ? (aiWaiting?"Нейросеть проверяет комментарии":"Нужна проверка преподавателя")
              : a.ai_preliminary ? "Предварительная оценка ИИ" : a.passed
                ? "Задание выполнено"
                : "Разберите ошибки и попробуйте снова"}
          </h2>
          <p>
            {a.duration} сек. · Критических ошибок: {a.critical_errors} ·{" "}
            {a.pending
              ? "Балл предварительный: свободный текст ещё не оценён."
              : a.ai_preliminary ? "Комментарии оценены локальной моделью. Преподаватель может уточнить оценку." : "Проверка завершена."}
          </p>
        </div>
      </div>
      <p>{a.measurement||'Время выполнения'}: {a.measured_seconds??'—'} сек. · Норматив: {a.norm_seconds??p.task.limit_seconds} сек. · Отклонение: {a.deviation_seconds===null?'нет первичного решения':`${a.deviation_seconds>0?'+':''}${a.deviation_seconds??a.duration-p.task.limit_seconds} сек.`}</p>
      {a.assisted&&<Notice>{p.state.guided?'Пошаговое обучение с подсказками.':'Работа выполнена с помощью преподавателя.'} Не учитывается при расчёте самостоятельного уровня.</Notice>}
      {a.address_checks?.length>0&&<details open><summary>Точность адреса</summary>{a.address_checks.map((x:Obj,i:number)=><p key={i}>{x.message}: «{x.fragment}». Ожидалось: «{x.expected}».</p>)}</details>}
      {a.text_checks?.length>0&&<details><summary>Замечания к оформлению текста ({a.text_checks.length})</summary><p>Локальные правила. Не заменяют проверку смысла и грамматики преподавателем.</p>{a.text_checks.map((x:Obj,i:number)=><p key={i}>{x.message}: «{x.fragment}»</p>)}</details>}
      {semantic?.status==='error'&&<Notice>Не удалось оценить комментарии: {semantic.error}. Ошибка модели не считается ошибкой ученика.</Notice>}
      {needsAI&&!aiWaiting&&<button onClick={async()=>{try{onUpdate?.(await api(`/ai/attempts/${p.id}/analyze-comments`,'POST'));}catch(e:any){setError(e.message);}}}>Повторить анализ комментариев</button>}
      <details className="result-conversation"><summary>Телефонные разговоры ({(p.state.dialogue?.length||0)+(p.state.messages?.length||0)} реплик)</summary>{[...(p.state.dialogue||[]),...(p.state.messages||[])].map((m:Obj,i:number)=><article key={i}><b>{m.who||'Служба'}</b> <small>{m.at?new Date(m.at).toLocaleTimeString('ru'):''}</small><p>{m.text||m.message}</p></article>)}</details>
      <table>
        <thead>
          <tr>
            <th>Критерий</th>
            <th>Ваш результат</th>
            <th>Ожидается</th>
            <th>Проверка</th>
            {u.role !== "student" && <th>Оценка преподавателя</th>}
          </tr>
        </thead>
        <tbody>
          {a.criteria.map((c: Obj) => (
            <tr key={c.id}>
              <td>
                <b>{c.label}</b>
                {c.critical && (
                  <small className="critical">Критический критерий</small>
                )}
                <small>
                  {c.weight} баллов · {c.skill}
                </small>
              </td>
              <td>
                {c.id==='phone_conversation'?'Реплики сохранены. Откройте раздел «Телефонные разговоры» выше.':c.kind==='contact'?[...new Set((c.actual||[]).map((id:string)=>p.task.contacts?.find((contact:Obj)=>contact.id===id)?.name||id))].join(', '):typeof c.actual === "object"
                  ? Array.isArray(c.actual)?c.actual.join(" → "):JSON.stringify(c.actual)
                  : String(c.actual ?? "—")}
              </td>
              <td>
                {c.id==='phone_conversation'?'Уточнены необходимые сведения; адрес и обстоятельства переданы без искажений.':c.kind==='contact'?(p.task.contacts?.find((contact:Obj)=>contact.id===c.expected)?.name||c.expected):typeof c.expected === "object"
                  ? Array.isArray(c.expected)?c.expected.join(", "):JSON.stringify(c.expected)
                  : String(c.expected)}
              </td>
              <td>
                <Badge
                  tone={
                    c.passed === null ? "amber" : c.passed ? "green" : "red"
                  }
                >
                  {c.passed === null
                    ? "На проверке"
                    : c.credit===.5 ? "Частично · ИИ" : c.passed
                      ? "Верно"
                      : "Ошибка"}
                </Badge>
                {c.ai_evaluation&&<div className="semantic-explanation"><small>{c.teacher_reviewed?'Проверено преподавателем; первичный разбор ИИ:':'Первичная оценка локальной модели:'}</small><p>{c.ai_evaluation.reason}</p>{c.ai_evaluation.warning&&<small>{c.ai_evaluation.warning}</small>}{c.ai_evaluation.evidence&&<blockquote>«{c.ai_evaluation.evidence}»</blockquote>}<small>{c.teacher_reviewed?'':`Начислено: ${c.passed===null?'ожидает решения':Math.round(c.weight*(c.credit||0))+' из '+c.weight}`}</small></div>}
              </td>
              {u.role !== "student" && (
                <td>
                  <select aria-label={"Оценка: "+c.label}
                    value={
                      review[c.id] === undefined ? "" : String(review[c.id])
                    }
                    onChange={(e) => {
                      const next = { ...review };
                      if (e.target.value === "") delete next[c.id];
                      else next[c.id] = e.target.value === "true";
                      setReview(next);
                    }}
                  >
                    <option value="">Без изменения</option>
                    <option value="true">Зачесть</option>
                    <option value="false">Не зачесть</option>
                  </select>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {u.role !== 'student' && <AIReview p={p} onUpdate={onUpdate}/>}
      {u.role !== "student" && (
        <form
          className="review-form"
          onSubmit={e=>{e.preventDefault();setConfirming(true);}}
        >
          <input
            placeholder="Комментарий к проверке"
            aria-label="Комментарий к проверке"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <button className="primary" disabled={saving||a.criteria.some((c:Obj)=>c.passed===null&&review[c.id]===undefined)}>{Object.keys(review).length||reason.trim()?'Сохранить и подтвердить':'Подтвердить оценку'}</button>
        </form>
      )}
      {saved&&<p role="status">{saved}</p>}
      {confirming&&<ArmDialog className="review-confirmation" title="Подтверждение оценки" onClose={()=>setConfirming(false)}><p>{Object.keys(review).length?'Вы уверены, что оценка с вашими исправлениями верна по всем критериям?':'Вы уверены, что нейросеть и автоматическая проверка верно определили оценку по всем критериям этого задания?'}</p><p>Подтверждённые ответы сохранятся как примеры для проверки этого же вопроса. Окончательное решение всегда принимает преподаватель.</p><div className="toolbar"><button className="primary" disabled={saving} onClick={async()=>{setSaving(true);try{const next=await api(`/attempts/${p.id}/review`,'POST',{criteria:review,confirm:true,reason:reason.trim()||'Оценка по всем критериям подтверждена преподавателем.'});onUpdate?.(next);setReview({});setReason('');setConfirming(false);setSaved('Данные записаны в базу примеров для обучения ИИ по этим вопросам. Последнее слово остаётся за преподавателем.');}catch(e:any){setError(e.message);setConfirming(false);}finally{setSaving(false);}}}>Да, подтвердить</button><button disabled={saving} onClick={()=>setConfirming(false)}>Нет, вернуться к проверке</button></div></ArmDialog>}
      <Notice>{error}</Notice>
      {a.reviews.map((r: Obj, i: number) => (
        <div className="review-note" key={i}>
          <b>{r.by}</b> · {new Date(r.at).toLocaleString("ru")}
          <p>{r.reason}</p>
        </div>
      ))}
      {u.role!=='student'&&p.task.mode==='112'&&<button onClick={async()=>{try{const r=await api(`/attempts/${p.id}/reuse`,'POST');window.location.assign('/tickets/'+r.id);}catch(e:any){setError(e.message);}}}>Создать из этой карточки черновик задания ДДС</button>}
      <details>
        <summary>Эталон карточки и методическое примечание</summary>
        <p>{p.task.method_note}</p><p>{p.task.validation_note}</p>
        <dl className="reference-card">
          {Object.entries(p.task.expected_card).map(([k, v]: any) => (
            <React.Fragment key={k}>
              <dt>{labels[k] || k}</dt>
              <dd>{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
            </React.Fragment>
          ))}
        </dl>
      </details>
    </div>
  );
}

export function Results() {
  const user=React.useContext(UserContext);
  const { data, error, setData } = useLoad("/results", 3000),
    [student, setStudent] = useState(""),
    [opened, setOpened] = useState<number | null>(null);
  const filtered =
    data?.filter((p: Obj) => !student || p.student === student) || [];
  const failures: Obj = {};
  filtered.forEach((p: Obj) =>
    p.assessment.criteria.forEach((c: Obj) => {
      if (c.passed === false)
        failures[p.task.category] = (failures[p.task.category] || 0) + 1;
    }),
  );
  return (
    <div className="page">
      <Heading eyebrow="ОБРАТНАЯ СВЯЗЬ" title="Результаты и прогресс" />
      <Notice>{error}</Notice>
      <div className="toolbar">
        {user.role!=='student'&&<select
          aria-label="Фильтр по ученику"
          value={student}
          onChange={(e) => setStudent(e.target.value)}
        >
          <option value="">Все доступные ученики</option>
          {[...new Set(data?.map((p: Obj) => p.student) || [])].map(
            (s: any) => (
              <option key={s}>{s}</option>
            ),
          )}
        </select>}
        <span>{filtered.length} попыток</span><a className="button" href="/api/reports.csv">{user.role==='student'?'Скачать мой отчёт CSV':'Скачать отчёт CSV (все доступные)'}</a>
      </div>
      {Object.keys(failures).length > 0 && (
        <div className="panel trends">
          <h3>Темы, которым стоит уделить внимание</h3>
          <p>
            Количество незачтённых критериев. Это статистика попыток, а не вывод
            машинного обучения.
          </p>
          {Object.entries(failures)
            .sort((a: any, b: any) => b[1] - a[1])
            .map(([name, count]: any) => (
              <div className="bar-row" key={name}>
                <span>{name}</span>
                <div>
                  <i
                    style={{
                      width:
                        (count /
                          Math.max(...(Object.values(failures) as number[]))) *
                          100 +
                        "%",
                    }}
                  />
                </div>
                <b>{count}</b>
              </div>
            ))}
        </div>
      )}
      <div className="panel table-panel">
        <table>
          <thead>
            <tr>
              <th>Ученик / задание</th>
              <th>Режим</th>
              <th>Дата</th>
              <th>Балл</th>
              <th>Состояние</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.map((p: Obj) => (
              <React.Fragment key={p.id}>
                <tr>
                  <td>
                    <b>{p.student}</b>
                    <small>{p.task.title}</small>
                  </td>
                  <td>{p.task.mode === "112" ? "112" : "ДДС"}</td>
                  <td>{new Date(p.started_at).toLocaleDateString("ru")}</td>
                  <td>
                    <b>{p.assessment.score ?? "—"}%</b>
                  </td>
                  <td>
                    <Badge
                      tone={
                        p.assessment.pending
                          ? "amber"
                          : p.assessment.passed
                            ? "green"
                            : "red"
                      }
                    >
                      {p.assessment.pending
                        ? "На проверке"
                        : p.assessment.ai_preliminary ? "Предварительно · ИИ" : p.assessment.passed
                          ? "Зачтено"
                          : "Не зачтено"}
                    </Badge>
                  </td>
                  <td>
                    <button
                      className="small"
                      onClick={() => setOpened(opened === p.id ? null : p.id)}
                    >
                      Разбор
                    </button>
                    <Link className="text-button" to={"/attempts/" + p.id}>
                      Карточка
                    </Link>
                  </td>
                </tr>
                {opened === p.id && (
                  <tr>
                    <td colSpan={6}>
                      <Assessment
                        p={p}
                        onUpdate={(next) =>
                          setData(
                            data.map((x: Obj) =>
                              x.id === p.id
                                ? { ...next, student: p.student }
                                : x,
                            ),
                          )
                        }
                      />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
        {!filtered.length && <Empty text="Пока нет завершённых попыток" />}
      </div>
    </div>
  );
}
