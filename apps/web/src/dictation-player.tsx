import React,{useEffect,useRef,useState} from 'react';
import {Volume2} from 'lucide-react';
import {audioResource,releaseAudio} from './audio-resource';
import {Notice} from './shared';

export function DictationPlayer({id}:{id:string}){
 const player=useRef<HTMLAudioElement>(null),[url,setUrl]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let alive=true,loaded='';audioResource('/api/media/'+id).then(value=>{loaded=value;if(alive)setUrl(value);else releaseAudio(value);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;player.current?.pause();releaseAudio(loaded);};},[id]);
 return <div className="dictation-player"><button type="button" disabled={!url||busy} onClick={async()=>{try{setError('');setBusy(true);const audio=player.current!;audio.currentTime=0;await audio.play();}catch(e:any){setError(e.message);setBusy(false);}}}><Volume2 size={18}/>{busy?'Слушайте запись…':'Прослушать запись'}</button><audio ref={player} src={url||undefined} onEnded={()=>setBusy(false)} onError={()=>{setBusy(false);setError('Не удалось воспроизвести запись.');}}/><Notice>{error}</Notice></div>;
}
