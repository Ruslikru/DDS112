import {TutorialCatalog} from './tutorials';
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
export function Assignments() {
  const u = React.useContext(UserContext),
    { data, error, load } = useLoad("/assignments", 5000),
    [show, setShow] = useState(false),
    [filter, setFilter] = useState(""),
    [err, setErr] = useState("");
  const nav = useNavigate();
  const [mode,setMode]=useState(new URLSearchParams(useLocation().search).get('mode')||'');
  const start = async (id: number, index: number) => {
    try {
      const p = await api(`/assignments/${id}/start`, "POST", {
        task_index: index,
      });
      nav("/attempts/" + p.id);
    } catch (e: any) {
      setErr(e.message);
    }
  };
  return (
    <div className="page">
      <Heading
        eyebrow="УЧЕБНЫЙ ПРОЦЕСС"
        title={u.role === "student" ? "Мои задания" : "Назначения"}
      >
        {u.role !== "student" && (
          <button className="primary" onClick={() => setShow(!show)}>
            <Plus size={18} />
            Назначить билет
          </button>
        )}
      </Heading>
      <Notice>{error || err}</Notice>{u.role==='student'&&<TutorialCatalog/>}
      {show && (
        <AssignmentForm
          done={() => {
            setShow(false);
            load();
          }}
        />
      )}
      <div className="toolbar"><button className={mode==='dds'?'primary':''} onClick={()=>setMode(mode==='dds'?'':'dds')}>Обучение ДДС</button><button className={mode==='112'?'primary':''} onClick={()=>setMode(mode==='112'?'':'112')}>Обучение 112</button>
        <div className="search">
          <Search size={17} />
          <input
            aria-label="Поиск заданий"
            placeholder="Найти билет или ученика"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        <span>{data?.length || 0} назначений</span>
      </div>
      <div className="assignment-list">
        {data
          ?.filter((a: Obj) =>
            (a.title + a.student).toLowerCase().includes(filter.toLowerCase())&&(!mode||a.tasks.some((t:Obj)=>t.mode===mode)),
          )
          .map((a: Obj) => (
            <div className="panel assignment" key={a.id}>
              <div className="assignment-icon">
                <ClipboardList size={23} />
              </div>
              <div className="assignment-info">
                <div className="tag-row">
                  <Badge>{a.training ? "Тренировка" : "Экзамен"}</Badge>
                  <span>
                    Версия {a.version} · #{a.id}
                  </span>
                </div>
                <h3>{a.title}</h3>
                <p>
                  {u.role !== "student" ? a.student + " · " : ""}
                  {a.tasks.length} заданий ·{" "}
                  {
                    a.attempts.filter((p: Obj) => p.status === "completed")
                      .length
                  }{" "}
                  завершённых попыток
                </p>
                <div className="task-buttons">
                  {a.tasks.map((t: Obj, i: number) => {
                    const p = a.attempts.find((x: Obj) => x.task_index === i);
                    const inProgress=p&&!["completed", "aborted"].includes(p.status);
                    const waitingForAudio=t.voice?.ready===false&&!inProgress;
                    if(mode&&t.mode!==mode)return null;
                    return (
                      <div key={i}>
                        <span className="task-mode">
                          {t.mode === "112" ? "112" : "ДДС"}
                        </span>
                        <span>{t.title}{waitingForAudio&&<small role="status">{t.voice.failed?'Ошибка генерации звука — сообщите преподавателю':`Генерируется звук: ${t.voice.generated}/${t.voice.total}`}</small>}</span>
                        {u.role === "student" ? (
                          <button
                            className="small"
                            disabled={!a.released||waitingForAudio}
                            title={waitingForAudio?'Билет станет доступен после генерации всех записей':undefined}
                            onClick={() => start(a.id, i)}
                          >
                            {waitingForAudio
                              ? "Ожидание звука"
                              : !a.released
                              ? "Ожидание запуска"
                              : p &&
                                  !["completed", "aborted"].includes(p.status)
                                ? "Продолжить"
                                : p
                                  ? "Повторить"
                                  : "Начать"}
                            <Play size={13} />
                          </button>
                        ) : p ? (
                          <Link
                            className="button small"
                            to={"/attempts/" + p.id}
                          >
                            Открыть попытку
                          </Link>
                        ) : (
                          <small>Ещё не начато</small>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
              {u.role !== "student" && !a.released && (
                <button
                  onClick={async () => {
                    await api(`/assignments/${a.id}/release`, "POST");
                    load();
                  }}
                >
                  Запустить
                </button>
              )}
            </div>
          ))}
      </div>
      {data?.length === 0 && <Empty />}
    </div>
  );
}
function AssignmentForm({ done }: { done: () => void }) {
  const { data: t } = useLoad("/tickets",5000),
    { data: users } = useLoad("/users");
  const [selected, setSelected] = useState<number[]>([]),
    [error, setError] = useState("");
  return (
    <form
      className="panel form-panel"
      onSubmit={async (e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        try {
          await api("/assignments", "POST", {
            version_id: Number(f.get("version")),
            students: selected,
            start_mode: f.get("start"),
            training: f.get("mode") === "training",
          });
          done();
        } catch (e: any) {
          setError(e.message);
        }
      }}
    >
      <h3>Новое назначение</h3>
      <div className="form-grid">
        <Field label="Билет">
          <select name="version" required>
            <option value="">Выберите билет</option>
            {t
              ?.filter((v: Obj) => v.published && !v.archived)
              .map((v: Obj) => (
                <option key={v.id} value={v.id} disabled={v.voice?.ready===false}>
                  {v.data.title} · v{v.number}{v.voice?.ready===false?` · звук ${v.voice.generated}/${v.voice.total}`:''}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Запуск">
          <select name="start">
            <option value="self">Ученик запускает самостоятельно</option>
            <option value="teacher">После команды преподавателя</option>
          </select>
        </Field>
        <Field label="Режим">
          <select name="mode">
            <option value="training">Тренировка — подсказки и пауза</option>
            <option value="exam">Экзамен — без подсказок и паузы</option>
          </select>
        </Field>
      </div>
      <div className="check-list">
        {users
          ?.filter((s: Obj) => s.role === "student" && s.active)
          .map((s: Obj) => (
            <label key={s.id}>
              <input
                type="checkbox"
                checked={selected.includes(s.id)}
                onChange={(e) =>
                  setSelected(
                    e.target.checked
                      ? [...selected, s.id]
                      : selected.filter((id) => id !== s.id),
                  )
                }
              />
              {s.name}
            </label>
          ))}
      </div>
      <Notice>{error}</Notice>
      <button className="primary" disabled={!selected.length}>
        Назначить выбранным ({selected.length})
      </button>
    </form>
  );
}
