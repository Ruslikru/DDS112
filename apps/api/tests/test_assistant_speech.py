"""Teacher assistant: mis-heard or mistyped command words are corrected to the command vocabulary before parsing."""
import pytest
from test_flows import app, TestClient, login, post
from apps.api.app.assistant import fix_keywords, clean_speech, SPEECH_PROMPT, speech_prompt

@pytest.mark.parametrize('spoken,fixed',[
 ('Белет','Билет'),
 ('открой белеты','открой билеты'),
 ('Покажи журнаал','Покажи журнал'),
 ('Открой жирнал','Открой журнал'),
 ('создай билет про пажар на 3 звезды','создай билет про пожар на 3 звезды'),
 ('в билете 1 поменяй сложнасть на 4','в билете 1 поменяй сложность на 4'),
 ('кто сейчас в класе','кто сейчас в классе'),
 ('Проверка робот','Проверка работ'),
 ('кто не в сети','кто не в сети'),
 ('Белый дом','Белый дом'),
 ('билеты','билеты'),
])
def test_command_words_are_corrected(spoken,fixed):
    assert fix_keywords(spoken)==fixed

def test_quotes_and_student_names_stay_as_written():
    assert fix_keywords('переименуй билет про лифт в «Лифт застрял»')=='переименуй билет про лифт в «Лифт застрял»'
    # «Сетин» is one letter away from «сети»: a student with that surname must not be turned into a command word.
    assert fix_keywords('где сидит Сетин')=='где сидит Сети'
    assert fix_keywords('где сидит Сетин',['Сетин'])=='где сидит Сетин'

def test_whisper_prompt_lists_commands():
    for word in ('журнал','билеты','классе','закрой'):assert word in SPEECH_PROMPT

def test_interpret_corrects_mis_heard_command():
    with TestClient(app) as c:
        login(c,'teacher')
        r=post(c,'/assistant/interpret',{'text':'Белет','context':{'page':'/'}}).json()
        assert r['intent']=='open_page' and r['action']=={'kind':'navigate','to':'/tickets'}
        r=post(c,'/assistant/interpret',{'text':'открой жирнал','context':{'page':'/'}}).json()
        assert r['action']=={'kind':'navigate','to':'/journal'}

@pytest.mark.parametrize('spoken,cleaned',[
 ('Служба сто два.','Служба 102'),
 ('Служба с тодва','Служба 102'),
 ('служба сто один','служба 101'),
 ('создай билет про пожар на три звезды','создай билет про пожар на 3 звезды'),
 ('в билете двенадцать поменяй сложность на четыре','в билете 12 поменяй сложность на 4'),
 ('в двенадцатом билете поменяй сложность','в билете 12 поменяй сложность'),
 ('сорок два пострадавших','42 пострадавших'),
 ('двое пострадавших','двое пострадавших'),
 ('переименуй билет в «Сто бед»','переименуй билет в «Сто бед»'),
 ('за каким ПК сидит Кузнецов','за каким ПК сидит Кузнецов'),
 ('Служба 100 один.','Служба 101'),
 ('Десидит Кузнецов.','Где сидит Кузнецов'),
 ('ПК 12 2 пострадавших','ПК 12 2 пострадавших'),
])
def test_spoken_numbers_become_digits(spoken,cleaned):
    assert clean_speech(spoken)==cleaned

def test_whisper_prompt_lists_services_and_digits():
    from test_flows import SessionLocal
    from sqlalchemy import select
    from apps.api.app.db import User
    with TestClient(app):pass
    with SessionLocal() as db:prompt=speech_prompt(db,db.scalar(select(User).where(User.login=='admin')))
    assert 'Служба 101' in prompt and 'на 3 звезды' in prompt and 'билете 12' in prompt
