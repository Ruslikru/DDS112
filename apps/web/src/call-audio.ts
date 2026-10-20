import {audioHeaders} from './audio-resource';
import {api,Obj} from './shared';

// One engine per handset. Backgrounds never restart between speech turns.
export class CallAudioEngine {
 private context?:AudioContext;
 private bus?:GainNode;
 private output?:DynamicsCompressorNode;
 private buffers=new Map<string,AudioBuffer>();
 private sources=new Set<AudioBufferSourceNode>();
 private timers=new Set<ReturnType<typeof setTimeout>>();
 private pending=new Set<()=>void>();
 private assets?:Obj;
 private epoch=0;
 private closed=false;
 private scene:Obj={};
 private primary=new WeakSet<HTMLMediaElement>();
 private waiting=false;
 private filler:Promise<void>=Promise.resolve();
 async loadManifest(){this.assets??=(await api('/call-audio/library')).assets;return this.assets!;}
 async unlock(){
  if(this.closed)throw Error('Разговор завершён');
  if(!this.context){
   this.context=new AudioContext();this.output=this.context.createDynamicsCompressor();
   this.output.threshold.value=-3;this.output.ratio.value=16;this.output.connect(this.context.destination);
   this.bus=this.context.createGain();this.bus.connect(this.output);
  }
  await this.context.resume();
 }
 private async buffer(id:string){
  if(this.buffers.has(id))return this.buffers.get(id)!;
  const assets=await this.loadManifest(),row=assets[id];
  if(!row)throw Error('Нет звукового файла: '+id);
  const response=await fetch(row.url,{headers:audioHeaders(),credentials:'same-origin'});if(!response.ok)throw Error('Не удалось загрузить звуковое окружение');
  const bytes=await response.arrayBuffer();if(bytes.byteLength!==row.bytes)throw Error('Звуковой файл повреждён');
  // On LAN HTTP the server performs SHA-256 verification; secure contexts also verify locally.
  if(crypto.subtle){const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');if(digest!==row.sha256)throw Error('Контрольная сумма звукового файла не совпала');}
  if(this.closed||!this.context)throw Error('Разговор завершён');
  const buffer=await this.context.decodeAudioData(bytes);
  if(Math.abs(buffer.duration-row.seconds)>.15)throw Error('Неверная длительность звукового файла');
  if(this.buffers.size>=8)this.buffers.delete(this.buffers.keys().next().value!);
  this.buffers.set(id,buffer);return buffer;
 }
 async prepare(scene:Obj={}){
  await this.unlock();await this.loadManifest();
  const ids=Array.from(new Set<string>(['ring','ringback','hangup',...(scene.backgrounds||[]),...(scene.ambient_events||[]),...(scene.events_after_reply||[]).map((x:Obj)=>x.id)]));
  for(let n=0;n<ids.length;n+=3)await Promise.all(ids.slice(n,n+3).map(id=>this.buffer(id)));
 }
 private play(id:string,loop=false,background=false,volume=.4,maxSeconds?:number){
  const buffer=this.buffers.get(id);if(!buffer||!this.context||!this.output||!this.bus)return Promise.resolve();
  const source=this.context.createBufferSource(),gain=this.context.createGain();source.buffer=buffer;source.loop=loop;
  gain.gain.value=volume;source.connect(gain);gain.connect(background?this.bus:this.output);this.sources.add(source);
  return new Promise<void>(resolve=>{const done=()=>{this.sources.delete(source);this.pending.delete(done);source.disconnect();gain.disconnect();resolve();};this.pending.add(done);source.onended=done;source.start();if(maxSeconds!==undefined)source.stop(this.context!.currentTime+Math.min(maxSeconds,buffer.duration));});
 }
 private later(fn:()=>void,ms:number){const timer=setTimeout(()=>{this.timers.delete(timer);fn();},ms);this.timers.add(timer);}
 async signal(id:'ring'|'ringback'|'hangup',loop=false){const epoch=this.epoch;await this.unlock();await this.buffer(id);if(epoch===this.epoch)void this.play(id,loop,false,.4,id==='hangup'?1:undefined);}
 stop(){
  this.waiting=false;this.epoch++;for(const timer of this.timers)clearTimeout(timer);this.timers.clear();
  for(const source of this.sources){try{source.stop();}catch{}}this.sources.clear();
  for(const done of [...this.pending])done();
 }
 async connect(scene:Obj={}){
  this.stop();const epoch=this.epoch;await this.prepare(scene);if(epoch!==this.epoch)return;
  this.scene=scene;this.duck(false);
  for(const id of scene.backgrounds||[]){const rms=this.assets?.[id]?.rms||.1;void this.play(id,true,true,Math.min(4,.1/rms)*.22*(id==='bg_siren_distant'?.55:1));}
  for(const id of scene.ambient_events||[]){const next=()=>this.later(()=>{if(epoch===this.epoch){void this.play(id,false,false,.3);next();}},18000+Math.random()*12000);next();}
 }
 duck(active:boolean){if(this.context&&this.bus)this.bus.gain.setTargetAtTime(active?.55:1,this.context.currentTime,active?.08:.12);}
 attach(player:HTMLMediaElement){
  if(this.primary.has(player))return;this.primary.add(player);
  if(this.context&&this.output){const source=this.context.createMediaElementSource(player);source.connect(this.output);}
  player.addEventListener('playing',()=>this.duck(true));
  for(const event of ['ended','pause','error'])player.addEventListener(event,()=>this.duck(false));
 }
 waitForReply(gender='male'){
  // The provided library is male; female callers retain their own voice.
  if(gender!=='male'||this.waiting)return;this.waiting=true;const epoch=this.epoch;
  const next=async()=>{
   if(!this.waiting||epoch!==this.epoch)return;
   let recent:string[]=[];try{recent=JSON.parse(sessionStorage.getItem('call-fillers')||'[]');}catch{}
   const choices=Object.keys(this.assets||{}).filter(id=>id.startsWith('filler_')&&!recent.includes(id));
   const id=choices[Math.floor(Math.random()*choices.length)];if(!id)return;
   this.filler=(async()=>{await this.buffer(id);if(!this.waiting||epoch!==this.epoch)return;sessionStorage.setItem('call-fillers',JSON.stringify([...recent,id].slice(-3)));this.duck(true);await this.play(id,false,false,.8);this.duck(false);})().catch(()=>{});
   await this.filler;if(this.waiting&&epoch===this.epoch)this.later(()=>void next(),6000);
  };
  this.later(()=>void next(),5000);
 }
 async finishWaiting(){this.waiting=false;await this.filler;}
 async replyEnded(){
  const epoch=this.epoch,events=this.scene.events_after_reply||[];this.scene={...this.scene,events_after_reply:[]};
  for(const event of events){
   const delay=Number(event.seconds??0);if(delay>0)await new Promise(resolve=>setTimeout(resolve,delay*1000));
   if(epoch!==this.epoch)return;await this.buffer(event.id);if(epoch!==this.epoch)return;
   await this.play(event.id,false,false,.7,Number(event.duration??1));
  }
 }
 hangup(){this.stop();void this.signal('hangup');}
 dispose(){this.stop();this.closed=true;void this.context?.close();this.buffers.clear();}
}
