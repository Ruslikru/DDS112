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
        return {'gpu':torch.cuda.is_available(),'models':{k:(root/v).exists() for k,v in {'piper':'../piper/FINAL_MODELS_29800/denis_29800.onnx','piper-denis':'../piper/FINAL_MODELS_29800/denis_29800.onnx','piper-irina':'../piper/FINAL_MODELS_29800/irina_29800.onnx','piper-ruslan':'../piper/FINAL_MODELS_29800/ruslan_29800.onnx','gigaam':'gigaam/config.json'}.items()}}
    device=req.get('device','cpu')
    if device=='gpu' and not torch.cuda.is_available():raise ValueError('CUDA GPU недоступен. Выберите CPU.')
    device='cuda' if device=='gpu' else 'cpu'
    start=time.perf_counter()
    if req['op'] in ('warm','transcribe') and req.get('model','gigaam')!='gigaam':
        raise ValueError('Распознавание доступно только через GigaAM v3')
    if req['op']=='warm':
        model=req.get('model','gigaam')
        if (model,device)!=stt_key:
            sys.path.insert(0,str(root/'gigaam'))
            from modeling_gigaam import GigaAMModel
            stt=GigaAMModel.from_pretrained(str(root/'gigaam'),local_files_only=True).to(device).eval()
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
            sys.path.insert(0,str(root/'gigaam'))
            from modeling_gigaam import GigaAMModel
            stt=GigaAMModel.from_pretrained(str(root/'gigaam'),local_files_only=True).to(device).eval()
            stt_key=key
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
    raise ValueError('Озвучка доступна только голосами Piper')

for line in sys.stdin:
    try:result={'ok':True,**run(json.loads(line))}
    except Exception as e:result={'ok':False,'error':str(e)}
    output.write(json.dumps(result,ensure_ascii=False)+'\n');output.flush()
