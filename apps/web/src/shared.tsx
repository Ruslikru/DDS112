import React, { useEffect, useState, useRef } from "react";
import { reportDiagnostic, flushDiagnostics } from './diagnostics';

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

export type Obj = Record<string, any>;
// getRandomValues works on local-network HTTP, where randomUUID may be unavailable.
export function uuid() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
export async function api(path: string, method = "GET", body?: any) {
  const requestId=uuid();
  let r:Response;
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),path==="/me" || /\/attempts\/[^/]+(?:\/command)?$/.test(path)?7000:180000);
  try { r = await fetch("/api" + path, {
    method,
    signal:controller.signal,
    headers: {
      "X-Requested-With": "Training112",
      "X-Request-ID": requestId,
      "X-Workstation": localStorage.getItem("training112:station-token")||"",
      ...(body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
    },
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  }); } catch(error) { reportDiagnostic('network_error',method+' /api'+path.split('?')[0],{request_id:requestId});window.dispatchEvent(new Event('training-network-failed'));throw Object.assign(new Error('Нет связи с локальным сервером'),{network:true}); } finally {clearTimeout(timeout);}
  const data = await r.json().catch(() => ({ detail: "Сервер недоступен" }));
  if (r.status === 401) window.dispatchEvent(new Event("auth-expired"));
  if (!r.ok) {
    if(r.status!==401)reportDiagnostic('api_error',`${method} /api${path.split('?')[0]}: ${r.status}`,{request_id:r.headers.get('X-Request-ID')||requestId});
    throw Object.assign(new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    ),{status:r.status});
  }
  void flushDiagnostics();
  return data;
}
export const UserContext = React.createContext<Obj>({});
export const roleNames: Obj = {
  student: "Ученик",
  teacher: "Преподаватель",
  admin: "Администратор",
};
export const statusNames: Obj = {
  ringing: "Входящий вызов",
  active: "В работе",
  paused: "Пауза",
  completed: "Завершено",
  aborted: "Прервано",
};
export const services = [
  "Служба 101",
  "Служба 102",
  "Служба 103",
  "Служба 104",
  "ДДС района",
  "Мослифт",
  "ЦОДД",
  "Мосводоканал",
  "Деп. ЖКХ",
  "ЦЭМП",
];
export const labels: Obj = {
  name: "ФИО заявителя",
  caller_status: "Статус заявителя",
  phone: "Телефон заявителя",
  contact_phone: "Контактный телефон",
  site_phone: "Телефон с места",
  region: "Субъект РФ",
  city: "Город / населённый пункт",
  country: "Страна",
  district: "Округ",
  area: "Район",
  object: "Объект",
  structure: "Строение / сооружение",
  street: "Улица",
  house: "Дом",
  building: "Корпус / строение",
  apartment: "Квартира",
  entrance: "Подъезд",
  floor: "Этаж",
  code: "Код домофона",
  address_note: "Дополнение к адресу",
  description: "Описание происшествия",
  incident_type: "Тип происшествия",
  victims: "Пострадавшие",
  victims_count: "Количество пострадавших",
  traits: "Признаки",
  medical_refusal: "Отказ от скорой",
  blocked: "Заблокированные",
  no_contact: "Нет контакта",
  call_lost: "Срыв звонка",
};
export function useLoad(path: string, interval = 0) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  const current=useRef(path);current.current=path;
  const serial=useRef(0);
  const load = () => {const request=++serial.current;return api(path)
      .then((value) => {if(current.current===path&&request===serial.current){setData(value);setError("");}})
      .catch((e) => {if(current.current===path&&request===serial.current)setError(e.message);});};
  useEffect(() => {setData(null);load();const id=interval?setInterval(load,interval):undefined;return()=>{serial.current++;if(id)clearInterval(id);};},[path,interval]);
  return { data, error, load, setData };
}
export function Notice({ children }: { children: any }) {
  return children ? (
    <div className="notice" role="alert">
      {children}
    </div>
  ) : null;
}
export function Badge({
  children,
  tone = "",
}: {
  children: any;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}
export function Field({ label, children }: { label: string; children: any }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Empty({ text = "Здесь пока нет данных" }: { text?: string }) {
  return (
    <div className="empty">
      <FileText size={32} />
      <h3>{text}</h3>
      <p>Новые записи появятся после работы с тренажёром.</p>
    </div>
  );
}
export function Heading({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children?: any;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
      </div>
      {children}
    </div>
  );
}
export function TextCheck({text}:{text:string}){
 const [result,setResult]=React.useState<Obj|null>(null),[error,setError]=React.useState('');
 React.useEffect(()=>{setResult(null);},[text]);
 return <div className="text-check"><button type="button" className="small" onClick={async()=>{try{setResult(await api('/text-check','POST',{text}));setError('');}catch(e:any){setError(e.message);}}}>Проверить оформление текста</button><Notice>{error}</Notice>{result&&<div><small>{result.method}</small>{result.issues.length?result.issues.map((x:Obj,i:number)=><p key={i}>{x.message}: «{x.fragment}»</p>):<p>По доступным правилам замечаний нет.</p>}</div>}</div>;
}
