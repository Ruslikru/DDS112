// Binary audio requests need the same workstation identity as JSON requests.
export function audioHeaders(){return {'X-Requested-With':'Training112','X-Workstation':localStorage.getItem('training112:station-token')||''};}
export async function audioResource(path:string){
 const response=await fetch(path,{headers:audioHeaders(),credentials:'same-origin'});
 if(!response.ok){const body=await response.json().catch(()=>null);throw Error(body?.detail||'Не удалось загрузить звук (код '+response.status+').');}
 return URL.createObjectURL(await response.blob());
}
export function releaseAudio(url?:string){if(url?.startsWith('blob:'))URL.revokeObjectURL(url);}
