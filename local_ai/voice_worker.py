"""Isolated speech process: JSON lines on stdin/stdout; model logs go to stderr."""
import contextlib
import json
import os
import sys
import time
import re
import wave as wav_module
import numpy as np
from pathlib import Path

os.environ['HF_HUB_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
root=Path(sys.argv[1])
output=sys.stdout
sys.stdout=sys.stderr
import torch
import soundfile as sf
torch.set_num_threads(min(6,os.cpu_count() or 2))
lib=Path(torch.__file__).parent/'lib'
os.environ['PATH']=str(lib)+os.pathsep+os.environ.get('PATH','')
dll=os.add_dll_directory(str(lib)) if os.name=='nt' else None
tts=None;tts_key=None;stt=None;stt_key=None;piper_cache={}

def piper_voice(name,device='cpu'):
    from piper import PiperVoice
    key=(name,device)
    if key not in piper_cache:
        piper_cache[key]=PiperVoice.load(str(root.parent/'piper'/'FINAL_MODELS_29800'/(name+'_29800.onnx')),use_cuda=device=='cuda')
    return piper_cache[key]

def run(req):
    global tts,tts_key,stt,stt_key
    if req['op']=='status':
        return {'gpu':torch.cuda.is_available(),'models':{k:(root/v).exists() for k,v in {'piper':'../piper/FINAL_MODELS_29800/denis_29800.onnx','piper-denis':'../piper/FINAL_MODELS_29800/denis_29800.onnx','piper-irina':'../piper/FINAL_MODELS_29800/irina_29800.onnx','piper-ruslan':'../piper/FINAL_MODELS_29800/ruslan_29800.onnx','tiny':'whisper-tiny/model.bin','base':'whisper-base/model.bin','gigaam':'gigaam/config.json'}.items()}}
    device=req.get('device','cpu')
    if device=='gpu' and not torch.cuda.is_available():raise ValueError('CUDA GPU недоступен. Выберите CPU.')
    device='cuda' if device=='gpu' else 'cpu'
    start=time.perf_counter()
    if req['op']=='warm':
        model=req.get('model','gigaam')
        if (model,device)!=stt_key:
            if model=='gigaam':
                sys.path.insert(0,str(root/'gigaam'))
                from modeling_gigaam import GigaAMModel
                stt=GigaAMModel.from_pretrained(str(root/'gigaam'),local_files_only=True).to(device).eval()
            else:
                from faster_whisper import WhisperModel
                stt=WhisperModel(str(root/('whisper-'+model)),device=device,compute_type='float16' if device=='cuda' else 'int8',local_files_only=True,cpu_threads=6)
            stt_key=(model,device)
        name=req.get('voice','denis')
        for candidate in ('denis','irina','ruslan'):
            piper_voice(candidate)
        if ('piper',name)!=tts_key:
            tts=piper_voice(name)
            tts_key=('piper',name)
        return {'seconds':round(time.perf_counter()-start,2),'stt':model,'tts':name}
    if req['op']=='transcribe':
        key=(req['model'],device)
        if key!=stt_key:
            stt=None
            if req['model']=='gigaam':
                sys.path.insert(0,str(root/'gigaam'))
                from modeling_gigaam import GigaAMModel
                stt=GigaAMModel.from_pretrained(str(root/'gigaam'),local_files_only=True).to(device).eval()
            else:
                from faster_whisper import WhisperModel
                stt=WhisperModel(str(root/('whisper-'+req['model'])),device=device,compute_type='float16' if device=='cuda' else 'int8',local_files_only=True,cpu_threads=6)
            stt_key=key
        if req['model']=='gigaam':
            import av
            resampler=av.AudioResampler(format='flt',layout='mono',rate=16000)
            parts=[]
            with av.open(req['input']) as container:
                for frame in container.decode(audio=0):
                    parts.extend(piece.to_ndarray().reshape(-1).copy() for piece in resampler.resample(frame))
            parts.extend(piece.to_ndarray().reshape(-1).copy() for piece in resampler.resample(None))
            if not parts:raise ValueError('В записи нет звука.')
            wav=torch.from_numpy(np.concatenate(parts)).to(device).float().unsqueeze(0)
            length=torch.tensor([wav.shape[-1]],device=device)
            if wav.shape[-1]>25*16000:raise ValueError('Для GigaAM запись должна быть короче 25 секунд.')
            with torch.inference_mode():
                encoded,encoded_len=stt.model.forward(wav,length)
                text=stt.model.decoding.decode(stt.model.head,encoded,encoded_len)[0].strip()
        else:
            # Словарь ожидаемых слов используется только моделью Whisper.
            segments,info=stt.transcribe(req['input'],language='ru',beam_size=int(req.get('beam') or 1),vad_filter=True,condition_on_previous_text=False,initial_prompt=req.get('prompt') or None)
            text=' '.join(s.text.strip() for s in segments).strip()
        if not text:raise ValueError('Речь не распознана. Повторите запись.')
        return {'text':text,'seconds':round(time.perf_counter()-start,2),'model':req['model']}
    if req['model'].startswith('piper'):
        name=req['model'].removeprefix('piper-') if req['model']!='piper' else ('irina' if req.get('gender')=='female' else 'denis')
        if name not in ('denis','irina','ruslan'):raise ValueError('Неизвестный голос Piper')
        key=('piper',name)
        if key!=tts_key:
            tts=piper_voice(name,device)
            tts_key=key
        with wav_module.open(req['output'],'wb') as wav_file:
            tts.synthesize_wav(req['text'],wav_file)
        with wav_module.open(req['output'],'rb') as wav_file:
            duration=wav_file.getnframes()/wav_file.getframerate()
        return {'seconds':round(time.perf_counter()-start,2),'duration':round(duration,2),'voice':name}
    key=(req['model'],device)
    if key!=tts_key:
        tts=None
        if torch.cuda.is_available():torch.cuda.empty_cache()
        if req['model']=='silero':
            tts=torch.package.PackageImporter(str(root/'silero-v5-ru.pt')).load_pickle('tts_models','model')
            tts.to(torch.device(device))
        else:
            from qwen_tts import Qwen3TTSModel
            tts=Qwen3TTSModel.from_pretrained(str(root/'qwen-tts'),device_map=device,dtype=torch.bfloat16 if device=='cuda' else torch.float32,attn_implementation='sdpa',local_files_only=True)
        tts_key=key
    female=req.get('gender')=='female'
    with torch.inference_mode():
        if req['model']=='silero':
            voice='ru_oksana' if female else 'ru_eduard'
            wave=tts.apply_tts(text=req['text'],speaker=voice,sample_rate=24000).cpu().numpy();sr=24000
        else:
            voice='Serena' if female else 'Ryan'
            chunks=[];chunk=''
            for word in req['text'].split():
                if len(chunk)+len(word)>300 and chunk:chunks.append(chunk);chunk=''
                chunk=(chunk+' '+word).strip()
            if chunk:chunks.append(chunk)
            parts=[]
            for chunk in chunks:
                waves,sr=tts.generate_custom_voice(text=chunk,language='Russian',speaker=voice,instruct='Speak Russian clearly. '+req.get('emotion','Calm, confident delivery.'),non_streaming_mode=True,max_new_tokens=min(1400,max(160,len(chunk)*4)),do_sample=False)
                parts.append(waves[0])
            wave=np.concatenate(parts)
    sf.write(req['output'],wave,sr)
    return {'seconds':round(time.perf_counter()-start,2),'duration':round(len(wave)/sr,2),'voice':voice}

for line in sys.stdin:
    try:result={'ok':True,**run(json.loads(line))}
    except Exception as e:result={'ok':False,'error':str(e)}
    output.write(json.dumps(result,ensure_ascii=False)+'\n');output.flush()
