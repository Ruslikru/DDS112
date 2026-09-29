"""Real-model DDS generation and conversation, isolated from user data."""
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

data=Path(tempfile.mkdtemp(prefix='112-dds-check-'))
os.environ.update(DATA_DIR=str(data),DATABASE_URL='sqlite:///'+(data/'check.db').as_posix(),DEMO_PASSWORD='DdsCheck112!')
from fastapi.testclient import TestClient
from apps.api.app.main import app


def main():
    result={}
    with TestClient(app) as c:
        def post(path,body=None):
            r=c.post('/api'+path,json=body or {},headers={'X-Requested-With':'Training112'})
            r.raise_for_status();return r.json()
        post('/login',{'login':'admin','password':'DdsCheck112!'})
        kind=c.get('/api/classifier?q=трубы').json()[0]['title']
        start=time.monotonic()
        draft=post('/ai/generate',{'mode':'dds','topic':'Прорыв трубы: вода течёт в подъезде жилого дома, пострадавших нет.',
                    'incident_type':kind,'district':'Щукино','own_service':'ДДС района','services':['Мосводоканал']})
        result['generation_seconds']=round(time.monotonic()-start,2)
        result['draft']=draft
        task=draft['data']['tasks'][0]
        assert task['initial_card']['victims']=='no'
        assert task['initial_card']['incident_type']==kind and task['mode']=='dds'
        saved=post('/tickets',draft['data']);post(f'/tickets/{saved["id"]}/publish')
        student=next(s for s in c.get('/api/users').json() if s['login']=='student')
        post('/assignments',{'version_id':saved['id'],'students':[student['id']]})
        post('/logout');post('/login',{'login':'student','password':'DdsCheck112!'})
        a=next(a for a in c.get('/api/assignments').json() if a['title']==draft['data']['title'])
        p=post(f'/assignments/{a["id"]}/start')
        result['questions']=[]
        for target,text in [('caller','Как Вас зовут?'),('caller','Назовите адрес, пожалуйста'),
                            ('brigade','Передаю заявку: прорыв трубы. Направьте бригаду по указанному адресу.'),
                            ('brigade','Вы уже прибыли? Доложите ход работ.')]:
            latest=c.get('/api/attempts/'+str(p['id'])).json()
            p=post(f'/ai/attempts/{p["id"]}/contact',{'contact_id':target,'text':text,'revision':latest['revision'],'command_id':str(uuid.uuid4())})
            answer=p['state']['messages'][-1]['text']
            assert not answer.startswith('Уточните, пожалуйста'),(text,answer)
            result['questions'].append({'text':text,'answer':answer})
        assert result['questions'][0]['answer']==task['initial_card']['name']
        assert task['initial_card']['house'] in result['questions'][1]['answer']
        assert p['state']['services']['ДДС района'][-1]['status']=='Получена службой'
    Path('local_ai/dds-check-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: DDS generation, publication, caller identity/address, brigade dispatch/progress, manual status control')


if __name__=='__main__': main()
