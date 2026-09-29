from test_flows import app
import importlib.util
from pathlib import Path
import pytest
from local_ai.speech_text import spoken_text, identity_answer
from local_ai.voice import VoiceRuntime

@pytest.mark.parametrize('text,expected', [
    ('Дом 28, квартира 112.', 'Дом двадцать восемь, квартира сто двенадцать.'),
    ('Бригада 1001, дом 26/2.', 'Бригада одна тысяча один, дом двадцать шесть дробь два.'),
    ('+7 (900) 123-45-67', 'семь девять ноль ноль один два три четыре пять шесть семь'),
    ('Код 007', 'Код ноль ноль семь'),
    ('Пострадавших нет.', 'Пострадавших нет.'),
])
def test_spoken_numbers(text, expected):
    assert spoken_text(text) == expected

@pytest.mark.parametrize('question', ['Как вас зовут?', 'Повторите ваше имя', 'Назовите фамилию', 'Представьтесь', 'Кто говорит?', 'Как к вам обращаться?'])
def test_identity_uses_authored_fact_without_loading_model(tmp_path, question):
    runtime = VoiceRuntime(tmp_path)
    result = runtime.classify(question, {'gender':'female','questions':[{'id':'identity-custom','question':'Как вас зовут?','answer':'Елена Андреевна Соколова.'}]})
    assert result['text'] == 'Елена Андреевна Соколова.'
    assert result['id'] == 'identity-custom'
    assert runtime.llm is None

def test_other_question_does_not_return_name():
    assert identity_answer('Есть пострадавшие?', [{'id':'name','question':'Имя','answer':'Елена'}]) is None

def test_native_settings_require_admin(tmp_path):
    path = Path(__file__).resolve().parents[3] / 'packaging' / 'native_window.py'
    spec = importlib.util.spec_from_file_location('voice_native_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    runtime = VoiceRuntime(tmp_path)
    for authorize in [None, lambda: False]:
        with pytest.raises(PermissionError): module.VoiceBridge(runtime, authorize_settings=authorize).voice_settings({'chat_enabled':True})
    module.VoiceBridge(runtime, authorize_settings=lambda: True).voice_settings({'chat_enabled':True})
    assert runtime.settings()['live']['chat_enabled'] is True
