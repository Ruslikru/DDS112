import {NetworkStatus} from './network-queue';
import {VoiceQueue} from './voice';
import {StudentPanel} from './student-panel';
import {TeacherStudents,TeacherAnalytics} from './teacher';
import {TeacherModes} from './teacher-modes';
import {ManagementSettings,Services,SystemUpdates} from './management';
import {StationLogin} from './station-login';
import {Classroom,ClassroomModes,TeacherWorkstations} from './classroom';
import {AdminWorkstations,DemoStationSetup,ServerNameSetup} from './demo-setup';
import {ClassroomClient} from './classroom-client';
import {LearningEditor,IntroGate} from './training-tools';
import {TeacherJournal} from './teacher-journal';
import {MiniQuestions} from './mini-questions';
import {ArmConsole} from './arm-journal';
const demoLaunchExample = new URL('./demo-launch-exe.png', import.meta.url).href;
import { Library, Registry } from './library';
import { Lessons } from './lessons';
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
  Radio,
  FileText,
  Eye,
  EyeOff,
  X,
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
import { Dashboard } from "./dashboard";
import { Assignments } from "./assignments";
import { Workspace } from "./workspace";
import { Results } from "./results";
import { Tickets, TicketEditor } from "./tickets";
import { People, Audit, System } from "./admin";
function deviceBadgeText() {
  const mode=localStorage.getItem('training112:station-mode');
  if(mode==='server')return 'Это сервер';
  if(mode==='client'){
    const number=localStorage.getItem('training112:station-configured')==='true' ? localStorage.getItem('training112:station-number') : '';
    return number ? `Это рабочее место №${number}` : 'Это рабочее место';
  }
  return '';
}

function AppDeviceBadge(){
  const [text,setText]=useState(deviceBadgeText);
  useEffect(()=>{const update=()=>setText(deviceBadgeText());window.addEventListener('station-ready',update);return()=>window.removeEventListener('station-ready',update);},[]);
  return text ? <span className="device-role-app" role="status">{text}</span> : null;
}

