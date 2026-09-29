import React, { useEffect, useState, useRef } from "react";
import { AISettings } from './ai';

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
import { Metric } from "./dashboard";
import { ClassifierPicker } from "./tickets";
export { People } from './people';
export function Audit() {
  const [q, setQ] = useState(""),
    [offset, setOffset] = useState(0),
    { data, error } = useLoad(
      "/audit?q=" + encodeURIComponent(q) + "&offset=" + offset,
      5000,
    );
  return (
    <div className="page">
      <Heading eyebrow="КОНТРОЛЬ И ПРОСЛЕЖИВАЕМОСТЬ" title="Журнал событий" />
      <Notice>{error}</Notice>
      <div className="toolbar">
        <input
          placeholder="Фильтр по событию: login, draft, status…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
        />
        <span>Записи доступны только пользователям с правом аудита</span>
      </div>
      <div className="panel table-panel">
        <table>
          <thead>
            <tr>
              <th>ID / время</th>
              <th>Пользователь</th>
              <th>Событие</th>
              <th>Объект</th>
              <th>Подробности</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((e: Obj) => (
              <tr key={e.id}>
                <td>
                  <small>#{e.id}</small>
                  {new Date(e.at).toLocaleString("ru")}
                </td>
                <td>{e.actor}</td>
                <td>
                  <code>{e.action}</code>
                </td>
                <td>{e.target || "—"}</td>
                <td>
                  <details>
                    <summary>Данные события</summary>
                    <pre>{JSON.stringify(e.detail, null, 2)}</pre>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          Новее
        </button>
        <span>
          {offset + 1}–{offset + (data?.length || 0)}
        </span>
        <button
          disabled={data?.length < 100}
          onClick={() => setOffset(offset + 100)}
        >
          Старее
        </button>
      </div>
    </div>
  );
}
export function System() {
  const { data, error } = useLoad("/system");
  return (
    <div className="page">
      <Heading eyebrow="ИНФРАСТРУКТУРА" title="Состояние системы" />
      <Notice>{error}</Notice>
      <AISettings/>
      <section className="panel form-panel"><h2>Диагностика тестирования</h2><p>Ошибки, запросы и работа модели записываются локально. Архив доступен администратору и не содержит базу пользователей или тексты карточек.</p><a className="button" href="/api/diagnostics/bundle">Скачать диагностический архив</a><p>При сообщении об ошибке укажите время, роль и номер попытки.</p></section>
      <div className="metrics">
        <Metric
          label="База данных"
          value={data?.database || "…"}
          sub="Пользователи, сценарии, попытки, аудит"
        />
        <Metric
          label="Классификатор"
          value={data?.classifier_count || 0}
          sub="Типов из исходной таблицы"
        />
        <Metric
          label="Учебный контур"
          value="Локальный"
          sub="Интернет для работы не требуется"
        />
        <Metric
          label="Версия"
          value={data?.version || "…"}
          sub="Базовый тренажёр 112 / ДДС"
        />
      </div>
      <div className="panel form-panel">
        <h2>Эксплуатация</h2>
        <p>
          Сервер работает на ПК. Другие устройства подключаются к его адресу в
          локальной сети. Карточки, оценки и журнал сохраняются в базе данных,
          аудио — в локальном хранилище сервера.
        </p>
        <h3>Что входит в эту версию</h3>
        <p>
          Два режима работы, назначение и прохождение билетов, запись MP3/WAV,
          проверка по критериям и ручная оценка, статистика ошибок, управление
          пользователями и журнал событий.
        </p>
        <h3>Границы учебной среды</h3>
        <p>
          Реальная телефония, интеграция с боевой Системой-112, VR и речевые
          модели не подключены. Начальные эталоны демонстрационные. Перед
          учебной эксплуатацией их должен проверить преподаватель.
        </p>
        <h3>Резервное копирование</h3>
        <p>
          Инструкция и команды резервного копирования находятся в README
          проекта. Копируйте базу и папку с аудио совместно. Восстановление
          выполняется администратором сервера.
        </p>
      </div>
      <div className="panel form-panel">
        <h3>Исходный классификатор</h3>
        <ClassifierPicker />
      </div>
    </div>
  );
}
