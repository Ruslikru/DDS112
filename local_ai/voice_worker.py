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

def piper_voice(name,device='cpu',threads=2):
    from piper import PiperVoice
    from piper.config import PiperConfig
    import onnxruntime as ort
    key=(name,device,threads)
    if key not in piper_cache:
        # Only execution parameters change. The trained ONNX files remain read-only.
        path=root.parent/'piper'/'FINAL_MODELS_29800'/(name+'_29800.onnx')
        options=ort.SessionOptions();options.intra_op_num_threads=threads;options.inter_op_num_threads=1
        for old in list(piper_cache):
            if old[2]!=threads:piper_cache.pop(old)
        piper_cache[key]=PiperVoice(config=PiperConfig.from_dict(json.loads(Path(str(path)+'.json').read_text('utf-8'))),
            session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider']))
    return piper_cache[key]

def run(req):
    global tts,tts_key,stt,stt_key
    if req['op']=='status':
        return {'gpu':torch.cuda.is_available(),'models':{k:(root/v).exists() for k,v in {'piper':'../piper/FINAL_MODELS_29800/denis_29800.onnx','piper-denis':'../piper/FINAL_MODELS_29800/denis_29800.onnx','piper-irina':'../piper/FINAL_MODELS_29800/irina_29800.onnx','piper-ruslan':'../piper/FINAL_MODELS_29800/ruslan_29800.onnx','gigaam':'gigaam/config.json'}.items()}}
    device=req.get('device','cpu')
    if device=='gpu' and not torch.cuda.is_available():raise ValueError('CUDA GPU недоступен. Выберите CPU.')
    device='cuda' if device=='gpu' else 'cpu'
    start=time.perf_counter()
    threads=max(1,min(16,int(req.get('stt_threads',2))))
    if torch.get_num_threads()!=threads:torch.set_num_threads(threads)
    tts_threads=max(1,min(16,int(req.get('tts_threads',2))))
    warm=stt_key is not None if req['op'] in ('warm','transcribe') else ('piper',req.get('model','piper').removeprefix('piper-'),tts_threads)==tts_key
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
            voice=piper_voice(candidate,threads=tts_threads)
            import io
            with wav_module.open(io.BytesIO(),'wb') as wav_file:voice.synthesize_wav('На связи.',wav_file)
        # Exercise the acoustic path too, rather than marking loaded weights as warmed.
        with torch.inference_mode():
            stt.model.forward(torch.zeros((1,16000),device=device),torch.tensor([16000],device=device))
        if ('piper',name,tts_threads)!=tts_key:
            tts=piper_voice(name,threads=tts_threads)
            tts_key=('piper',name,tts_threads)
        return {'seconds':round(time.perf_counter()-start,2),'stt':model,'tts':name,'stt_threads':threads,'tts_threads':tts_threads}
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
        if not re.search(r'[а-яёa-z0-9]',text,re.I):raise ValueError('Речь не распознана. Повторите запись.')
        return {'text':text,'seconds':round(time.perf_counter()-start,2),'model':req['model'],'warm':warm,'threads':threads}
    if req['model'].startswith('piper'):
        name=req['model'].removeprefix('piper-') if req['model']!='piper' else ('irina' if req.get('gender')=='female' else 'denis')
        if name not in ('denis','irina','ruslan'):raise ValueError('Неизвестный голос Piper')
        key=('piper',name,tts_threads)
        warm=(name,device,tts_threads) in piper_cache
        if key!=tts_key:
            tts=piper_voice(name,device,tts_threads)
            tts_key=key
        with wav_module.open(req['output'],'wb') as wav_file:
            tts.synthesize_wav(req['text'],wav_file)
        with wav_module.open(req['output'],'rb') as wav_file:
            duration=wav_file.getnframes()/wav_file.getframerate()
        return {'seconds':round(time.perf_counter()-start,2),'duration':round(duration,2),'voice':name,'warm':warm,'threads':tts_threads}
    raise ValueError('Озвучка доступна только голосами Piper')

for line in sys.stdin:
    try:result={'ok':True,**run(json.loads(line))}
    except Exception as e:result={'ok':False,'error':str(e)}
    output.write(json.dumps(result,ensure_ascii=False)+'\n');output.flush()
