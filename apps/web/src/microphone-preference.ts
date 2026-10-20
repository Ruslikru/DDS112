const KEY='training112:assistant-mic';
export const MICROPHONE_CHANGED='training112:microphone-changed';
export function selectedMicrophone(){try{return localStorage.getItem(KEY)||'';}catch{return '';}}
export function selectMicrophone(id:string){
 try{if(id)localStorage.setItem(KEY,id);else localStorage.removeItem(KEY);}catch{}
 window.dispatchEvent(new Event(MICROPHONE_CHANGED));
}
