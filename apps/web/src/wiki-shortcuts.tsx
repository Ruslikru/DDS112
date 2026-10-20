import React,{useState} from 'react';
import {Keyboard,Search,X,ChevronRight} from 'lucide-react';
import './wiki-shortcuts.css';
const reference:[string,[string,string][]][]=[
 ['Основные',[
 ['Alt (удерживать)','Показать доступные комбинации клавиш на странице карточки'],['Insert','Создать новую карточку (оператор 112)'],['Esc','Закрыть карточку или всплывающее окно'],['Tab / Shift + Tab','Перейти вперёд / назад между полями и кнопками карточки'],['Ctrl + F5','Обновить список происшествий и журнал']]],
 ['Поля карточки',[
 ['Alt + F1 / Alt + F2 / Alt + F3','Блоки телефонных номеров'],['Alt + K','Канал связи'],['Alt + Q','Заявитель'],['Alt + A','Адрес'],['Alt + P','Пострадавшие'],['Alt + N','Нет контакта / срыв звонка'],['Alt + T','Что случилось'],['Alt + R','Выбор значимого типа происшествия'],['Alt + O','Описание'],['Alt + Z','Управление службами'],['Alt + n','Добавленная опросная карта: n — её номер (например, Alt + 1)'],['Alt + Ctrl + n','Вопрос в опросной карте: n — номер вопроса']]],
 ['Создание карточки',[
 ['Alt + S','Сохранить карточку'],['Alt + W','Создать связь'],['Alt + B','Создать напоминание'],['Alt + V','Отметить происшествие как важное'],['Alt + M','Создать сообщение об ошибке']]],
 ['Просмотр карточки',[
 ['Alt + O','Перейти к блоку отработок'],['Shift + F1','Просмотр'],['Shift + F2','Дополнить'],
 ['Alt + S','Отработана / Завершить — в зависимости от статуса карточки'],['Alt + W','Создать связь'],['Alt + B','Создать напоминание'],['Alt + V','Отметить происшествие как важное'],['Alt + Y','Проверена — при доступности этого статуса'],['Alt + N','Вернуть на доработку — при доступности этого статуса']]],
 ['Добавление связи',[
 ['Alt + 1','Поиск происшествия'],['Alt + 2','Список происшествий'],['Alt + 3','Кнопка возврата']]],
];

function KeyCombination({value}:{value:string}){
 const hold=value.includes('(удерживать)');
 return <span className="hotkey-combination">{value.replace(' (удерживать)','').split(' / ').map((variant,i)=><React.Fragment key={variant}>{i>0&&<span className="hotkey-alternative">или</span>}<span className="hotkey-keys">{variant.split(' + ').map((key,j)=><React.Fragment key={key}>{j>0&&<span className="hotkey-plus">+</span>}<kbd>{key}</kbd></React.Fragment>)}</span></React.Fragment>)}{hold&&<span className="hotkey-hold">удерживать</span>}</span>;
}
export function WikiShortcuts({operator112}:{operator112:boolean}){
 const [query,setQuery]=useState(''),[category,setCategory]=useState('Все сочетания');
 const groups:[string,[string,string][]][]=[...reference,['Телефон и ассистент',[
 ['Ctrl + Space (удерживать)','Говорить ассистенту или по активному телефону'],['Enter / Shift + Enter','Отправить команду ассистенту / перенести строку'],...(operator112?[['Ctrl + Enter','Принять входящий звонок 112'] as [string,string]]:[])
 ]]];
 const needle=query.trim().toLocaleLowerCase('ru');
 const shown=groups.filter(([title])=>category==='Все сочетания'||category===title).map(([title,rows])=>[title,rows.filter(([key,action])=>(key+' '+action+' '+title).toLocaleLowerCase('ru').includes(needle))] as [string,[string,string][]]).filter(([,rows])=>rows.length);
 return <section className="hotkeys-reference" aria-labelledby="hotkeys-title"><header className="hotkeys-heading"><Keyboard size={23} aria-hidden="true"/><h2 id="hotkeys-title">Горячие клавиши</h2></header>
 <div className="hotkeys-search"><Search size={18} aria-hidden="true"/><input aria-label="Найти горячую клавишу" placeholder="Найти сочетание или действие" value={query} onChange={e=>{setQuery(e.target.value);setCategory('Все сочетания');}}/>{query&&<button type="button" onClick={()=>setQuery('')} aria-label="Очистить поиск клавиш"><X size={17}/></button>}</div>
 <div className="hotkeys-layout"><nav className="hotkeys-categories" aria-label="Разделы горячих клавиш">{['Все сочетания',...groups.map(([title])=>title)].map(title=><button type="button" key={title} aria-pressed={category===title} onClick={()=>{setCategory(title);setQuery('');}}><span>{title}</span><ChevronRight size={15} aria-hidden="true"/></button>)}</nav>
 <div className="hotkeys-content" aria-live="polite">{shown.length?shown.map(([title,rows])=><section className="hotkeys-group" key={title}><h3>{title}</h3><table><thead><tr><th scope="col">Сочетание</th><th scope="col">Действие</th></tr></thead><tbody>{rows.map(([keys,action])=><tr key={keys}><td><KeyCombination value={keys}/></td><td>{action}</td></tr>)}</tbody></table></section>):<div className="hotkeys-empty"><Search size={24}/><h3>Ничего не найдено</h3><p>Попробуйте название клавиши или действия, например «адрес».</p><button type="button" onClick={()=>setQuery('')}>Сбросить поиск</button></div>}</div></div></section>;
}
