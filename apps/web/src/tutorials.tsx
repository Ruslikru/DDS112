import React,{useState,useEffect,useRef} from 'react';
import {useNavigate} from 'react-router-dom';
import {api,useLoad,Notice,Obj} from './shared';
import {StudentHint} from './student-hint';
import './tutorials.css';

export function TutorialCatalog({revisit=false}:{revisit?:boolean}){
 const {data:profile}=useLoad('/learning/profile',3000);
 const {data,error}=useLoad('/tutorials',5000),nav=useNavigate(),[busy,setBusy]=useState(false),[err,setErr]=useState('');
 if(!profile||!revisit&&!profile.needs_onboarding)return null;
 return <section className="panel tutorial-catalog"><h2>Знакомство с программой</h2><p>Начните с билета с подсказками. Подсказки покажут, куда нажать и что заполнить. Их можно проходить повторно.</p><Notice>{error||err}</Notice><div>{data?.map((t:Obj)=><article key={t.key}><b>{t.title}</b><small>★☆☆☆☆ · пошагово{t.completed?' · пройден':''}</small>{t.voice?.ready===false&&<small role="status">{t.voice.failed?'Ошибка генерации звука — сообщите преподавателю':`Генерируется звук: ${t.voice.generated}/${t.voice.total}`}</small>}<button data-guide="tutorial-start" disabled={busy||t.voice?.ready===false} onClick={async()=>{setBusy(true);try{await api('/learning/intro','POST',{});const p=await api('/tutorials/'+t.version_id+'/start','POST');nav('/attempts/'+p.id);}catch(e:any){setErr(e.message);}finally{setBusy(false);}}}>{t.voice?.ready===false?'Ожидание звука':t.completed?'Повторить':'Начать с подсказками'}</button></article>)}</div></section>;
}

