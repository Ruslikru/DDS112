"""Regression with the real local model, isolated from the user's database."""
import json
import os
from pathlib import Path
import tempfile
import uuid

data=Path(tempfile.mkdtemp(prefix='112-caller-check-'))
os.environ.update(DATA_DIR=str(data),DATABASE_URL='sqlite:///'+(data/'check.db').as_posix(),DEMO_PASSWORD='CallerCheck112!')
from fastapi.testclient import TestClient
from apps.api.app.main import app


def main():
    results=[]
    with TestClient(app) as c:
        def post(path,body):
            r=c.post('/api'+path,json=body,headers={'X-Requested-With':'Training112'})
            r.raise_for_status()
            return r.json()
        post('/login',{'login':'student','password':'CallerCheck112!'})
        assignment=next(a for a in c.get('/api/assignments').json() if 'Запах газа' in a['title'])
        p=post(f'/assignments/{assignment["id"]}/start',{})
        p=post(f'/attempts/{p["id"]}/command',{'type':'accept_call','revision':p['revision'],'command_id':str(uuid.uuid4())})
        for text,expected in [('Как Вас зовут?','name'),('Подскажите, как Вас зову?','name'),
                              ('Как я могу к вам обращаться?','name'),('Назовите адрес.','address')]:
            p=post(f'/ai/attempts/{p["id"]}/question',{'text':text,'revision':p['revision'],'command_id':str(uuid.uuid4())})
            assert p['state']['asked'][-1]==expected,(text,p['state']['dialogue'][-1])
            answer=p['state']['dialogue'][-1]['text']
            if expected=='name': assert answer=='Алексей Соколов.'
            results.append({'question':text,'answer':answer,'matched':expected})
    Path('local_ai/caller-check-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: gas scenario, name paraphrases and typo, stable facts, address')


if __name__=='__main__': main()
