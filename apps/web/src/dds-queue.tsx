import React from 'react';
import {useParams} from 'react-router-dom';
import {ArmJournal} from './arm-journal';
export function DDSQueue({lessonId,studentId}:{lessonId?:number,studentId?:number}){
 const {id}=useParams();
 return <ArmJournal queue endpoint={`/lessons/${lessonId||Number(id)}/queue${studentId?'?student_id='+studentId:''}`}/>;
}
