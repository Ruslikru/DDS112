import React,{useContext} from 'react';
import {Link,useLocation} from 'react-router-dom';
import {UserContext} from './shared';
import './tutorials.css';
export function StudentPanel(){
 const u=useContext(UserContext),location=useLocation();
 if(u.role!=='student')return <nav className="student-learning-nav"><Link to={u.role==='teacher'?'/journal':'/tickets'}>{u.role==='teacher'?'Вернуться в журнал':'Вернуться к билетам'}</Link></nav>;
 return <section className="student-learning-panel"><h2>Обучение</h2><small>{u.name}</small><nav className="student-learning-nav" aria-label="Учебные разделы">{[['/assignments','Мои билеты'],['/results','Мой прогресс'],['/lessons','Занятия с преподавателем']].map(([url,title])=><Link key={url} to={url} className={location.pathname===url?'active':''}>{title}</Link>)}</nav></section>;
}
