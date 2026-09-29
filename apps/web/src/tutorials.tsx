import React,{useState,useEffect} from 'react';
import {useNavigate} from 'react-router-dom';
import {api,useLoad,Notice,Obj} from './shared';
import {StudentHint} from './student-hint';
import './tutorials.css';

export function TutorialCatalog(){
 const {data,error}=useLoad('/tutorials',5000),nav=useNavigate(),[busy,setBusy]=useState(false),[err,setErr]=useState('');
 return <section className="panel tutorial-catalog"><h2>Знакомство с программой</h2><p>Начните с этих четырёх билетов. Подсказки покажут, куда нажать и что заполнить. Их можно проходить повторно.</p><Notice>{error||err}</Notice><div>{data?.map((t:Obj)=><article key={t.key}><b>{t.title}</b><small>★☆☆☆☆ · пошагово{t.completed?' · пройден':''}</small>{t.voice?.ready===false&&<small role="status">{t.voice.failed?'Ошибка генерации звука — сообщите преподавателю':`Генерируется звук: ${t.voice.generated}/${t.voice.total}`}</small>}<button disabled={busy||t.voice?.ready===false} onClick={async()=>{setBusy(true);try{const p=await api('/tutorials/'+t.version_id+'/start','POST');nav('/attempts/'+p.id);}catch(e:any){setErr(e.message);}finally{setBusy(false);}}}>{t.voice?.ready===false?'Ожидание звука':t.completed?'Повторить':'Начать с подсказками'}</button></article>)}</div></section>;
}

