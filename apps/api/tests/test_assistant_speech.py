"""Teacher assistant: mis-heard or mistyped command words are corrected to the command vocabulary before parsing."""
import pytest
from test_flows import app, TestClient, login, post
from apps.api.app.assistant import fix_keywords, SPEECH_PROMPT

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
