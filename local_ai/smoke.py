"""Real-model smoke test against an isolated database; never touches user attempts."""
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

data=Path(tempfile.mkdtemp(prefix='112-ai-smoke-'))
os.environ.update(DATA_DIR=str(data),DATABASE_URL='sqlite:///'+(data/'test.db').as_posix(),DEMO_PASSWORD='LocalSmoke112!')
from fastapi.testclient import TestClient
from apps.api.app.main import app
from local_ai.engine import engine

def main():
    results={}
    with TestClient(app) as client:
        def post(path,body=None):
            response=client.post('/api'+path,json=body or {},headers={'X-Requested-With':'Training112'})
            response.raise_for_status();return response.json()
        post('/login',{'login':'admin','password':'LocalSmoke112!'})
        start=time.monotonic()
        generated=post('/ai/generate',{'mode':'112','topic':'Учебное ДТП во дворе Москвы: две легковые машины, пострадавших нет. Заявитель видел столкновение.'})
        results['generation']=generated;results['generation_seconds']=round(time.monotonic()-start,2)
        post('/logout')
        post('/login',{'login':'student','password':'LocalSmoke112!'})
        a=next(a for a in client.get('/api/assignments').json() if 'Задымление' in a['title'])
        p=post(f'/assignments/{a["id"]}/start')
        p=post(f'/attempts/{p["id"]}/command',{'type':'accept_call','revision':p['revision'],'command_id':str(uuid.uuid4())})
        results['questions']=[]
        for text in ['Как я могу к вам обращаться?','Где это произошло?','Есть раненые?']:
            p=post(f'/ai/attempts/{p["id"]}/question',{'text':text,'revision':p['revision'],'command_id':str(uuid.uuid4())})
            results['questions'].append({'question':text,'answer':p['state']['dialogue'][-1]['text'],'asked':p['state']['asked']})
        def cmd(kind,payload=None):
            nonlocal p
            p=post(f'/attempts/{p["id"]}/command',{'type':kind,'revision':p['revision'],'command_id':str(uuid.uuid4()),'payload':payload or {}})
        cmd('draft',{'street':'Берзарина','house':'21','incident_type':'Задымление мусоропровода','description':'Дым в доме, пострадавших нет.'})
        cmd('notify',{'services':['Служба 101']});cmd('end_call');cmd('finish')
        score_before=p['assessment']['score']
        post('/logout');post('/login',{'login':'teacher','password':'LocalSmoke112!'})
        reviewed=post(f'/ai/attempts/{p["id"]}/review')
        assert reviewed['assessment']['score']==score_before
        results['review']=reviewed['assessment']['ai_review']
    (Path(__file__).parent/'smoke-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Real-model smoke completed; results in local_ai/smoke-results.json')

if __name__=='__main__': main()
