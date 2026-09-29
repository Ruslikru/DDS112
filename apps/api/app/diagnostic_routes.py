import io
import json
import platform
import time
import zipfile
from collections import defaultdict
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel,Field
from . import main as m
from .diagnostics import event,log_dir,scrub

router=APIRouter(prefix='/api/diagnostics')
class ClientEvent(BaseModel):
    kind:str=Field(max_length=60)
    message:str=Field(default='',max_length=2000)
    stack:str=Field(default='',max_length=4000)
    path:str=Field(default='',max_length=200)
    request_id:str=Field(default='',max_length=64)
    session_id:str=Field(default='',max_length=64)
    viewport:str=Field(default='',max_length=40)

@router.post('/client')
def client(data:ClientEvent,u=Depends(m.current)):
    # Only authenticated users can append diagnostics; no form values are sent by the UI.
    event('client',actor_id=u.id,role=u.role,kind=data.kind,message=data.message,stack=data.stack,
          path=data.path.split('?')[0],client_request_id=data.request_id,ui_session=data.session_id,viewport=data.viewport)
    return {'ok':True}

@router.get('/bundle')
def bundle(u=Depends(m.current),db=Depends(m.getdb)):
    m.admin(u)
    m.audit(db,u,'diagnostic_bundle_exported');db.commit()
    event('diagnostic_bundle_exported',actor_id=u.id)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('system.json',json.dumps({'version':'0.6.1','os':platform.platform(),'python':platform.python_version(),
            'database':m.engine.dialect.name,'collected_at':m.now()},ensure_ascii=False,indent=2))
        # Bounded tails, with a fixed allow-list. No database, .env, passwords or full audit payloads.
        for path in sorted(log_dir().iterdir()):
            if not path.is_file() or path.is_symlink(): continue
            if not any(path.name==prefix or path.name.startswith(prefix+'.') for prefix in ['diagnostics.jsonl','server.log','launcher.log','local-ai.log']): continue
            with path.open('rb') as file:
                file.seek(max(0,path.stat().st_size-1_000_000));text=file.read(1_000_000).decode('utf-8',errors='replace')
            archive.writestr('logs/'+path.name,'\n'.join(scrub(line) for line in text.splitlines()))
        archive.writestr('README.txt','Local technical diagnostics. No database or full scenario texts included.\nTimes use UTC; request_id correlates UI and server events. Log tails may start mid-line.\n')
    return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="training112-diagnostics.zip"'})
