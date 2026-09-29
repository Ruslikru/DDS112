type RecordData=Record<string,unknown>;
const key='training112:diagnostics';
const sessionId=Array.from(crypto.getRandomValues(new Uint8Array(12)),b=>b.toString(16).padStart(2,'0')).join('');
let queue:RecordData[]=[];let sending=false;
try{queue=JSON.parse(sessionStorage.getItem(key)||'[]').slice(-30);}catch{}
function save(){try{sessionStorage.setItem(key,JSON.stringify(queue));}catch{}}
export function reportDiagnostic(kind:string,message='',extra:RecordData={}){
  queue.push({kind,message:message.slice(0,2000),path:location.pathname.slice(0,200),session_id:sessionId,
    viewport:`${innerWidth}x${innerHeight}@${devicePixelRatio}`,...extra});
  queue=queue.slice(-30);save();void flushDiagnostics();
}
export async function flushDiagnostics(){
  if(sending||!queue.length||!navigator.onLine)return;sending=true;
  try{while(queue.length){const item=queue[0];const r=await fetch('/api/diagnostics/client',{method:'POST',
    headers:{'Content-Type':'application/json','X-Requested-With':'Training112','X-Workstation':localStorage.getItem('training112:station-token')||''},body:JSON.stringify(item)});
    if(!r.ok)break;queue.shift();save();}}
  catch{}finally{sending=false;}
}
export function initializeDiagnostics(){
  window.addEventListener('error',e=>reportDiagnostic('js_error',e.message,{stack:String(e.error?.stack||'').slice(0,4000)}));
  window.addEventListener('unhandledrejection',e=>reportDiagnostic('unhandled_rejection',String(e.reason?.message||e.reason),{stack:String(e.reason?.stack||'').slice(0,4000)}));
  window.addEventListener('offline',()=>reportDiagnostic('network_offline'));
  window.addEventListener('online',()=>reportDiagnostic('network_online'));
  reportDiagnostic('ui_started');setInterval(()=>void flushDiagnostics(),15000);
}
