import React, {useState} from 'react';
import {api, Notice, useLoad, type Obj} from './shared';
import './mini-questions.css';

const blank={prompt:'',kind:'text',answer:'',options:[] as string[],level:1,active:true,audio_text:'',voice_gender:'female'};

export function MiniQuestions(){
  const {data:questions,error,load}=useLoad('/learning/questions',3000);
  const [edit,setEdit]=useState<Obj>(blank);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  const save=async(event:React.FormEvent<HTMLFormElement>)=>{
    event.preventDefault();setBusy(true);setMessage('');
    try{await api('/learning/questions'+(edit.id?'/'+edit.id:''),edit.id?'PUT':'POST',edit);setEdit(blank);await load();setMessage('Вопрос сохранён.');}
    catch(problem:any){setMessage(problem.message);}
    finally{setBusy(false);}
  };
  const toggle=async(question:Obj)=>{
    setBusy(true);setMessage('');
    try{await api('/learning/questions/'+question.id,'PUT',{...question,active:!question.active});await load();}
    catch(problem:any){setMessage(problem.message);}
    finally{setBusy(false);}
  };
  return <div className="page mini-questions-page"><h1>Минивопросы</h1><Notice>{error||message}</Notice><section className="panel mini-questions-panel"><h2 className="section-title-bar">Минивопросы</h2>
    <form className="mini-question-form" onSubmit={save}>
      <label>Вопрос<input required value={edit.prompt} onChange={event=>setEdit({...edit,prompt:event.target.value})}/></label>
      <div className="mini-question-pair"><label>Тип<select value={edit.kind} onChange={event=>setEdit({...edit,kind:event.target.value})}><option value="text">Написать текст</option><option value="choice">Выбрать вариант</option><option value="hotkey">Нажать клавиши</option></select></label><label>Минимальный уровень<input type="number" min={0} max={4} value={edit.level} onChange={event=>setEdit({...edit,level:Number(event.target.value)})}/></label></div>
      <label>Текст для озвучки (не показывается ученику)<textarea value={edit.audio_text||''} onChange={e=>setEdit({...edit,audio_text:e.target.value})} placeholder="Например: Москва, улица Декабристов, дом 28"/></label><label>Голос<select value={edit.voice_gender||'female'} onChange={e=>setEdit({...edit,voice_gender:e.target.value})}><option value="female">Женский</option><option value="male">Мужской</option></select></label><p>При сохранении запись добавится в очередь генерации. Вопрос появится в обучении после готовности звука.</p>
      <label>Правильный ответ<input required value={edit.answer} onChange={event=>setEdit({...edit,answer:event.target.value})}/></label>
      {edit.kind==='choice'&&<label>Варианты, каждый с новой строки<textarea value={edit.options.join('\n')} onChange={event=>setEdit({...edit,options:event.target.value.split('\n')})}/></label>}
      <div className="mini-question-buttons"><button className="primary" disabled={busy}>{edit.id?'Сохранить изменения':'Сохранить вопрос'}</button>{edit.id&&<button type="button" onClick={()=>setEdit(blank)}>Отмена</button>}</div>
    </form>
    <div className="mini-question-list">{questions?.map((question:Obj)=><div className="catalog-row" key={question.id}><span>{question.prompt}{question.audio_status&&<small>{question.audio_status==='ready'?'Звук готов':question.audio_status==='failed'?'Ошибка озвучки: '+question.audio_error:'Звук генерируется…'}</small>}{question.audio_id&&<audio controls src={'/api/media/'+question.audio_id}/>} {!question.active&&' · скрыт'}</span><div><button type="button" onClick={()=>{setEdit(question);window.scrollTo({top:0,behavior:'smooth'});}}>Изменить</button><button type="button" disabled={busy} onClick={()=>toggle(question)}>{question.active?'Удалить из обучения':'Вернуть'}</button></div></div>)}</div>
  </section></div>;
}
