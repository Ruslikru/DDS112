import pytest
from local_ai.dds_dialogue import reply

CONTACT={'id':'brigade','kind':'brigade','name':'Старший','response':'Выезжаем.'}
REPORT='Москва, улица Конёнкова, дом 13. Подъезжаем к адресу. Уточните удобный подъезд к месту происшествия.'
def state(report=REPORT,previous=None):
 messages=[{'contact_id':'brigade','who':'Старший','direction':'incoming','text':report}]
 if previous:messages.extend([{'contact_id':'brigade','who':'Диспетчер → Старший','text':previous},{'contact_id':'brigade','who':'Старший','direction':'outgoing_answer','text':'Есть сведения о подъезде?'}])
 return {'messages':messages,'contact_counts':{'brigade':1}}
def no_model(*args,**kwargs):pytest.fail('This short call must not wait for Qwen')

@pytest.mark.parametrize('text,fragment',[
 ('Подъезд с правой стороны втором.','Проверим подъезд'),('Второй подъезд.','Проверим подъезд'),
 ('Подъезд с правой стороны дома.','Проверим подъезд'),('Заезжайте через двор.','Проверим подъезд'),
 ('Я не знаю как подъехать, данных нет.','сами найдём'),('Данных нет.','сами найдём'),
 ('Карту посмотрите или людей поспрашивайте.','на месте'),('Уточните у местных.','на месте'),
])
def test_access_reply_ends_call_without_inference(text,fragment):
 value=reply(text,{},CONTACT,state(),[],no_model)
 assert value['call_end'] and fragment in value['answer']
 assert value['ai']['source']=='rule'


def test_off_topic_call_asks_once_then_ends():
 first=reply('Сегодня хорошая погода.',{},CONTACT,state(),[],no_model)
 assert not first['call_end'] and 'подъезд' in first['answer']
 second=reply('Не о том говорим.',{},CONTACT,state(previous='Сегодня хорошая погода.'),[],no_model)
 assert second['call_end'] and 'на месте' in second['answer']


def test_new_incoming_call_gets_its_own_turn_budget():
 s=state(previous='Старый разговор');s['messages'][-1]['call_end']=True
 s['messages'].append({'contact_id':'brigade','direction':'incoming','who':'Старший','text':REPORT})
 value=reply('Повторите вопрос.',{},CONTACT,s,[],no_model)
 assert not value['call_end']


def test_hold_request_is_respected():
 value=reply('Не вешайте трубку, подождите.',{},CONTACT,state(previous='Секунду.'),[],lambda *a,**kw:({'text':'Ожидаю.'},{'model':'test'}))
 assert not value['call_end']


@pytest.mark.parametrize('kind',['caller','service'])
def test_access_question_uses_available_contact_facts_without_model(kind):
 contact={'id':'source','kind':kind,'name':'Источник','response':'На связи.'}
 options=[{'id':'access','question':'Как подъехать к месту происшествия?','answer':'Проезд закрыт. Въезд со двора.'}]
 value=reply('Подскажите как проехать к дому?',{},contact,{},options,no_model)
 assert value['answer']=='Проезд закрыт. Въезд со двора.'
 assert value['question_id']=='access' and value['call_end']
