import {Check} from 'lucide-react';
import {type Obj} from './shared';
import './teacher-ui-polish.css';

export function confirmedTeacherReview(assessment:Obj){
  const reviews=assessment?.reviews||[];
  const last=reviews[reviews.length-1];
  return last?.confirm===true&&!assessment.pending&&!assessment.ai_preliminary?last:null;
}

export function TeacherReviewMark({assessment,details=false}:{assessment:Obj;details?:boolean}){
  const last=confirmedTeacherReview(assessment);
  if(!last)return null;
  const date=last.at?new Date(last.at):null;
  const description=[last.by,date&&!Number.isNaN(date.getTime())?date.toLocaleString('ru'):null].filter(Boolean).join(' · ');
  return <div className={'teacher-review-mark'+(details?' with-details':'')}>
    <span className="teacher-reviewed-badge" title={description}><Check size={14} aria-hidden="true"/>Проверено преподавателем</span>
    {details&&description&&<small>{description}</small>}
  </div>;
}
