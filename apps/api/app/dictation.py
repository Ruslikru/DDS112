"""Prepare spelling drills as audio, keeping the target text out of student prompts."""
import re

PROMPT='Прослушайте запись и введите услышанное без ошибок.'

def is_dictation(data):
    return data.get('kind')=='text' and (data.get('dictation') or re.search(r'введите.*(без ошибок|точно)|напишите.*без ошибок',data.get('prompt',''),re.I))

def prepare(data,db,owner):
    if not is_dictation(data):return data
    from .voice import prepare as voice_prepare
    data={**data,'dictation':True,'prompt':PROMPT,'audio_text':data.get('audio_text') or data['answer']}
    result=voice_prepare({'tasks':[{'contacts':[{'id':'mini','response':data['audio_text'],'voice_gender':data.get('voice_gender','female')}]}]},db,owner)
    data['voice_key']=result['tasks'][0]['contacts'][0]['voice_lines'][0]['voice_key']
    return data

def seed(db):
    from sqlalchemy import select
    from .classroom_models import MiniQuestion
    for question in db.scalars(select(MiniQuestion)):
        if is_dictation(question.data):question.data=prepare(question.data,db,question.owner_id)
    db.commit()
