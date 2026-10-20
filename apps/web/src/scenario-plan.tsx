import React from 'react';
import {type Obj} from './shared';

export const accessSources:Record<string,string>={
  auto:'По сложности билета',card:'В исходной карточке',
  service_history:'В истории другой службы',caller:'Нужно уточнить у заявителя',
  unknown:'Сведений нет — допустим честный ответ',
};

export function ScenarioPlan({task}:{task:Obj}){
  const scenario=task.scenario;
  if(!scenario?.version)return null;
  const access=scenario.access, routing=scenario.routing;
  return <details className="scenario-plan" open>
    <summary>Ход задания и источники сведений</summary>
    <div className="scenario-plan-source"><strong>Уточнение подъезда</strong>
      <p>{accessSources[access.source]}{access.service?' · '+access.service:''}</p>
      <p>{access.answer}</p>
      <small>Ученик увидит сведения в указанном источнике. Каждый доклад требует отдельной записи; разговор оценивается отдельно.</small>
    </div>
    <ol>{scenario.stages.map((stage:Obj)=><li key={stage.id}>
      <strong>{stage.status||'Уточнение подъезда · статус не меняется'}</strong><p>{stage.report}</p>
    </li>)}</ol>
    {routing&&<details><summary>Основания назначения служб</summary>
      <p>{routing.matched?`Классификатор 046_11 · строка ${routing.row} · код ${routing.code}`:'Получателей необходимо проверить вручную'}</p>
      {routing.warning&&<p role="note">{routing.warning}</p>}
      {routing.unavailable?.length>0&&<p>Службы отключены в справочнике: {routing.unavailable.join(', ')}.</p>}
      {routing.entries?.length>0&&<ul>{routing.entries.map((e:Obj)=><li key={e.cell}>{e.service} · {e.value} <small>({e.cell})</small></li>)}</ul>}
      {routing.excluded?.length>0&&<p>Исключения сохранены из исходной матрицы: {routing.excluded.map((e:Obj)=>e.cell).join(', ')}.</p>}
    </details>}
  </details>;
}