function Login({ onLogin }: { onLogin: (u: Obj) => void }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [showPassword, setShowPassword] = useState(false),
    [serverMode,setServerMode] = useState(localStorage.getItem('training112:station-mode')==='server'),
    [serverReady,setServerReady] = useState<boolean|null>(null),
    [stationConfigured,setStationConfigured] = useState(localStorage.getItem('training112:station-configured')==='true'),
    [demoRole, setDemoRole] = useState(localStorage.getItem('training112:demo-role') || ''),
    [demoPassword, setDemoPassword] = useState(localStorage.getItem('training112:demo-password-hint') || ''),
    [welcome, setWelcome] = useState(sessionStorage.getItem('training112:demo-welcome') || ''),
    [hintVisible, setHintVisible] = useState(false);
  const loginInput = useRef<HTMLInputElement>(null);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleHint = () => {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    if (demoRole) idleTimer.current = setTimeout(() => setHintVisible(true), 30_000);
  };
  useEffect(() => {
    const update = () => {
      setServerMode(localStorage.getItem('training112:station-mode')==='server');
      setStationConfigured(localStorage.getItem('training112:station-configured')==='true');
      setDemoRole(localStorage.getItem('training112:demo-role') || '');
      setDemoPassword(localStorage.getItem('training112:demo-password-hint') || '');
      setWelcome(sessionStorage.getItem('training112:demo-welcome') || '');
    };
    window.addEventListener('station-ready', update);
    return () => window.removeEventListener('station-ready', update);
  }, []);
  useEffect(()=>{
    if(!serverMode)return;
    api('/classroom/server-setup').then((status:Obj)=>setServerReady(status.ready!==false)).catch(()=>{});
  },[serverMode]);
  useEffect(() => {
    let active=true;
    const sync=async()=>{
      const bridge=(window as any).pywebview?.api;
      if(!bridge?.get_demo_identity)return false;
      try{
        const info=await bridge.get_demo_identity();
        if(!active)return true;
        if(info.role){
          setDemoRole(info.role);
          setDemoPassword(info.password||'');
          setStationConfigured(Boolean(info.configured));
          if(info.role==='client'&&info.configured)setWelcome('');
        }
        return true;
      }catch{return false;}
    };
    sync();
    const timer=setInterval(async()=>{if(await sync())clearInterval(timer);},500);
    return()=>{active=false;clearInterval(timer);};
  },[]);
  useEffect(() => {
    if (!demoRole || welcome) return;
    const reveal = setTimeout(() => setHintVisible(true), 400);
    scheduleHint();
    return () => { clearTimeout(reveal); if (idleTimer.current) clearTimeout(idleTimer.current); };
  }, [demoRole, welcome]);
  return (
    <div className="login-page">
      <form
        className="login-box"
        onChange={scheduleHint}
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          const f = new FormData(e.currentTarget);
          try {
            if (demoRole === 'client' && localStorage.getItem('training112:station-configured') !== 'true' && f.get('login') !== 'admin') {
              throw new Error('Сначала войдите как администратор и назначьте номер рабочего места.');
            }
            if (serverMode && serverReady===false && f.get('login') !== 'admin') {
              throw new Error('Сначала войдите как администратор и задайте название учебного сервера.');
            }
            onLogin(await api("/login", "POST", Object.fromEntries(f)));
          } catch (e: any) {
            setError(e.message);
            if (demoRole) setHintVisible(true);
          } finally {
            setBusy(false);
          }
        }}
      >
        <h1><strong>112</strong> ВХОД В СИСТЕМУ</h1><StationLogin/>
        <Field label="логин:">
          <input
            ref={loginInput}
            name="login"
            autoComplete="username"
            required
            autoFocus
            placeholder="Введите логин"
          />
        </Field>
        <Field label="пароль:">
          <div className="login-password"><input
            name="password"
            type={showPassword ? 'text' : 'password'}
            autoComplete="current-password"
            required
            placeholder="Введите пароль"
          /><button type="button" className="password-visibility" aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div>
        </Field>
        <Notice>{error}</Notice>
        <button className="primary wide" disabled={busy}>
          {busy ? "Вход…" : "ВОЙТИ"}
        </button>
        <div className="login-note">
          112/ДДС - Учебный контур
        </div>
        {deviceBadgeText() && <div className="device-role-login" role="status">{deviceBadgeText()}</div>}
        {serverMode&&serverReady===false&&<p className="server-setup-login-note">Сначала войдите администратором и задайте название сервера.</p>}
        {demoRole && hintVisible && !welcome && <aside className="demo-hint" aria-label="Подсказка для демонстрационного режима">
          <button type="button" className="demo-hint-close" aria-label="Закрыть подсказку" onClick={() => { setHintVisible(false); scheduleHint(); }}><X size={18}/></button>
          <p>{demoRole === 'server' ? serverReady===false ? 'Это эмуляция ПК сервера. Сначала войдите администратором и задайте название сервера.' : 'Это эмуляция ПК сервера. На нём можно войти в учётную запись преподавателя или администратора.' : !stationConfigured ? 'Это новое рабочее место. Сначала войдите администратором и назначьте номер рабочего места.' : 'Это эмуляция рабочего места. На нём можно войти в учётную запись администратора или одного из студентов.'}</p>
          <div><span>Логины</span><div className="demo-accounts">{(demoRole === 'server' ? serverReady===false ? ['admin'] : ['teacher','admin'] : !stationConfigured ? ['admin'] : ['admin','student1','student2','student3','student4','student5']).map(account=><button type="button" className={account.startsWith('student')?'demo-account-student':''} key={account} onClick={() => { if(loginInput.current){loginInput.current.value=account;loginInput.current.focus();scheduleHint();} }}><b>{account}</b>{account.startsWith('student')&&<small>{({student1:'Новичок · изучение интерфейса',student2:'Начальный · ★★☆☆☆',student3:'Средний · ★★★☆☆',student4:'Продвинутый · ★★★★☆',student5:'Опытный · ★★★★★'})[account]}</small>}</button>)}</div></div>
          <div><span>Пароль</span><strong>{demoPassword || 'Заданный при первом запуске'}</strong></div>
        </aside>}
      </form>
      {welcome && <div className="demo-welcome-backdrop" role="presentation"><div className="demo-welcome" role="dialog" aria-modal="true" aria-labelledby="demo-welcome-title">
        <h2 id="demo-welcome-title">{welcome === 'server' ? 'Сервер запущен' : 'Новое рабочее место'}</h2>
        {welcome === 'server' ? <p>Сначала войдите как администратор и задайте название сервера.</p> : <><p>Представим, что эта версия запущена на отдельном ПК. Сначала выберите учебный сервер, затем назначьте номер рабочего места в его контуре.</p><p>Настройку выполняет администратор: войдите под его учётной записью.</p></>}
        <button type="button" onClick={() => { sessionStorage.removeItem('training112:demo-welcome'); setWelcome(''); }}>Продолжить</button>
      </div></div>}
    </div>
  );
}
function DemoTeacherWelcome({user}:{user:Obj}){
  const [visible,setVisible]=useState(()=>localStorage.getItem('training112:demo-role')==='server'&&user.role==='teacher'&&sessionStorage.getItem('training112:demo-teacher-welcome')==='true');
  if(!visible)return null;
  return <div className="demo-setup-backdrop" data-no-capture><section className="demo-setup-dialog demo-teacher-welcome" role="dialog" aria-modal="true" aria-labelledby="demo-teacher-welcome-title"><h2 id="demo-teacher-welcome-title">Теперь запустите рабочее место</h2><p>Не закрывая этого окна, запустите ещё один экземпляр приложения, там также выберите «Запустить на одном ПК».</p><p>Это будет версия клиента. В ней можно будет протестировать рабочее место студента.</p><p>Таких экземпляров можно запустить несколько.</p><img src={demoLaunchExample} alt="Запустите Dispetcher112.exe ещё раз"/><div className="demo-setup-actions"><button type="button" className="primary" onClick={()=>{sessionStorage.removeItem('training112:demo-teacher-welcome');setVisible(false);}}>Продолжить</button></div></section></div>;
}
function RequiredPasswordChange({onDone}:{onDone:(user:Obj)=>void}){
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  return <div className="password-reset-page"><form className="password-reset-card" onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const password=String(f.get('password')||'');const again=String(f.get('again')||'');if(password!==again){setError('Пароли не совпадают');return;}setBusy(true);setError('');try{onDone(await api('/change-password','POST',{password}));}catch(error:any){setError(error.message);}finally{setBusy(false);}}}><h1>Задайте новый пароль</h1><p>Временный пароль использован. Создайте свой пароль для дальнейшего входа.</p><Field label="Новый пароль"><input type="password" name="password" minLength={8} required autoComplete="new-password"/></Field><Field label="Повторите пароль"><input type="password" name="again" minLength={8} required autoComplete="new-password"/></Field><Notice>{error}</Notice><button className="primary" disabled={busy}>Сохранить пароль</button></form></div>;
}
export function App() {
  const [user, setUser] = useState<Obj | null>(null),
    [ready, setReady] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const expire = () => setUser(null);
    window.addEventListener("auth-expired", expire);
    return () => window.removeEventListener("auth-expired", expire);
  }, []);
  useEffect(() => {
    const heartbeat=()=>{if(localStorage.getItem('training112:station-token'))api('/classroom/heartbeat','POST').catch(()=>{});};
    heartbeat();
    window.addEventListener('station-ready',heartbeat);
    const timer=setInterval(heartbeat,4000);
    return()=>{clearInterval(timer);window.removeEventListener('station-ready',heartbeat);};
  }, [user?.id]);
  useEffect(() => {
    api("/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    if (user)
      api("/ui-event", "POST", {
        page: location.pathname,
        action: "navigation",
      }).catch(() => {});
  }, [location.pathname, user?.id]);
  useEffect(() => {
    if (!user) return;
    const logClick = (event: MouseEvent) => {
      const button = (event.target as HTMLElement).closest(
        "button, a, summary",
      );
      if (!button) return;
      api("/ui-event", "POST", {
        page: location.pathname,
        action:
          "click: " +
          (
            button.getAttribute("aria-label") ||
            button.getAttribute("title") ||
            button.textContent ||
            ""
          )
            .trim()
            .slice(0, 160),
      }).catch(() => {});
    };
    document.addEventListener("click", logClick, true);
    return () => document.removeEventListener("click", logClick, true);
  }, [location.pathname, user?.id]);
  if (!ready)
    return <div className="loading">Подключение к учебному серверу…</div>;
  if (!user)
    return (
      <Login
        onLogin={(u) => {
          setUser(u);
          navigate(u.role === "student" ? "/registry" : "/");
        }}
      />
    );
  if (user.must_change_password) return <RequiredPasswordChange onDone={setUser}/>;
  const links = user.role === "admin" ? [["/","Рабочие места",LayoutDashboard],["/system","Настройки",Settings],["/users","Пользователи",Users],["/tickets","Билеты",FileText],["/learning","Минивопросы",FileText],["/services","Службы",Phone],["/updates","Обновление системы",Settings]] : user.role==="teacher" ? [["/journal","Журнал",ClipboardList],["/reviews","Проверка работ",ClipboardList],["/","Рабочие места",LayoutDashboard],["/classroom/modes","Режимы",ClipboardList],["/users","Студенты",Users],["/analytics","Аналитика",BarChart3],["/tickets","Билеты",FileText],["/learning","Минивопросы",FileText]] : [
    ["/", user.role === "student" ? "Обзор" : user.role === "admin" ? "Рабочие места" : "Учебный класс", LayoutDashboard],
    ["/classroom/modes", "Режимы обучения", ClipboardList],
    ["/learning", "Учебные материалы и справочники", FileText],
    [
      "/assignments",
      user.role === "student" ? "Мои задания" : "Назначения",
      ClipboardList,
    ],
    ...(user.role !== "student"
      ? [
          ["/tickets", "Билеты", FileText],
          ["/users", "Учебные группы", Users],
        ]
      : []),
    ["/registry", "Реестр карточек", FileText],
    ["/library", "Материалы", FileText],
    ["/lessons", "Занятия", ClipboardList],
    ["/results", "Результаты", BarChart3],
    ...(user.audit_access ? [["/audit", "Журнал событий", ShieldCheck]] : []),
    ...(user.role === "admin" ? [["/system", "Система", Settings]] : []),
  ];
  return (
    <UserContext.Provider value={user}><NetworkStatus key={user.id} user={user.id}/><ClassroomClient>{user.role!=='student'&&<VoiceQueue/>}{!location.pathname.startsWith('/attempts/')&&<IntroGate/>}{user.role==='admin'&&<ServerNameSetup/>}{user.role==='admin'&&<DemoStationSetup user={user}/>}<DemoTeacherWelcome user={user}/>
      <div
        className={
          "app " + (user.role!=="student"?"staff-app ":"") +
          (location.pathname.startsWith("/attempts/") ? "workstation-app arm-app" : (location.pathname === "/" && user.role === "student") || location.pathname === "/registry" || location.pathname === "/journal" || /\/lessons\/\d+\/queue/.test(location.pathname) ? "arm-app" : "")
        }
      >
        <div className="app-body">
          <div className={"arm-training-header "+(user.role!=="student"?"admin-header":"")}>{user.role!=='student'&&<div><span>{user.name||roleNames[user.role]}<br/><b>{(links.find(l=>l[0]===location.pathname)?.[1] as string)||(location.pathname==='/lessons'?'Занятия':'Редактор билета')}</b></span><AppDeviceBadge/></div>}<ArmConsole/></div>
          <main className={user.role==='student'&&!location.pathname.startsWith('/attempts/')?'student-page-layout':''}>
            <Routes>
              <Route path="/" element={user.role === "student" ? <Registry/> : user.role === "admin" ? <AdminWorkstations/> : <TeacherWorkstations />} />
              <Route path="/classroom" element={user.role === "admin" ? <AdminWorkstations/> : <TeacherWorkstations/>}/><Route path="/classroom/modes" element={<TeacherModes/>}/><Route path="/learning" element={user.role==='student'?<LearningEditor/>:<MiniQuestions/>}/>
              <Route path="/assignments" element={<Assignments />} />
              <Route path="/attempts/:id" element={<Workspace />} />
              <Route path="/tickets" element={<Tickets />} />
              <Route path="/tickets/:id" element={<TicketEditor />} />
              <Route path="/users" element={user.role==="teacher"?<TeacherStudents/>:<People />} /><Route path="/analytics" element={<TeacherAnalytics/>}/>
              <Route path="/registry" element={<Registry />} />
              <Route path="/library" element={<Library />} />
              <Route path="/lessons" element={<Lessons />} />
              <Route path="/lessons/:id/queue" element={<DDSQueue />} />
              <Route path="/journal" element={<Registry/>}/><Route path="/reviews" element={<TeacherJournal/>}/><Route path="/results" element={<Results />} />
              <Route path="/audit" element={<Audit />} />
              <Route path="/system" element={user.role==="admin"?<ManagementSettings/>:<System />} /><Route path="/services" element={user.role==="admin"?<Services/>:<Empty text="Нет доступа"/>}/><Route path="/updates" element={user.role==="admin"?<SystemUpdates/>:<Empty text="Нет доступа"/>}/>
              <Route path="*" element={<Empty text="Страница не найдена" />} />
            </Routes>{user.role==='student'&&!location.pathname.startsWith('/attempts/')&&<StudentPanel/>}
          </main>

        </div>
      </div>
    </ClassroomClient></UserContext.Provider>
  );
}
