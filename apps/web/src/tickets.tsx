import {ArmDialog} from './arm-ui';
import {VoiceDraft} from './voice';
import { TextCheck } from './shared';
import { DraftWizard as AIDraft } from './draft-wizard';
import {ticketStars,legacyDifficulty,starLabel} from './ticket-difficulty';
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
export function Tickets() {
  const { data, error, load } = useLoad("/tickets"),
    u = React.useContext(UserContext),
    [filter, setFilter] = useState(""),
    [archive, setArchive] = useState(false),
    [service, setService] = useState(""),
    [mode, setMode] = useState(""),
    [difficulty, setDifficulty] = useState(""),
    [order, setOrder] = useState("newest"),
    [importing, setImporting] = useState(false),
    [assistantOpen, setAssistantOpen] = useState(false),
    [err, setErr] = useState("");
  const nav = useNavigate();
  const [trial,setTrial]=useState<Obj|null>(null);
  const [trying,setTrying]=useState(false);
  async function tryTask(index:number){setTrying(true);try{const p=await api(`/tickets/${trial!.id}/try`,"POST",{task_index:index});nav("/attempts/"+p.id);}catch(e:any){setErr(e.message);setTrial(null);}finally{setTrying(false);}}
  const latest = Array.from(new Map((data || []).slice().reverse().map((item: Obj) => [item.ticket_id, item])).values()) as Obj[];
  const serviceNames = Array.from(new Set(latest.flatMap((item: Obj) => item.data.tasks.flatMap((task: Obj) => task.services || [])))).sort() as string[];
  const visible = latest.filter(item => item.archived === archive &&
    `${item.ticket_id} ${item.data.title}`.toLocaleLowerCase().includes(filter.toLocaleLowerCase()) &&
    (!service || item.data.tasks.some((task: Obj) => (task.services || []).includes(service) || task.own_service === service)) &&
    (!mode || item.data.tasks.some((task: Obj) => task.mode === mode)) &&
    (!difficulty || ticketStars(item.data) === Number(difficulty)));
  visible.sort((a, b) => order === "oldest" ? a.ticket_id - b.ticket_id : order === "title" ? a.data.title.localeCompare(b.data.title, "ru") : order === 'difficulty-asc' ? ticketStars(a.data)-ticketStars(b.data) || a.ticket_id-b.ticket_id : order === 'difficulty-desc' ? ticketStars(b.data)-ticketStars(a.data) || b.ticket_id-a.ticket_id : b.ticket_id - a.ticket_id);
  async function importJson(file?: File) {
    if (!file) return;
    if (file.size > 512 * 1024) { setErr("Файл должен быть не больше 512 КБ"); return; }
    setImporting(true); setErr("");
    try {
      const content = JSON.parse(await file.text());
      const draft = await api('/ai/tickets/from-json', 'POST', {content});
      const saved = await api('/tickets', 'POST', draft.data);
      nav('/tickets/' + saved.id);
    } catch (problem: any) { setErr(problem.message); }
    finally { setImporting(false); }
  }
  return (
    <div className="page">
      <Heading eyebrow="УЧЕБНЫЙ МАТЕРИАЛ" title="Библиотека билетов">
        {u.role !== "student" && <div className="ticket-create-actions"><Link to="/tickets/new" className="button"><Plus size={18}/>Создать билет вручную</Link><button type="button" className="primary" onClick={()=>setAssistantOpen(true)}>Создать билет с помощью ИИ</button></div>}
      </Heading>
      <Notice>{error || err}</Notice>{trial&&<ArmDialog title="Пройти билет" onClose={()=>setTrial(null)}><p>{trial.data.title}</p>{trial.data.tasks.map((t:Obj,i:number)=><button key={t.id} disabled={trying} onClick={()=>tryTask(i)}>{t.title} · {t.mode==='dds'?'ДДС':'112'}</button>)}</ArmDialog>}
      {u.role !== 'student' && assistantOpen && <AIDraft onClose={()=>setAssistantOpen(false)}/>}
      <div className="ticket-list-tabs" role="tablist" aria-label="Состояние билетов"><button role="tab" aria-selected={!archive} className={!archive ? 'active' : ''} onClick={()=>setArchive(false)}>Билеты</button><button role="tab" aria-selected={archive} className={archive ? 'active' : ''} onClick={()=>setArchive(true)}>Архив</button></div>
      <div className="ticket-list-toolbar">
        <label className="button ticket-import">{importing ? 'Разбираем файл…' : 'Импорт JSON'}<input type="file" accept=".json,application/json" hidden disabled={importing} onChange={event=>{void importJson(event.target.files?.[0]);event.target.value='';}}/></label>
        <label className="ticket-list-search"><Search size={16}/><input aria-label="Поиск билета" placeholder="Номер или название" value={filter} onChange={event=>setFilter(event.target.value)}/></label>
        <select aria-label="Служба" value={service} onChange={event=>setService(event.target.value)}><option value="">Все службы</option>{serviceNames.map(name=><option key={name}>{name}</option>)}</select>
        <select aria-label="Режим" value={mode} onChange={event=>setMode(event.target.value)}><option value="">112 и ДДС</option><option value="112">112</option><option value="dds">ДДС</option></select>
        <select aria-label="Сложность" value={difficulty} onChange={event=>setDifficulty(event.target.value)}><option value="">Любая сложность</option>{[1,2,3,4,5].map(stars=><option key={stars} value={stars}>{starLabel(stars)}</option>)}</select>
        <select aria-label="Порядок" value={order} onChange={event=>setOrder(event.target.value)}><option value="newest">Новые сначала</option><option value="oldest">По номеру</option><option value="title">По названию</option><option value="difficulty-asc">Сначала проще ★→★★★★★</option><option value="difficulty-desc">Сначала сложнее ★★★★★→★</option></select>
      </div>
      <div className="ticket-grid">
        {visible.map((v: Obj) => (
            <div className="panel ticket-card" key={v.id}>
              <div className="ticket-card-top"><strong>Билет № {v.ticket_id}</strong>{!v.published && <Badge tone="amber">Черновик</Badge>}</div>
              <h3>{v.data.title}</h3>
              <p>{ticketSummary(v.data)}</p>
              <span className="ticket-difficulty" aria-label={`Сложность: ${ticketStars(v.data)} из 5`} title={v.data.difficulty_reason||''}>{starLabel(ticketStars(v.data))}</span>
              <div className="ticket-actions">{u.role!=="student"&&<button className="small" onClick={()=>setTrial(v)}>Пройти билет</button>}
                <Link className="button small" to={"/tickets/" + v.id}>
                  {v.editable ? "Открыть редактор" : "Посмотреть"}
                </Link>
                {v.editable && !v.published && (
                  <button
                    className="small primary"
                    onClick={async () => {
                      try {
                        await api(`/tickets/${v.id}/publish`, "POST");
                        load();
                      } catch (e: any) {
                        setErr(e.message);
                      }
                    }}
                  >
                    Опубликовать
                  </button>
                )}
                {v.editable && (
                  <button
                    className="text-button"
                    onClick={async () => {
                      await api(`/tickets/${v.ticket_id}/archive`, "POST");
                      load();
                    }}
                  >
                    {v.archived ? "Вернуть" : "В архив"}
                  </button>
                )}
              </div>
            </div>
          ))}
      </div>
      {!visible.length && <div className="panel ticket-list-empty">{archive ? 'В архиве билетов нет.' : 'Билеты не найдены.'}</div>}
    </div>
  );
}
function ticketSummary(data: Obj) {
  const description = String(data.description || '').trim();
  if (description && !/демонстрационная адаптация|черновик ии|проверьте карточку|требуется проверка методистом|практика полного цикла ддс/i.test(description)) return description;
  const task = data.tasks?.[0];
  return String(task?.initial_card?.description || task?.intro || 'Учебная ситуация').replace(/^Получена карточка(?: 112)?:?\s*/i, '').trim();
}
const newTask = () => ({
  id: uuid(),
  title: "Новое задание",
  mode: "112",
  category: "Происшествие",
  intro: "Опишите исходную реплику заявителя",
  phone: "+7 (000) 000-00-01",
  source: "Авторский сценарий",
  method_note: "Требует проверки преподавателем",
  limit_seconds: 30,
  own_service: "ДДС района",
  questions: [],
  initial_card: {},
  expected_card: {},
  type_options: [],
  traits: [],
  services: [],
  routing: [],
  service_events: [],
  contacts: [],
  criteria: [],
});
export function TicketEditor() {
  const { id } = useParams(),
    u = React.useContext(UserContext),
    nav = useNavigate(),
    [data, setData] = useState<Obj | null>(null),
    [version, setVersion] = useState<Obj | null>(null),
    [index, setIndex] = useState(0),
    [error, setError] = useState(""),
    [section, setSection] = useState("story"),
    [showAllCardFields, setShowAllCardFields] = useState(false),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (id === "new") {
      setVersion(null);
      setData({
        title: "Новый учебный билет",
        description: "",
        difficulty: "Базовый",
        difficulty_stars: 1,
        tasks: [newTask()],
      });
    } else
      api("/tickets")
        .then((v) => {
          const item = v.find((v: Obj) => v.id === Number(id));
          if (item) {
            setVersion(item);
            setData({ ...item.data, description: ticketSummary(item.data), tasks: item.data.tasks.map((task: Obj) => ({...task, method_note: /^Демонстрационная адаптация\./i.test(task.method_note || '') ? '' : task.method_note})) });
          } else setError("Билет не найден");
        })
        .catch((e) => setError(e.message));
  }, [id]);
  if (!data)
    return (
      <div className="page">
        <Notice>{error}</Notice>Загрузка…
      </div>
    );
  const task = data.tasks[index],
    readonly = u.role === "student" || (version && !version.editable);
  function update(k: string, v: any) {
    setData((d) => ({ ...d!, [k]: v }));
  }
  function updateTask(k: string, v: any) {
    setData((d) => ({
      ...d!,
      tasks: d!.tasks.map((t: Obj, i: number) =>
        i === index ? { ...t, [k]: v } : t,
      ),
    }));
  }
  function updateItem(key: string, i: number, k: string, v: any) {
    updateTask(
      key,
      task[key].map((x: Obj, n: number) => (n === i ? { ...x, [k]: v } : x)),
    );
  }
  async function save(publish = false) {
    setBusy(true);
    setError("");
    try {
      const v = await api(
        "/tickets" + (version ? "?ticket_id=" + version.ticket_id : ""),
        "POST",
        data,
      );
      if (publish) await api(`/tickets/${v.id}/publish`, "POST");
      nav(publish?"/tickets":"/tickets/"+v.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (readonly)
    return (
      <div className="page">
        <VoiceDraft data={data}/><Heading eyebrow="УЧЕБНЫЙ МАТЕРИАЛ" title={data.title}>
          <Link className="button" to="/tickets">
            К билетам
          </Link>
        </Heading>
        <p>{data.description}</p><button onClick={async()=>{try{const v=await api('/tickets','POST',data);nav('/tickets/'+v.id);}catch(e:any){setError(e.message);}}}>Создать свою копию для редактирования</button>
        {data.tasks.map((t: Obj) => (
          <div className="panel form-panel" key={t.id}>
            <Badge>{t.mode === "112" ? "Оператор 112" : "Диспетчер ДДС"}</Badge>
            <h2>{t.title}</h2>
            <p>{t.intro}</p>
            <p>
              {t.source} · {t.method_note}
            </p>
            <details>
              <summary>Диалог и эталонные ответы</summary>
              {t.questions.map((q: Obj) => (
                <div className="review-note" key={q.id}>
                  <b>{q.question}</b>
                  <p>{q.answer}</p>
                  {q.audio_id && (
                    <audio controls src={"/api/media/" + q.audio_id} />
                  )}
                </div>
              ))}
            </details>
            <details>
              <summary>Эталон карточки</summary>
              <dl className="reference-card">
                {Object.entries(t.expected_card).map(([k, v]: any) => (
                  <React.Fragment key={k}>
                    <dt>{labels[k] || k}</dt>
                    <dd>{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
                  </React.Fragment>
                ))}
              </dl>
            </details>
            <details>
              <summary>Критерии проверки ({t.criteria.length})</summary>
              {t.criteria.map((c: Obj) => (
                <div className="review-note" key={c.id}>
                  <b>{c.label}</b>
                  <p>
                    {String(c.expected)} · {c.weight} баллов{" "}
                    {c.critical ? "· критический" : ""}
                  </p>
                </div>
              ))}
            </details>
          </div>
        ))}
      </div>
    );
  return (
    <div className="page editor"><VoiceDraft data={data}/>
      <Heading
        eyebrow="КОНСТРУКТОР СЦЕНАРИЯ"
        title={version ? `Билет № ${version.ticket_id}` : "Новый билет"}
      >
        <div className="actions">
          <Link to="/tickets" className="button">
            Отмена
          </Link>
          {!readonly && (
            <>
              <button disabled={busy} onClick={() => save()}>
                Сохранить черновик
              </button>
              <button
                disabled={busy}
                className="primary"
                onClick={() => save(true)}
              >
                Сохранить и опубликовать
              </button>
            </>
          )}
        </div>
      </Heading>
      <Notice>{error}</Notice>
      {version?.published && (
        <div className="info-banner">
          Опубликованная версия неизменяема. Сохранение создаст новую версию;
          старые назначения и результаты останутся прежними.
        </div>
      )}
      <fieldset disabled={readonly || busy}>
        <div className="panel form-panel">
          <div className="form-grid">
            <Field label="Название билета">
              <input
                value={data.title}
                onChange={(e) => update("title", e.target.value)}
              />
            </Field>
            <Field label="Сложность билета">
              <select
                value={ticketStars(data)}
                onChange={(e) => {const stars=Number(e.target.value);setData(current=>({...current!,difficulty_stars:stars,difficulty:legacyDifficulty(stars),difficulty_reason:'Выбрано преподавателем'}));}}
              >
                {[1,2,3,4,5].map(stars=><option key={stars} value={stars}>{starLabel(stars)}</option>)}
              </select>
              {data.difficulty_reason&&<small>{data.difficulty_reason}</small>}
            </Field>
            <Field label="Описание">
              <textarea rows={3}
                value={data.description}
                onChange={(e) => update("description", e.target.value)}
              />
            </Field>
          </div>
        </div>
        <div className="editor-layout ticket-editor-layout">
          {data.tasks.length>1&&<label className="legacy-task-selector">Задание в сохранённом билете<select value={index} onChange={event=>setIndex(Number(event.target.value))}>{data.tasks.map((item:Obj,n:number)=><option key={item.id} value={n}>{n+1}. {item.title}</option>)}</select></label>}
          <div className="panel task-editor">
            <div className="form-grid">
              <Field label="Название задания">
                <input
                  value={task.title}
                  onChange={(e) => updateTask("title", e.target.value)}
                />
              </Field>
              <Field label="Режим">
                <select
                  value={task.mode}
                  onChange={(e) => updateTask("mode", e.target.value)}
                >
                  <option value="112">Оператор 112</option>
                  <option value="dds">Диспетчер ДДС</option>
                </select>
              </Field>
              <Field label="Категория для статистики">
                <input
                  value={task.category}
                  onChange={(e) => updateTask("category", e.target.value)}
                />
              </Field>
            </div>
            <div className="editor-tabs">
              {[
                ["story", "Ситуация"],
                ["card", "Карточка"],
                ["routing", "Службы и события"],
                ...(task.mode === 'dds' ? [["contacts", "Звонки"]] : []),
                ["criteria", "Проверка"],
              ].map(([k, label]) => (
                <button
                  key={k}
                  className={section === k ? "active" : ""}
                  onClick={() => setSection(k)}
                >
                  {label}
                </button>
              ))}
            </div>
            {section === "story" && (
              <div className="editor-section">
                <Field label="Первое сообщение / описание ситуации">
                  <textarea
                    rows={5}
                    value={task.intro}
                    onChange={(e) => updateTask("intro", e.target.value)}
                  />
                </Field>
                <TextCheck text={task.intro}/>
                <div className="form-grid">
                  <Field label="Телефон заявителя">
                    <input
                      value={task.phone}
                      onChange={(e) => updateTask("phone", e.target.value)}
                    />
                  </Field>
                  <Field label="Своя служба (ДДС)">
                    <input
                      value={task.own_service}
                      onChange={(e) =>
                        updateTask("own_service", e.target.value)
                      }
                    />
                  </Field>
                  <Field label="Учебный норматив, секунд">
                    <input
                      type="number"
                      min={30}
                      max={7200}
                      value={task.limit_seconds}
                      onChange={(e) =>
                        updateTask("limit_seconds", Number(e.target.value))
                      }
                    />
                  </Field>
                </div>
                <Field label="Методическое примечание и статус проверки">
                  <textarea
                    value={task.method_note}
                    onChange={(e) => updateTask("method_note", e.target.value)}
                  />
                </Field>
              </div>
            )}
            {section === "dialogue" && (
              <div className="editor-section">
                <p>
                  Ученик спрашивает голосом или выбирает готовый вопрос. Ответы берутся из фактов этого билета. Уточните дополнительные обстоятельства до публикации.
                </p>
                <Field label="Голос заявителя"><select value={task.caller_gender||''} onChange={e=>updateTask('caller_gender',e.target.value||null)}><option value="">Определить по имени</option><option value="male">Мужской</option><option value="female">Женский</option></select></Field>
                {task.questions.map((q: Obj, i: number) => (
                  <div className="question-editor" key={q.id}>
                    <div className="section-title">
                      <b>Вопрос {i + 1}</b>
                      <button
                        className="danger-text"
                        onClick={() =>
                          updateTask(
                            "questions",
                            task.questions.filter(
                              (_: Obj, n: number) => n !== i,
                            ),
                          )
                        }
                      >
                        Удалить
                      </button>
                    </div>
                    <Field label="Вопрос оператора">
                      <input
                        value={q.question}
                        onChange={(e) =>
                          updateItem("questions", i, "question", e.target.value)
                        }
                      />
                    </Field>
                    <Field label="Ответ заявителя">
                      <textarea
                        value={q.answer}
                        onChange={(e) =>
                          updateItem("questions", i, "answer", e.target.value)
                        }
                      />
                    </Field>
                  </div>
                ))}
                <button
                  onClick={() =>
                    updateTask("questions", [
                      ...task.questions,
                      {
                        id: uuid(),
                        question: "",
                        answer: "",
                        required: true,
                      },
                    ])
                  }
                >
                  <Plus size={16} />
                  Добавить вопрос
                </button>
              </div>
            )}
            {section === "card" && (
              <div className="editor-section">
                {task.mode === '112' && <><Field label="Типы происшествий для выбора учеником (по одному на строку)">
                  <textarea
                    value={task.type_options.join("\n")}
                    onChange={(e) =>
                      updateTask("type_options", e.target.value.split("\n"))
                    }
                  />
                </Field><p>Обычно здесь один правильный тип. Добавляйте другие только если ученик должен выбирать между похожими происшествиями.</p>
                <ClassifierPicker
                  add={(v) =>
                    updateTask("type_options", [
                      ...new Set([...task.type_options.filter(Boolean), v]),
                    ])
                  }
                /></>}
                <Field label="Уточняющие признаки (по одному на строку)">
                  <textarea
                    className="ticket-traits-input"
                    rows={Math.max(5, task.traits.length + 2)}
                    ref={node=>{if(node){node.style.height='auto';node.style.height=`${node.scrollHeight+4}px`;}}}
                    value={task.traits.join("\n")}
                    onChange={(e) =>
                      updateTask("traits", e.target.value.split("\n"))
                    }
                  />
                </Field>
                <h3>{task.mode === 'dds' ? 'Полученная карточка' : 'Эталон и исходные сведения'}</h3>
                <p>
                  {task.mode === 'dds' ? 'Диспетчер получает заполненную карточку и организует реагирование.' : 'Эталон используется для проверки карточки ученика. Исходные сведения видны ученику сразу.'}
                </p>
                <button type="button" className="button small" onClick={() => setShowAllCardFields(!showAllCardFields)}>{showAllCardFields ? 'Скрыть пустые поля' : 'Показать все поля'}</button>
                <table className="card-editor-table">
                  <thead>
                    <tr>
                      <th>Поле</th>
                      {task.mode === '112' && <th>Эталон</th>}
                      <th>{task.mode === 'dds' ? 'Значение' : 'Исходное значение'}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(labels)
                      .filter(([k]) => k !== "traits" && (showAllCardFields || task.initial_card[k] || task.expected_card[k]))
                      .map(([k, label]: any) => (
                        <tr key={k}>
                          <td>{label}</td>
                          {(task.mode === 'dds' ? ["initial_card"] : ["expected_card", "initial_card"]).map((key) => (
                            <td key={key}>
                              {['victims','blocked','medical_refusal','no_contact','call_lost'].includes(k)?<select value={task[key][k]||''} onChange={e=>updateTask(key,{...task[key],[k]:e.target.value})}><option value="">Не задано</option><option value="unknown">Неизвестно</option><option value="yes">Да</option><option value="no">Нет</option></select>:<input
                                value={task[key][k] || ""}
                                onChange={(e) =>
                                  updateTask(key, {
                                    ...task[key],
                                    [k]: e.target.value,
                                  })
                                }
                              />}
                            </td>
                          ))}
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
            {section === "routing" && (
              <div className="editor-section">
                <p>
                  В режиме 112 службы подбираются по типу происшествия, признакам и пострадавшим; ученик подтверждает оповещение. В ДДС получатели уже входят в карточку. Критерии оценки определяют, какие
                  службы обязательны. Отсчёт сообщений начинается с поступления карточки или с передачи заявки выбранному абоненту.
                </p>
                <Field label="Дополнительные службы (по одной на строку)">
                  <textarea
                    className="ticket-services-input"
                    rows={Math.max(6, task.services.length + 2)}
                    value={task.services.join("\n")}
                    onChange={(e) =>
                      updateTask(
                        "services",
                        e.target.value.split("\n").filter(Boolean),
                      )
                    }
                  />
                </Field>
                <h3>Сообщения бригады</h3>
                {task.service_events.map((v: Obj, i: number) => (
                  <div className="event-editor ticket-event" key={i}>
                    <Field label="Через, сек.">
                      <input
                        type="number"
                        min={0}
                        value={v.after ?? v.after_seconds ?? 10}
                        onChange={(e) =>
                          updateItem(
                            "service_events",
                            i,
                            "after",
                            Number(e.target.value),
                          )
                        }
                      />
                    </Field>
                    <Field label="Канал"><select value={v.kind||'message'} onChange={e=>updateItem('service_events',i,'kind',e.target.value)}><option value="message">Текстовое сообщение</option><option value="incoming_call">Входящий звонок</option></select></Field>
                    {v.kind!=='incoming_call'&&<label><input type="checkbox" checked={!!v.spoken} onChange={e=>updateItem('service_events',i,'spoken',e.target.checked)}/>Озвучивать сообщение</label>}<Field label="Голос"><select value={v.voice_gender||'male'} onChange={e=>updateTask('service_events',task.service_events.map((x:Obj,n:number)=>n===i||v.contact_id&&x.contact_id===v.contact_id?{...x,voice_gender:e.target.value}:x))}><option value="male">Мужской</option><option value="female">Женский</option></select></Field>
                    <Field label="Отсчёт времени"><select value={v.trigger_contact||''} onChange={e=>updateItem('service_events',i,'trigger_contact',e.target.value)}><option value="">С поступления карточки</option>{(task.contacts||[]).map((c:Obj)=><option key={c.id} value={c.id}>С передачи заявки: {c.name}</option>)}</select></Field>
                    {v.kind==='incoming_call'&&<Field label="Кто звонит"><select value={v.contact_id||''} onChange={e=>{const c=task.contacts.find((c:Obj)=>c.id===e.target.value);updateTask('service_events',task.service_events.map((x:Obj,n:number)=>n===i?{...x,contact_id:c?.id,who:c?.name}:x));}}><option value="">Выберите абонента</option>{(task.contacts||[]).map((c:Obj)=><option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>}
                    <Field label="Текст сообщения">
                      <textarea rows={4}
                        value={v.text || v.message || ""}
                        onChange={(e) =>
                          updateItem(
                            "service_events",
                            i,
                            "text",
                            e.target.value,
                          )
                        }
                      />
                    </Field>
                    <button
                      className="danger-text"
                      onClick={() =>
                        updateTask(
                          "service_events",
                          task.service_events.filter(
                            (_: Obj, n: number) => n !== i,
                          ),
                        )
                      }
                    >
                      Удалить
                    </button>
                  </div>
                ))}
                <button
                  onClick={() =>
                    updateTask("service_events", [
                      ...task.service_events,
                      { after: 10, text: "", kind:'incoming_call', contact_id:task.contacts?.[0]?.id||'', who:task.contacts?.[0]?.name||'' },
                    ])
                  }
                >
                  <Plus size={16} />
                  Добавить сообщение
                </button>
              </div>
            )}
            {section === "contacts" && <div className="editor-section"><h3>Звонки по сценарию</h3><p>Здесь задаются ответы заявителя, бригады и других служб на учебные звонки диспетчера. Откройте нужного абонента для редактирования.</p>
              {(task.contacts||[]).map((c:Obj,i:number)=><details className="contact-editor ticket-contact" key={c.id}><summary>{c.name || 'Новый абонент'} <small>{c.kind==='brigade'?'Бригада':c.kind==='caller'?'Заявитель':'Служба'}</small></summary><div className="form-grid">
                <Field label="Название бригады / службы"><input value={c.name} onChange={e=>updateItem('contacts',i,'name',e.target.value)}/></Field>
                <Field label="Учебный телефон"><input value={c.phone} onChange={e=>updateItem('contacts',i,'phone',e.target.value)}/></Field>
                <Field label="Тип абонента"><select value={c.kind} onChange={e=>updateItem('contacts',i,'kind',e.target.value)}><option value="brigade">Бригада</option><option value="service">Другая ДДС</option><option value="caller">Заявитель</option></select></Field>
                {c.kind==='service'&&<Field label="Название службы-получателя"><input value={c.service} onChange={e=>updateItem('contacts',i,'service',e.target.value)}/></Field>}
              </div><Field label="Ответ при первом обращении"><textarea value={c.response} onChange={e=>updateItem('contacts',i,'response',e.target.value)}/></Field>
              <Field label="Ответы при повторных обращениях (по одному на строку)"><textarea value={(c.updates||[]).join('\n')} onChange={e=>updateItem('contacts',i,'updates',e.target.value.split('\n'))}/></Field>
              <details><summary>Дополнительные вопросы и ответы этого абонента</summary>{(c.questions||[]).map((q:Obj,n:number)=><div className="form-grid" key={q.id}><Field label="Вопрос"><input value={q.question} onChange={e=>updateItem('contacts',i,'questions',c.questions.map((x:Obj,j:number)=>j===n?{...x,question:e.target.value}:x))}/></Field><Field label="Ответ"><textarea value={q.answer} onChange={e=>updateItem('contacts',i,'questions',c.questions.map((x:Obj,j:number)=>j===n?{...x,answer:e.target.value}:x))}/></Field><button onClick={()=>updateItem('contacts',i,'questions',c.questions.filter((_:Obj,j:number)=>j!==n))}>Удалить вопрос</button></div>)}<button onClick={()=>updateItem('contacts',i,'questions',[...(c.questions||[]),{id:'custom-'+uuid(),question:'Уточняющий вопрос',answer:'Ответ по сценарию',required:false}])}>Добавить вопрос абоненту</button></details>
              <button className="danger-text" onClick={()=>updateTask('contacts',task.contacts.filter((_:Obj,n:number)=>n!==i))}>Удалить контакт</button></details>)}
              <button onClick={()=>updateTask('contacts',[...(task.contacts||[]),{id:uuid(),name:'Учебная бригада',kind:'brigade',phone:'1001',service:'',response:'Информация принята, бригада выезжает.',updates:['Прибыли на место.','Работы завершены.']}])}>Добавить абонента</button>
              <p>ДДС получает готовую карточку. Оцениваются решение, связь, статусы и комментарии; контроль заполнения карточки оператором 112 не входит в обязанности ДДС.</p>
            </div>}
            {section === "criteria" && (
              <div className="editor-section">
                <div className="section-title">
                  <div>
                    <h3>Проверка выполнения</h3>
                    <p>
                      Свободный текст проверяет преподаватель. Порог зачёта —
                      70%, без критических ошибок.
                    </p>
                  </div>
                  <button
                    onClick={() =>
                      updateTask("criteria", [
                        ...task.criteria,
                        {
                          id: uuid(),
                          label: "Новый критерий",
                          kind: task.mode==='dds'?"manual":"field",
                          field: task.mode==='dds'?"":"street",
                          expected: "",
                          weight: 10,
                          critical: false,
                          skill: "Полнота карточки",
                        },
                      ])
                    }
                  >
                    <Plus size={16} />
                    Критерий
                  </button>
                </div>
                {task.criteria.map((c:Obj,i:number)=><div className="criterion-editor ticket-criterion" key={c.id}>
                  <div className="ticket-criterion-number">Критерий {i+1}</div>
                  <div className="criterion-heading"><Field label="Что проверяем"><textarea rows={2} value={c.label} onChange={e=>updateItem('criteria',i,'label',e.target.value)}/></Field><button className="danger-text" onClick={()=>updateTask('criteria',task.criteria.filter((_:Obj,n:number)=>n!==i))}>Удалить</button></div>
                  <div className="criterion-controls"><Field label="Способ проверки"><select value={c.kind} onChange={e=>{const kind=e.target.value;updateTask('criteria',task.criteria.map((item:Obj,n:number)=>n===i?{...item,kind,field:kind==='field'?'street':'',expected:kind==='time'?300:''}:item));}}>{Object.entries({field:'Значение в карточке',question:'Задан вопрос',service:'Оповещена служба',status:'Отмечен статус ДДС',time:'Соблюдено время',manual:'Проверяет преподаватель',contact:'Связь с абонентом',validation:'Карточка проверена'}).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></Field>
                  {c.kind==='field'&&<Field label="Какое поле проверять"><select value={c.field} onChange={e=>updateItem('criteria',i,'field',e.target.value)}><option value="">Выберите поле</option>{Object.entries(labels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></Field>}
                  <Field label={`Значимость: ${c.weight} из 100`}><input aria-label="Вес критерия" type="range" min={1} max={100} value={c.weight} onChange={e=>updateItem('criteria',i,'weight',Number(e.target.value))}/></Field></div>
                  {['contact','question','service','status'].includes(c.kind)?<Field label={c.kind==='contact'?'С кем нужно связаться':c.kind==='question'?'Какой вопрос нужно задать':c.kind==='service'?'Какую службу оповестить':'Какой статус отметить'}><select value={String(c.expected??'')} onChange={e=>updateItem('criteria',i,'expected',e.target.value)}><option value="">Выберите значение</option>{(c.kind==='contact'?(task.contacts||[]).map((x:Obj)=>[x.id,x.name]):c.kind==='question'?task.questions.map((x:Obj)=>[x.id,x.question]):c.kind==='service'?task.services.map((x:string)=>[x,x]):['Принята','Не принята','Начало реагирования','Прибытие','Проведение работ','Работы завершены'].map(x=>[x,x])).map(([value,label]:string[])=><option key={value} value={value}>{label}</option>)}</select></Field>:
                  <Field label={c.kind==='manual'?'Признаки правильного выполнения':c.kind==='time'?'Не более, секунд':'Правильное значение'}>{c.kind==='time'?<input type="number" min={1} max={7200} value={c.expected} onChange={e=>updateItem('criteria',i,'expected',Number(e.target.value))}/>:['victims','blocked','medical_refusal','no_contact','call_lost'].includes(c.field)?<select value={c.expected} onChange={e=>updateItem('criteria',i,'expected',e.target.value)}><option value="">Выберите значение</option><option value="yes">Да</option><option value="no">Нет</option><option value="unknown">Неизвестно</option></select>:<textarea rows={c.kind==='manual'?4:2} value={Array.isArray(c.expected)?c.expected.join(', '):String(c.expected??'')} onChange={e=>updateItem('criteria',i,'expected',c.field==='traits'?e.target.value.split(',').map(v=>v.trim()):e.target.value)}/>}</Field>}
                  <label className="criterion-critical"><input type="checkbox" checked={c.critical} onChange={e=>updateItem('criteria',i,'critical',e.target.checked)}/>Критическая ошибка — без выполнения этого условия билет не зачтён</label>
                </div>)}
              </div>
            )}
          </div>
        </div>
      </fieldset>
    </div>
  );
}
function AudioUpload({
  value,
  onChange,
}: {
  value?: string;
  onChange: (v: string | null) => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="audio-upload">
      <span>Озвучка · MP3 / WAV · до 20 МБ</span>
      <input
        aria-label="Загрузить аудиозапись"
        type="file"
        accept=".mp3,.wav"
        disabled={busy}
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          setBusy(true);
          const form = new FormData();
          form.append("file", f);
          try {
            const r = await api("/media", "POST", form);
            onChange(r.id);
            setError("");
          } catch (e: any) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      />
      {value && (
        <>
          <audio controls src={"/api/media/" + value} />
          <button className="small" onClick={() => onChange(null)}>
            Убрать запись
          </button>
        </>
      )}
      <Notice>{error}</Notice>
    </div>
  );
}
export function ClassifierPicker({ add }: { add?: (v: string) => void }) {
  const [q, setQ] = useState(""),
    { data } = useLoad("/classifier?q=" + encodeURIComponent(q));
  return (
    <details className="classifier-picker">
      <summary>
        {add
          ? "Найти тип происшествия в справочнике"
          : "Просмотреть типы происшествий"}
      </summary>
      <input
        placeholder="Например: правонарушение"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div>
        {q.trim().length >= 2 && data?.map((r: Obj) => (
          <button
            className="classifier-row"
            key={r.code}
            disabled={!add}
            onClick={() => add?.(r.title)}
          >
            <code>{r.code}</code>
            <span>{r.title}</span>
            {add && <Plus size={15} />}
          </button>
        ))}
      </div>
      <small>
        Справочник помогает выбрать точное название и код происшествия. Введите хотя бы два символа для поиска.
      </small>
    </details>
  );
}