export function TutorialCoach({p,card,phoneOpen,editingStatus,contactId,contactText,selected,trainingMenu,statusError}:{p:Obj,card:Obj,phoneOpen:boolean,editingStatus:boolean,contactId:string,contactText:string,selected:string[],trainingMenu:boolean,statusError?:string}){
 const [read,setRead]=useState(sessionStorage.getItem('tutorial-read:'+p.id)==='yes');
 const [,setTick]=useState(0);
 const activity=useRef(performance.now()),stage=useRef({key:'',at:performance.now()}),seenScript=useRef(false);
 useEffect(()=>{const active=()=>{activity.current=performance.now();};const events=['pointerdown','keydown','input','change'];events.forEach(name=>document.addEventListener(name,active,true));return()=>events.forEach(name=>document.removeEventListener(name,active,true));},[p.id]);
 useEffect(()=>{const timer=setInterval(()=>setTick(x=>x+1),300);return()=>clearInterval(timer);},[]);
 const dds=p.task.mode==='dds',history=p.state.services[p.task.own_service]||[],statuses=history.map((h:Obj)=>h.status),n=p.task.onboarding?.endsWith('2')?2:1;
 const street=n===1?'Декабристов':'Конёнкова',house=n===1?'28':'26';
 let target='',text='',callScript='',step=0;
 const point=(selector:string,message:string,num:number)=>{target=selector;text=message;step=num;};
 const phone=(message:string,num:number)=>point('[data-guide="phone"]',message,num);
 const status=(name:string,message:string,num:number)=>{
  if(!editingStatus){point('button[title="Изменить статус своей службы"]','Нажмите карандаш, чтобы открыть изменение статуса.',num);return;}
  const select=document.querySelector<HTMLSelectElement>('.arm-status-form select[name="status"]');
  const comment=document.querySelector<HTMLInputElement>('.arm-status-form input[name="comment"]');
  if(select?.value!==name)point('.arm-status-form select[name="status"]',`Откройте список и выберите «${name}».`,num);
  else if(statusError?.startsWith('Проверьте комментарий.'))point('.arm-status-form input[name="comment"]',statusError,num);
  else if(!comment?.value.trim())point('.arm-status-form input[name="comment"]',`Запишите комментарий: «${message}»`,num);
  else point('button[title="Сохранить статус"]','Нажмите галочку, чтобы сохранить статус и комментарий.',num);
 };
 const contact=(message:string,num:number)=>{
  const phase=document.querySelector('.dds-voice-call')?.getAttribute('data-phase')||'idle';
  if(['ready','starting','recording','sending'].includes(phase))callScript=message;
  if(phase==='idle')point('[data-guide="voice-contact"]','Нажмите «Позвонить» рядом со «Старший бригады».',num);
  else if(phase==='dialing'||phase==='greeting')point('.dds-voice-call .phone-phase',phase==='dialing'?'Идёт соединение. Дождитесь ответа бригады.':'Прослушайте приветствие бригады.',num);
  else if(phase==='recording')point('.dds-voice-call .voice-mic','Говорите, удерживая кнопку. Закончив сообщение, отпустите её.',num);
  else if(phase==='sending')point('.dds-voice-call .phone-phase','Сообщение отправляется. Прослушайте ответ бригады.',num);
  else point('.dds-voice-call .voice-mic','Удерживайте микрофон и передайте заявку бригаде.',num);
 };
 const incoming=(message:string,num:number)=>point(p.state.incoming_calls?.length?'[data-guide=accept]':'[data-guide=phone]',p.state.incoming_calls?.length?'Бригада звонит. Примите звонок и прослушайте доклад.':message,num);
 if(p.state.tutorial_result_seen)return null;
 if(['completed','aborted'].includes(p.status))return <section className="tutorial-progress"><b>Вводный билет завершён</b><p>Нажмите «Результат» в управлении обучением. Пока ИИ анализирует работу, можно решать минивопросы — это тренировка, они не влияют на оценку.</p>{p.assessment&&<StudentHint dismissible={false} target='[data-guide=training-result]'><b>Посмотрите результат</b><p>Здесь появится оценка и разбор работы. Во время анализа доступны минивопросы для тренировки.</p></StudentHint>}</section>;
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
  if(!read)point('.arm-address-read','Прочитайте адрес и описание происшествия. Затем нажмите «Карточку прочитал».',1);
  else if(!statuses.includes('Принята'))status('Принята','Карточка принята, сведения прочитаны.',2);
  else if(count<1)contact(`Москва, ${street}, ${house}. ${p.card.description}`,3);
  else if(!statuses.includes('Начало реагирования'))status('Начало реагирования','Бригада приняла заявку и выехала.',4);
  else if(!p.state.received_stages?.includes('arrived'))incoming('Ожидайте звонка бригады о прибытии. Повторно звонить сейчас не нужно.',5);
  else if(!statuses.includes('Прибытие'))status('Прибытие','Бригада сообщила о прибытии.',6);
  else if(!statuses.includes('Проведение работ'))status('Проведение работ','Бригада проверяет обстановку и устраняет проблему.',7);
  else if(!p.state.received_stages?.includes('done'))incoming('Ожидайте доклада бригады о завершении работ.',8);
  else if(!statuses.includes('Работы завершены'))status('Работы завершены','По докладу бригады работы завершены, опасность устранена.',9);
  else point(trainingMenu?'[data-guide="finish"]':'[data-guide="training"]',trainingMenu?'Завершите учебную попытку и посмотрите результат.':'Откройте управление обучением справа: можно завершать билет.',10);
 }
 const action=target+'|'+text;
 if(stage.current.key!==action)stage.current={key:action,at:performance.now()};
 const recording=!!document.querySelector('.dds-voice-call[data-phase="recording"]');
 const showHint=n===1||performance.now()-Math.max(activity.current,stage.current.at)>=3000||recording&&seenScript.current;
 if(showHint&&callScript)seenScript.current=true;
 return <section className="tutorial-progress"><b>Первые шаги · {dds?'ДДС':'112'}</b><small>Шаг {step} из {dds?10:11}</small><p>{showHint?text:'Выполняйте знакомые действия самостоятельно. Подсказка появится, если вы задержитесь.'}</p>{showHint&&callScript&&<blockquote className="tutorial-call-script" data-guide="call-script"><strong>Передайте бригаде</strong>{callScript}</blockquote>}{dds&&!read&&<button onClick={()=>{setRead(true);sessionStorage.setItem('tutorial-read:'+p.id,'yes');}}>Карточку прочитал</button>}{showHint&&<StudentHint dismissible={false} key={target+step} target={target}><b>Шаг {step}</b><p>{text}</p>{callScript&&<blockquote className="tutorial-call-script" data-guide="call-script"><strong>Передайте бригаде</strong>{callScript}</blockquote>}{dds&&!read&&<button onClick={()=>{setRead(true);sessionStorage.setItem('tutorial-read:'+p.id,'yes');}}>Карточку прочитал</button>}</StudentHint>}</section>;
}
