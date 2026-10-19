"""Teacher assistant: the place of the incident in the create command, and one-click answers about victims."""
import pytest
from test_flows import app, TestClient, login, post
from test_assistant_tickets import ask, follow, run, STORY
from apps.api.app.assistant_tickets import parse_address
from apps.api.app.scenario_wizard import split_address

@pytest.mark.parametrize('text,address',[
 ('создай билет про пожар по адресу улица Ленина 5','улица Ленина 5'),
 ('создай билет про пожар на улице Садовой, дом 3, для службы 101','улица Садовой, дом 3'),
 ('адрес: проспект Мира 10','проспект Мира 10'),
 ('адрес Ясный проезд 7','Ясный проезд 7'),
 ('создай билет про пожар на улице','') ,
 ('создай билет про пожар на 3 звезды',''),
])
def test_address_is_read_from_the_phrase(text,address):
    assert parse_address(text)==address

@pytest.mark.parametrize('value,parts',[
 ('улица Ленина, дом 5',('улица Ленина','5')),
 ('улица Ленина 5',('улица Ленина','5')),
 ('проспект Мира 10к2',('проспект Мира','10к2')),
 ('Ясный проезд',('Ясный проезд','')),
])
def test_split_address(value,parts):
    assert split_address(value)==parts

def test_address_does_not_leak_into_the_incident():
    from apps.api.app.assistant_tickets import parse_create
    slots=parse_create('создай билет про пожар по адресу улица Ленина 5 для службы 101 на 3 звезды',[])
    assert slots['incident_query']=='пожар' and slots['address']=='улица Ленина 5' and slots['difficulty']==3

def test_address_reaches_the_card_and_the_draft(monkeypatch):
    from apps.api.app import scenario_wizard
    monkeypatch.setattr(scenario_wizard,'complete',lambda *a,**kw:({'description':STORY},{'model':'test'}))
    with TestClient(app) as c:
        login(c,'teacher')
        r=ask(c,'создай билет про пожар для службы 101 на 3 звезды в режиме ДДС без пострадавших')
        assert r['confirm_required'] and 'Черновик с описанием и звонками' in r['preview']
        # An edit after the confirmation card is accepted and the card is rebuilt.
        r=follow(c,r,'адрес улица Ленина 5')
        assert r['confirm_required'] and r['slots']['address']=='улица Ленина 5' and 'Адрес: улица Ленина 5' in r['preview']
        r=follow(c,r,'сложность 4')
        assert r['slots']['difficulty']==4 and r['slots']['address']=='улица Ленина 5','later edits keep the address'
        generated=run(c,r);assert generated.status_code==200,generated.text
        assert 'Ленина' in generated.json()['slots']['title'],'the draft title carries the named street'

def test_victims_buttons_answer_both_questions():
    with TestClient(app) as c:
        login(c,'teacher')
        r=ask(c,'создай билет про пожар для службы 101 на 3 звезды в режиме ДДС')
        assert r['missing'][0]['slot']=='victims'
        labels=[o['label'] for o in r['missing'][0]['options']]
        assert labels==['Нет','Пока неизвестно','Один','Двое','Трое','Больше']
        two=follow(c,r,'Двое',victims='yes:2')
        assert two['confirm_required'] and two['slots']['victims']=='yes' and two['slots']['victims_count']==2 and 'есть, 2 чел.' in two['preview']
        more=follow(c,r,'Больше',victims='yes')
        assert more['missing'][0]['slot']=='victims_count' and [o['value'] for o in more['missing'][0]['options']][:3]==[1,2,3]
        five=follow(c,more,'5',victims_count=5)
        assert five['confirm_required'] and five['slots']['victims_count']==5
