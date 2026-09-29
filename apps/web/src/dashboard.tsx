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
export function Dashboard() {
  const u = React.useContext(UserContext),
    { data: a } = useLoad("/assignments"),
    { data: r } = useLoad("/results");
  const completed = r?.length || 0;
  const scores =
    r?.map((x: Obj) => x.assessment.score).filter((x: any) => x !== null) || [];
  return (
    <div className="page">
      <Heading
        eyebrow="ГОТОВНОСТЬ К СМЕНЕ"
        title={u.role === "student" ? "Ваша учебная смена" : "Центр подготовки"}
      />
      <div className="hero">
        <div>
          <Badge tone="light">ПРАКТИКА В РЕАЛЬНОМ ИНТЕРФЕЙСЕ</Badge>
          <h2>
            Спокойствие.
            <br />
            Точность. Действие.
          </h2>
          <p>
            Отработайте приём обращения и заполнение карточки
            <br />в безопасной учебной среде.
          </p>
          <Link className="button white" to="/assignments">
            {u.role === "student" ? "Перейти к заданиям" : "Открыть назначения"}
            <ChevronRight size={18} />
          </Link>
        </div>
        <div className="hero-mark">
          <Radio size={110} strokeWidth={1} />
          <span>112 / ДДС</span>
          <small>СЛУШАТЬ · УТОЧНЯТЬ · РЕАГИРОВАТЬ</small>
        </div>
      </div>
      <div className="metrics">
        <Metric
          label="Назначений"
          value={a?.length || 0}
          sub="Доступно в учебном контуре"
        />
        <Metric
          label="Завершено попыток"
          value={completed}
          sub="История сохраняется"
        />
        <Metric
          label="Средний балл"
          value={
            scores.length
              ? Math.round(
                  scores.reduce((s: number, v: number) => s + v, 0) /
                    scores.length,
                ) + "%"
              : "—"
          }
          sub="Предварительный, до ручной проверки"
        />
        <Metric
          label="Ожидают проверки"
          value={r?.filter((x: Obj) => x.assessment.pending).length || 0}
          sub="Свободный текст проверяет преподаватель"
        />
      </div>
      <div className="section-title">
        <h2>Рабочие режимы</h2>
        <span>Два этапа обработки происшествия</span>
      </div>
      <div className="mode-grid">
        <div className="panel mode-card">
          <Phone />
          <Badge>ОПЕРАТОР 112</Badge>
          <h3>От звонка до оповещения</h3>
          <p>
            Примите вызов, уточните обстоятельства, заполните карточку и
            направьте её службам.
          </p>
        </div>
        <div className="panel mode-card">
          <Radio />
          <Badge>ДИСПЕТЧЕР ДДС</Badge>
          <h3>От карточки до результата</h3>
          <p>
            Подтвердите приём карточки, обработайте сообщения бригады и
            зафиксируйте реагирование.
          </p>
        </div>
      </div>
      <div className="method-note">
        Сценарии начального набора — демонстрационные адаптации материалов.
        Эталоны и оценки требуют проверки профильным преподавателем.
      </div>
    </div>
  );
}
export function Metric({
  label,
  value,
  sub,
}: {
  label: string;
  value: any;
  sub: string;
}) {
  return (
    <div className="panel metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}