export function TutorialCoach({p,card,phoneOpen,editingStatus,contactId,contactText,selected,trainingMenu}:{p:Obj,card:Obj,phoneOpen:boolean,editingStatus:boolean,contactId:string,contactText:string,selected:string[],trainingMenu:boolean}){
 const [read,setRead]=useState(sessionStorage.getItem('tutorial-read:'+p.id)==='yes'),[visible,setVisible]=useState(true);
 const [,setTick]=useState(0);
 useEffect(()=>{const timer=setInterval(()=>setTick(x=>x+1),300);return()=>clearInterval(timer);},[]);
 const dds=p.task.mode==='dds',history=p.state.services[p.task.own_service]||[],statuses=history.map((h:Obj)=>h.status),n=p.task.onboarding?.endsWith('2')?2:1;
 const street=n===1?'Декабристов':'Конёнкова',house=n===1?'28':'26';
 let target='',text='',step=0;
 const point=(selector:string,message:string,num:number)=>{target=selector;text=message;step=num;};
 const phone=(message:string,num:number)=>point('[data-guide="phone"]',message,num);
 const status=(name:string,message:string,num:number)=>point(editingStatus?'button[title="Сохранить статус"]':'button[title="Изменить статус своей службы"]',editingStatus?`Выберите «${name}», запишите в комментарии: «${message}». Нажмите галочку для сохранения.`:`Откройте изменение статуса своей службы. Следующий статус — «${name}». ${message}`,num);
 const contact=(message:string,num:number)=>{if(document.querySelector('.voice-mic.ready,.voice-mic.recording'))point('.voice-mic',message+' Нажмите микрофон, произнесите сообщение и нажмите ещё раз. Прослушайте ответ.',num);else point('[data-guide=voice-contact]',message+' Нажмите «Старший бригады», дождитесь приветствия и включите микрофон.',num);};
 const incoming=(message:string,num:number)=>point(p.state.incoming_calls?.length?'[data-guide=accept]':'[data-guide=phone]',p.state.incoming_calls?.length?'Бригада звонит. Примите звонок и прослушайте доклад.':message,num);
 if(['completed','aborted'].includes(p.status))return <section className="tutorial-progress"><b>Вводный билет завершён</b><p>Теперь можно повторить его или перейти к следующему в «Моих билетах».</p></section>;
 if(!dds){
  if(p.state.call==='ringing'){if(!phoneOpen)phone('Нажмите на телефон, чтобы открыть входящий вызов.',1);else point('[data-guide="accept"]','Нажмите «Принять звонок» и прослушайте первое сообщение заявителя.',1);}

  else if(card.name?.trim()!=='Елена Андреевна Соколова')point('input[aria-label="Фамилия и имя заявителя"]','Запишите имя заявителя. Если не расслышали, уточните голосом через микрофон.',2);
  else if(!card.caller_status)point('select[aria-label="Статус заявителя"]','Выберите статус «очевидец»: заявитель видит происшествие.',3);
  else if(card.street?.trim()!==street)point('[data-field="street"]',`Запишите улицу: ${street}. При необходимости уточните её голосом.`,4);
  else if(card.house?.trim()!==house)point('[data-field="house"]',`Введите номер дома: ${house}.`,5);
  else if((card.description?.trim().length||0)<15)point('textarea[aria-label="Описание со слов заявителя"]','Кратко запишите, что случилось и что пострадавших нет. Если сведений не хватает, уточните их голосом.',6);
  else if(!card.incident_type)point('select[aria-label="Тип происшествия"]','Выберите тип происшествия из списка.',7);
  else if(card.victims!=='no')point('select[aria-label="Пострадавшие"]','Заявитель сообщил, что пострадавших нет. Выберите «нет».',8);
  else if(!Object.keys(p.state.services).length){if(document.querySelector('.arm-service-options')&&selected.includes(p.task.services[0]))point('[data-guide=apply-services]','Нажмите «применить», затем сохраните карточку.',9);else if(selected.includes(p.task.services[0]))point('.arm-save','Нажмите «СОХРАНИТЬ»: карточка сохранится, выбранная служба получит заявку.',9);else if(document.querySelector('.arm-service-options'))point('.arm-service-options button',`Выберите «${p.task.services[0]}», затем «применить».`,9);else point('button[title="Добавить службу"]',`Добавьте получателя «${p.task.services[0]}».`,9);}
  else if(p.state.call!=='ended'){if(!phoneOpen)phone('Откройте телефон, чтобы закончить разговор после передачи заявки.',10);else point('[data-guide="end-call"]','Нажмите «Завершить разговор». Заявка уже передана службе.',10);}
  else point(trainingMenu?'[data-guide="finish"]':'[data-guide="training"]',trainingMenu?'Нажмите «Завершить работу», чтобы увидеть результат.':'Откройте управление обучением в правой панели. Все основные действия выполнены.',11);
 }else{
  const count=p.state.contact_counts?.brigade||0;
  if(!read)point('.arm-address-read','Прочитайте адрес и описание. ДДС получает заполненную карточку: заново вводить сведения не требуется.',1);
  else if(!statuses.includes('Принята'))status('Принята','Карточка принята, сведения прочитаны.',2);
  else if(count<1)contact(`Передайте бригаде: Москва, улица ${street}, дом ${house}. ${p.card.description}`,3);
  else if(!statuses.includes('Начало реагирования'))status('Начало реагирования','Бригада приняла заявку и выехала.',4);
  else if(!p.state.received_stages?.includes('arrived'))incoming('Ожидайте звонка бригады о прибытии. Повторно звонить сейчас не нужно.',5);
  else if(!statuses.includes('Прибытие'))status('Прибытие','Бригада сообщила о прибытии.',6);
  else if(!statuses.includes('Проведение работ'))status('Проведение работ','Бригада проверяет обстановку и устраняет проблему.',7);
  else if(!p.state.received_stages?.includes('done'))incoming('Ожидайте доклада бригады о завершении работ.',8);
  else if(!statuses.includes('Работы завершены'))status('Работы завершены','По докладу бригады работы завершены, опасность устранена.',9);
  else point(trainingMenu?'[data-guide="finish"]':'[data-guide="training"]',trainingMenu?'Завершите учебную попытку и посмотрите результат.':'Откройте управление обучением справа: можно завершать билет.',10);
 }
 return <section className="tutorial-progress"><b>Первые шаги · {dds?'ДДС':'112'}</b><small>Шаг {step} из {dds?10:11}</small><p>{text}</p><button onClick={()=>setVisible(!visible)}>{visible?'Скрыть стрелку':'Показать стрелку'}</button>{dds&&!read&&<button onClick={()=>{setRead(true);sessionStorage.setItem('tutorial-read:'+p.id,'yes');}}>Карточку прочитал</button>}{visible&&<StudentHint key={target+step} target={target} onClose={()=>setVisible(false)}><b>Шаг {step}</b><p>{text}</p>{dds&&!read&&<button onClick={()=>{setRead(true);sessionStorage.setItem('tutorial-read:'+p.id,'yes');}}>Карточку прочитал</button>}</StudentHint>}</section>;
}
